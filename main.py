import datetime
import logging
import time
from typing import List, Optional

import phonenumbers
import requests
from backports.datetime_fromisoformat import MonkeyPatch
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.models import APIKey
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from pydantic import ValidationError
from starlette import status
from starlette.responses import JSONResponse, RedirectResponse

from airtable import (AIRTABLE_AUTH_HEADER, AIRTABLE_BASE_URL,
                      AIRTABLE_REQUEST_DELAY,
                      build_airtable_datetime_expression,
                      build_airtable_formula_chain, get_airtable_records,
                      get_citizen_id_matched_airtable_records)
from models import (CareProvidedReport, CareRequest, CareRequestResponse,
                    CareStatus, RequestStatus)
from security import API_KEY_NAME, get_api_key
from utils import hyphenate_citizen_id

MonkeyPatch.patch_fromisoformat()

TIMEZONE = datetime.timezone(datetime.timedelta(hours=7))

CHANNEL_NAME = 'BKKCOVID19CONNECT'

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/openapi.json", tags=["documentation"])
async def get_open_api_endpoint(api_key: APIKey = Depends(get_api_key)):
    response = JSONResponse(
        get_openapi(title='BKKCOVID19CONNECT API', version=1, routes=app.routes)
    )
    return response


@app.get("/docs", tags=["documentation"])
async def get_documentation(api_key: APIKey = Depends(get_api_key), request: Request = Query(...)):
    response = get_swagger_ui_html(
        openapi_url="/openapi.json", title="API docs")
    response.set_cookie(
        API_KEY_NAME,
        value=api_key,
        domain=request.url.hostname,
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response


@app.get("/redoc", tags=["documentation"])
async def get_redoc(api_key: APIKey = Depends(get_api_key), request: Request = Query(...)):
    response = get_redoc_html(openapi_url="/openapi.json", title="API docs")
    response.set_cookie(
        API_KEY_NAME,
        value=api_key,
        domain=request.url.hostname,
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response


@app.get("/logout")
async def route_logout_and_remove_cookie(request: Request):
    response = RedirectResponse(url="/")
    response.delete_cookie(API_KEY_NAME, domain=request.url.hostname)
    return response


@app.get("/requests", response_model=CareRequestResponse)
async def read_requests(last_status_change_since: Optional[datetime.datetime] = Query(None),
                        last_status_change_until: Optional[datetime.datetime] = Query(None),
                        status: Optional[List[RequestStatus]] = Query(None),
                        care_status: Optional[List[CareStatus]] = Query(None),
                        api_key: APIKey = Depends(get_api_key)):

    filter_by_formulas = []

    if last_status_change_since:
        filter_by_formulas.append(
            "DATETIME_DIFF({Last Status Change Datetime}," +
            f"{build_airtable_datetime_expression(last_status_change_since, TIMEZONE)}) >= 0")

    if last_status_change_until:
        filter_by_formulas.append(
            "DATETIME_DIFF({Last Status Change Datetime}," +
            f"{build_airtable_datetime_expression(last_status_change_until, TIMEZONE)}) < 0")

    if status and len(status) > 0:
        filter_by_formulas.append(build_airtable_formula_chain('OR', list(
            map(lambda status: f"{{Status}}=\"{status}\"", status))))

    if care_status and len(care_status) > 0:
        filter_by_formulas.append(build_airtable_formula_chain('OR', list(
            map(lambda care_status: f"{{Care Status}}=\"{care_status}\"", care_status))))

    params = {
        'pageSize': 100,
    }

    if len(filter_by_formulas) > 0:
        params['filterByFormula'] = build_airtable_formula_chain('AND', filter_by_formulas)

    records = get_airtable_records(params)

    response_data = []

    for record in records:
        fields = record.get('fields', [])
        try:
            response_data.append(CareRequest(
                citizen_id=fields.get('Citizen ID').replace("-", "") if fields.get('Citizen ID') else None,
                first_name=fields.get('First Name'),
                last_name=fields.get('Last Name'),
                phone_number=phonenumbers.format_number(phonenumbers.parse(
                    fields.get('Phone Number'), "TH"), phonenumbers.PhoneNumberFormat.E164),
                email=fields.get('Email'),
                sex=fields.get('Sex'),
                date_of_birth=fields.get(
                    'Date of Birth') if fields.get('Date of Birth') else None,
                status=fields.get('Status'),
                street_address=fields.get('Street Address'),
                subdistrict=fields.get('Subdistrict'),
                district=fields.get('District'),
                province=fields.get('Province'),
                postal_code=fields.get('Postal Code'),
                request_datetime=datetime.datetime.fromisoformat(
                    f"{fields.get('Request Datetime')[:-1]}+00:00").astimezone(TIMEZONE),
                channel=CHANNEL_NAME,
                covid_test_document_image_url=fields.get('Covid Test Document Image')[0].get(
                    'url') if fields.get('Covid Test Document Image') else None,
                covid_test_location_type=fields.get('Covid Test Location Type'),
                covid_test_location_name=fields.get('Covid Test Location Name'),
                covid_test_date=fields.get(
                    'Covid Test Date') if fields.get('Covid Test Date') else None,
                covid_test_confirmation_date=fields.get(
                    'Covid Test Confirmation Date') if fields.get('Covid Test Confirmation Date') else None,
                symptoms=fields.get('Symptoms', []),
                other_symptoms=fields.get('Other Symptoms'),
                care_status=fields.get('Care Status'),
                care_provider_name=fields.get('Care Provider Name'),
                last_care_status_change_datetime=datetime.datetime.fromisoformat(f"{fields.get('Last Care Status Change Datetime')[:-1]}+00:00").astimezone(
                    TIMEZONE) if fields.get('Last Care Status Change Datetime') else None,
                location_latitude=fields.get('Location Latitude'),
                location_longitude=fields.get('Location Longitude'),
                caretaker_first_name=fields.get('Caretaker First Name'),
                caretaker_last_name=fields.get('Caretaker Last Name'),
                caretaker_email=fields.get('Caretaker Email'),
                caretaker_phone_number=phonenumbers.format_number(phonenumbers.parse(
                    fields.get('Caretaker Phone Number'), "TH"), phonenumbers.PhoneNumberFormat.E164),
                caretaker_relationship=fields.get('Caretaker Relationship'),
                checker=fields.get('Checker'),
                note=fields.get('Note'),
                last_status_change_datetime=datetime.datetime.fromisoformat(f"{fields.get('Last Status Change Datetime')[:-1]}+00:00").astimezone(
                    TIMEZONE) if fields.get('Last Status Change Datetime') else None
            ))
        except ValidationError as e:
            logging.error(
                'A record was dropped due to a Validation error', exc_info=e)
        except AttributeError as e:
            logging.error('A record was dropped due to an Attribute error', exc_info=e)
        except phonenumbers.NumberParseException as e:
            logging.error('A record was dropped due to an NumberParse exception', exc_info=e)

    if len(records) - len(response_data) > 0:
        logging.warn(
            f"A total of {len(records) - len(response_data)} was unable to be created.")
    return {
        'data': response_data
    }


@app.post("/care_provided_report")
def report_provided_care(care_provided_report: List[CareProvidedReport], api_key: APIKey = Depends(get_api_key)):
    if care_provided_report:
        reports = [] + care_provided_report

        matched_records = get_citizen_id_matched_airtable_records([report.citizen_id for report in reports])

        records_to_be_updated = []
        skipped_reports = []
        updated_reports = []

        for report in care_provided_report:
            citizen_id = hyphenate_citizen_id(report.citizen_id)
            care_provider_name = report.care_provider_name
            id_matched_records = list(filter(lambda record: record.get(
                'fields').get('Citizen ID') == citizen_id, matched_records))

            if len(list(filter(lambda rp: rp.citizen_id == report.citizen_id, care_provided_report))) != 1:
                skipped_reports.append(report.dict())
                continue
            if len(id_matched_records) == 1:
                updated_reports.append(report.dict())
            else:
                skipped_reports.append(report.dict())

            for record in id_matched_records:
                records_to_be_updated.append({
                    'id': record.get('id'),
                    'fields': {
                        'Care Status': 'PROVIDED',
                        'Care Provider Name': care_provider_name,
                        'Note': f"Update care status to PROVIDED by {care_provider_name} via API-SHIM on {datetime.datetime.now().astimezone(TIMEZONE).isoformat()}\n" +
                                record.get('fields').get('Note', '')
                    }
                })

        processed_count = 0
        retry_count = 0
        skipped_count = 0
        updated_records = []

        for i in range(0, len(records_to_be_updated), 10):
            time.sleep(AIRTABLE_REQUEST_DELAY)
            working_records = records_to_be_updated[i:i + 10]

            if retry_count > 5:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                    detail="Unable to reach backend, possible case of partial update, please retry.")

            response = requests.patch(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER,
                                      json={'records': working_records})

            if response.status_code != requests.codes.OK:
                retry_count += 1
                i -= 10
            else:
                retry_count = 0
                updated_records += working_records

        if skipped_count > 0:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Unable to reach backend, possible case of partial update, please retry.")

        return JSONResponse(content={'skipped': skipped_reports, 'updated': updated_reports},
                            status_code=status.HTTP_200_OK if len(skipped_reports) == 0
                            else status.HTTP_207_MULTI_STATUS)

    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

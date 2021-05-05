import datetime
import decimal
import logging
import os
import sys
import time
from enum import Enum
from typing import Dict, List, Optional, Union

import dotenv
import phonenumbers
import requests
from backports.datetime_fromisoformat import MonkeyPatch
from fastapi import FastAPI, Query, Request, Security
from fastapi.exceptions import HTTPException
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.models import APIKey
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.security.api_key import APIKeyCookie, APIKeyHeader, APIKeyQuery
from phonenumbers import NumberParseException
from pydantic import (BaseModel, EmailStr, Field, HttpUrl, ValidationError,
                      constr)
from pydantic.fields import Field
from starlette import status
from starlette.responses import JSONResponse, RedirectResponse, Response

MonkeyPatch.patch_fromisoformat()

dotenv.load_dotenv()
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = "Care%20Requests"
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_AUTH_HEADER = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

TIMEZONE = datetime.timezone(datetime.timedelta(hours=7))
REQUEST_DELAY = 0.5

TRUSTED_KEYS = []

if os.environ.get('BMA_API_KEY'):
    TRUSTED_KEYS.append(os.environ.get('BMA_API_KEY'))

CHANNEL_NAME = 'BKKCOVID19CONNECT'

API_KEY_NAME = 'token'

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_cookie = APIKeyCookie(name=API_KEY_NAME, auto_error=False)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def get_api_key(api_key_cookie: str = Security(api_key_cookie),
                      api_key_header: str = Security(api_key_header),
                      api_key_query: str = Security(api_key_query)):
    if api_key_cookie in TRUSTED_KEYS:
        return api_key_cookie
    elif api_key_header in TRUSTED_KEYS:
        return api_key_header
    elif api_key_query in TRUSTED_KEYS:
        return api_key_query
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )


class Channel(str, Enum):
    BKKCOVID19CONNECT = "BKKCOVID19CONNECT"


class CovidTestLocationType(str, Enum):
    PUBLIC_HEALTH_CENTER = "PUBLIC_HEALTH_CENTER"
    PROACTIVE_OR_MOBILE = "PROACTIVE_OR_MOBILE"
    BMA_HOSPITAL = "BMA_HOSPITAL"
    PUBLIC_HOSPITAL = "PUBLIC_HOSPITAL"
    PRIVATE_HOSPITAL = "PRIVATE_HOSPITAL"


class Sex(str, Enum):
    FEMALE = "FEMALE"
    MALE = "MALE"


class Symptom(str, Enum):
    FEVER = "FEVER"
    COUGH = "COUGH"
    HEMOPTYSIS = "HEMOPTYSIS"
    DYSPNEA = "DYSPNEA"
    ORTHOPNEA = "ORTHOPNEA"


class RequestStatus(str, Enum):
    UNCONTACTED = "UNCONTACTED"
    WORKING = "WORKING"
    FINISHED = "FINISHED"
    NOT_COMPATIBLE = "NOT_COMPATIBLE"


class CareStatus(str, Enum):
    NOT_SEEKING = "NOT_SEEKING"
    SEEKING = "SEEKING"
    PROVIDED = "PROVIDED"


class CareRequest(BaseModel):
    citizen_id: constr(regex=r'^\d{13}$')
    first_name: str
    last_name: str
    phone_number: str
    email: Optional[EmailStr]
    sex: Sex
    date_of_birth: datetime.date
    status: RequestStatus = Field(..., description='''
        - UNCONTACTED: ยังไม่ได้ติดต่อ
        - WORKING: กำลังติดต่อ
        - FINISHED: ติดต่อและยืนยันข้อมูลเรียบร้อยแล้ว
        - NOT_COMPATIBLE: ข้อมูลที่ไม่ใช้งาน (ข้อมูลทดสอบหรือข้อมูลเสีย)
    ''')
    street_address: str
    subdistrict: str
    district: str
    province: str
    postal_code: constr(regex=r'^\d{5}$')
    request_datetime: datetime.datetime
    channel: Channel
    covid_test_document_image_url: Optional[HttpUrl]
    covid_test_location_type: CovidTestLocationType = Field(..., description='''
        - PUBLIC_HEALTH_CENTER: ศูนย์บริการสาธารณสุข
        - PROACTIVE_OR_MOBILE: ตรวจเชิงรุกหรือรถตรวจ
        - BMA_HOSPITAL: โรงพยาบาลในสังกัดกรุงเทพมหานคร
        - PUBLIC_HOSPITAL: โรงพยาบาลหรือหน่วยงานอื่นๆ ของรัฐบสล
        - PRIVATE_HOSPITAL: โรงพยาบาลหรือหน่วยงานอื่นๆ ของเอกชน
    ''')
    covid_test_location_name: str
    covid_test_date: datetime.date
    covid_test_confirmation_date: Optional[datetime.date]
    symptoms: List[Symptom]
    other_symptoms: Optional[str]
    care_status: CareStatus = Field(..., description='''
        - NOT_SEEKING: ไม่ต้องการเข้ารับการรักษา
        - SEEKING: ต้องการเข้ารับการรักษา
        - PROVIDED: เข้าถึงการรักษาแล้ว
    ''')
    care_provider_name: Optional[str]
    last_care_status_change_datetime: Optional[datetime.datetime]
    location_latitude: decimal.Decimal
    location_longitude: decimal.Decimal
    caretaker_first_name: str
    caretaker_last_name: str
    caretaker_email: Optional[EmailStr]
    caretaker_phone_number: str
    caretaker_relationship: str
    checker: Optional[str]
    note: Optional[str]
    last_status_change_datetime: Optional[datetime.datetime]


class CareRequestResponse(BaseModel):
    data: List[CareRequest]


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


def build_airtable_formula_chain(formula: str, expressions: List[str]) -> str:
    if len(expressions) == 0:
        return ''
    if len(expressions) == 1:
        return expressions[0]
    return f"{formula}({expressions[0]},{build_airtable_formula_chain(formula, expressions[1:])})"


def build_airtable_datetime_expression(_datetime: datetime.datetime, unit_specifier: str = "ms") -> str:
    # Check logic if datetime is aware from
    # https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive
    if _datetime.tzinfo is None or _datetime.tzinfo.utcoffset(_datetime) is None:
        _datetime = _datetime.replace(tzinfo=TIMEZONE)
    return f"DATETIME_PARSE(\"{_datetime.strftime('%Y %m %d %H %M %S %z')}\",\"YYYY MM DD HH mm ss ZZ\",\"ms\")"


def get_airtable_records(params) -> List:
    response = requests.get(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER, params=params)
    results = response.json()
    records = results.get('records', [])
    # Loop to handle multi-page query
    while results.get('offset'):
        time.sleep(REQUEST_DELAY)
        response = requests.get(
            AIRTABLE_BASE_URL,
            headers=AIRTABLE_AUTH_HEADER,
            params={'offset': results.get('offset')})
        logging.warn(
            f'Executing multi-page query... ' +
            f'Currently on page {len(records) // 100}. Got {len(records)} records so far.')
        results = response.json()
        records += results['records']
    return records


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
            f"{build_airtable_datetime_expression(last_status_change_since)}) >= 0")

    if last_status_change_until:
        filter_by_formulas.append(
            "DATETIME_DIFF({Last Status Change Datetime}," +
            f"{build_airtable_datetime_expression(last_status_change_until)}) < 0")

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
        except NumberParseException as e:
            logging.error('A record was dropped due to an NumberParse exception', exc_info=e)

    if len(records) - len(response_data) > 0:
        logging.warn(
            f"A total of {len(records) - len(response_data)} was unable to be created.")
    return {
        'data': response_data
    }


class CareProvidedReport(BaseModel):
    citizen_id: constr(regex=r'^\d{13}$')
    care_provider_name: str


@app.post("/care_provided_report")
def report_provided_care(care_provided_report: List[CareProvidedReport], api_key: APIKey = Depends(get_api_key)):

    def hyphenate_citizen_id(unhyphenated_id: str) -> str:
        return (f"{unhyphenated_id[0]}-{unhyphenated_id[1:5]}-{unhyphenated_id[5:10]}" +
                f"-{unhyphenated_id[10:12]}-{unhyphenated_id[12]}")

    if care_provided_report:
        reports = [] + care_provided_report

        matched_records = []

        while len(reports) > 0:
            working_reports = reports[:100]
            reports = reports[100:]

            citizen_id_filter_str = build_airtable_formula_chain('OR', list(set(
                map(lambda report: f"{{Citizen ID}}=\"{hyphenate_citizen_id(report.citizen_id)}\"", working_reports))))
            params = [
                ('fields[]', 'Citizen ID'),
                ('fields[]', 'Care Status'),
                ('fields[]', 'Note'),
                ('filterByFormula', build_airtable_formula_chain('AND', [
                    citizen_id_filter_str,
                    # Rejecting to update requests older than 21 days
                    f"DATETIME_DIFF({build_airtable_datetime_expression(datetime.datetime.now(), unit_specifier='d')}," +
                    '{Request Datetime}) > 21',
                    '{Status}="FINISHED"'
                ])),
                ('sort[0][field]', 'Request Datetime'),
                ('sort[0][direction]', 'asc'),
            ]
            records = get_airtable_records(params=params)
            matched_records += records

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

        while processed_count < len(records_to_be_updated):
            time.sleep(REQUEST_DELAY)
            working_records = records_to_be_updated[processed_count:processed_count + 10]
            if retry_count > 5:
                skipped_count += 10
                processed_count += 10
            response = requests.patch(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER,
                                      json={'records': working_records})
            if response.status_code == requests.codes.OK:
                updated_records += working_records
                processed_count += 10
                retry_count = 0
            else:
                retry_count += 1

        if skipped_count > 0:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Unable to reach backend, possible case of partial update, please retry.")

        return JSONResponse(content={'skipped': skipped_reports, 'updated': updated_reports},
                            status_code=status.HTTP_200_OK if len(skipped_reports) == 0
                            else status.HTTP_207_MULTI_STATUS)

    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

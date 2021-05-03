import datetime
import decimal
import logging
import os
import sys
import time
from enum import Enum
from typing import List, Optional, Union

import dotenv
import phonenumbers
import requests
from backports.datetime_fromisoformat import MonkeyPatch
from fastapi import FastAPI, Query, Security
from fastapi.exceptions import HTTPException
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.models import APIKey
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.security.api_key import APIKeyCookie, APIKeyHeader, APIKeyQuery
from pydantic import BaseModel, EmailStr, HttpUrl, ValidationError
from starlette import status
from starlette.responses import JSONResponse, RedirectResponse

MonkeyPatch.patch_fromisoformat()

dotenv.load_dotenv()
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = "app6QQHLp7ui8gEae"
AIRTABLE_TABLE_NAME = "Care%20Requests"
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_AUTH_HEADER = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

TRUSTED_KEYS = []

if os.environ.get('BMA_API_KEY'):
    TRUSTED_KEYS.append(os.environ.get('BMA_API_KEY'))

CHANNEL_NAME = 'BKKCOVID19CONNECT'

API_KEY_NAME = 'token'

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_cookie = APIKeyCookie(name=API_KEY_NAME, auto_error=False)

COOKIE_DOMAIN = "bkkcovid19connect-api.vistec.ist"

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


class Request(BaseModel):
    citizen_id: str
    first_name: str
    last_name: str
    phone_number: str
    email: Optional[EmailStr]
    sex: Sex
    date_of_birth: datetime.date
    status: RequestStatus
    street_address: str
    subdistrict: str
    district: str
    province: str
    postal_code: str
    request_datetime: datetime.datetime
    channel: Channel
    covid_test_document_image_url: Optional[HttpUrl]
    covid_test_location_type: CovidTestLocationType
    covid_test_location_name: str
    covid_test_date: datetime.date
    covid_test_confirmation_date: Optional[datetime.date]
    symptoms: List[Symptom]
    other_symptoms: Optional[str]
    care_status: CareStatus
    care_provider_name: Optional[str]
    last_care_status_change_datetime: Optional[datetime.datetime]
    location_latitude: decimal.Decimal
    location_longitude: decimal.Decimal
    caretaker_first_name: str
    caretaker_last_name: str
    caretaker_phone_number: str
    caretaker_relationship: str
    checker: Optional[str]
    note: Optional[str]
    last_status_change_datetime: Optional[datetime.datetime]


class RequestRead(Request):
    concatenated_address: str
    location: str
    transfer_status: int

    @property
    def location(self) -> str:
        return f"{self.location_latitude},{self.location_longitude}"

    @property
    def concatenated_address(self) -> str:
        return f"{self.street_address} {self.subdistrct} {self.district} {self.province} {self.postal_code}"

    @property
    def transfer_status(self) -> int:
        return


class Response(BaseModel):
    data: List[Request]


@app.get("/openapi.json", tags=["documentation"])
async def get_open_api_endpoint(api_key: APIKey = Depends(get_api_key)):
    response = JSONResponse(
        get_openapi(title='BKKCOVID19CONNECT API', version=1, routes=app.routes)
    )
    return response


@app.get("/docs", tags=["documentation"])
async def get_documentation(api_key: APIKey = Depends(get_api_key)):
    response = get_swagger_ui_html(
        openapi_url="/openapi.json", title="API docs")
    response.set_cookie(
        API_KEY_NAME,
        value=api_key,
        domain=COOKIE_DOMAIN,
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response


@app.get("/redoc", tags=["documentation"])
async def get_redoc(api_key: APIKey = Depends(get_api_key)):
    response = get_redoc_html(openapi_url="/openapi.json", title="API docs")
    response.set_cookie(
        API_KEY_NAME,
        value=api_key,
        domain=COOKIE_DOMAIN,
        httponly=True,
        max_age=1800,
        expires=1800,
    )
    return response


@app.get("/logout")
async def route_logout_and_remove_cookie():
    response = RedirectResponse(url="/")
    response.delete_cookie(API_KEY_NAME, domain=COOKIE_DOMAIN)
    return response


@app.get("/requests", response_model=Response)
async def read_requests(last_status_change_since: Optional[datetime.datetime] = Query(None),
                        last_status_change_until: Optional[datetime.datetime] = Query(None),
                        status: Optional[List[RequestStatus]] = Query(None),
                        api_key: APIKey = Depends(get_api_key)):

    filter_by_formulas = []

    if last_status_change_since:
        if last_status_change_since.tzinfo is None or last_status_change_since.tzinfo.utcoffset(last_status_change_since) is None:
            last_status_change_since = last_status_change_since.replace(
                tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
        filter_by_formulas.append(
            f"DATETIME_DIFF({{Last Status Change Datetime}},DATETIME_PARSE(\"{last_status_change_since.strftime('%Y %m %d %H %M %S %z')}\",\"YYYY MM DD HH mm ss ZZ\",\"ms\")) >= 0")

    if last_status_change_until:
        if last_status_change_until.tzinfo is None or last_status_change_until.tzinfo.utcoffset(last_status_change_until) is None:
            last_status_change_until = last_status_change_until.replace(
                tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
        filter_by_formulas.append(
            f"DATETIME_DIFF({{Last Status Change Datetime}},DATETIME_PARSE(\"{last_status_change_until.strftime('%Y %m %d %H %M %S %z')}\",\"YYYY MM DD HH mm ss ZZ\",\"ms\")) < 0")

    if status and len(status) > 0:
        status_filter_param = f"{{Status}}=\"{status[0]}\""
        for _status in status[1:]:
            status_filter_param = f"OR({status_filter_param},{{Status}}=\"{_status}\")"
        filter_by_formulas.append(status_filter_param)

    params = {
        'pageSize': 100,
    }

    if len(filter_by_formulas) > 0:
        filter_by_formula_param = f"{filter_by_formulas[0]}"
        for formula in filter_by_formulas[1:]:
            filter_by_formula_param = f"AND({filter_by_formula_param},{formula})"
        params['filterByFormula'] = filter_by_formula_param

    response = requests.get(
        AIRTABLE_BASE_URL,
        headers=AIRTABLE_AUTH_HEADER,
        params=params)
    results = response.json()
    records = results.get('records', [])
    response_data = []

    while results.get('offset'):
        time.sleep(0.8)
        response = requests.get(
            AIRTABLE_BASE_URL,
            headers=AIRTABLE_AUTH_HEADER,
            params={
                **{'offset': results.get('offset')
                   }
            })
        logging.warn(
            f'Executing multi-page query... ' +
            f'Currently on page {len(records) // 100}. Got {len(records)} records so far.')
        results = response.json()
        records += results['records']

    for record in records:
        fields = record.get('fields', [])
        try:
            response_data.append(Request(
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
                    f"{fields.get('Request Datetime')[:-1]}+00:00").astimezone(datetime.timezone(datetime.timedelta(hours=7))),
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
                    datetime.timezone(datetime.timedelta(hours=7))) if fields.get('Last Care Status Change Datetime') else None,
                location_latitude=fields.get('Location Latitude'),
                location_longitude=fields.get('Location Longitude'),
                caretaker_first_name=fields.get('Caretaker First Name'),
                caretaker_last_name=fields.get('Caretaker Last Name'),
                caretaker_phone_number=phonenumbers.format_number(phonenumbers.parse(
                    fields.get('Caretaker Phone Number'), "TH"), phonenumbers.PhoneNumberFormat.E164),
                caretaker_relationship=fields.get('Caretaker Relationship'),
                checker=fields.get('Checker'),
                note=fields.get('Note'),
                last_status_change_datetime=datetime.datetime.fromisoformat(f"{fields.get('Last Status Change Datetime')[:-1]}+00:00").astimezone(
                    datetime.timezone(datetime.timedelta(hours=7))) if fields.get('Last Status Change Datetime') else None
            ))
        except ValidationError as e:
            logging.error(
                'A record was dropped due to a Validation error', exc_info=e)
        except AttributeError as e:
            logging.error('A record was dropped due to an Attribute error', exc_info=e)
    if len(records) - len(response_data) > 0:
        logging.warn(
            f"A total of {len(records) - len(response_data)} was dropped.")
    return {
        'data': response_data
    }

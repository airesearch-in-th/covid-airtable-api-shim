import datetime
import decimal
import logging
import os
import sys
from enum import Enum
from typing import List, Optional, Union

import dotenv
import requests
import phonenumbers
from backports.datetime_fromisoformat import MonkeyPatch
from fastapi import FastAPI, Security, Query
from fastapi.exceptions import HTTPException
from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError
from starlette import status
from fastapi.security.api_key import APIKeyCookie, APIKeyHeader, APIKeyQuery
from starlette.responses import JSONResponse, RedirectResponse
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.openapi.models import APIKey
from fastapi.openapi.docs import get_swagger_ui_html

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

COOKIE_DOMAIN = "127.0.0.1"

app = FastAPI()


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
    HOSPITALIZED = "HOSPITALIZED"
    NOT_COMPATIBLE = "NOT_COMPATIBLE"


class Request(BaseModel):
    citizen_id: str
    first_name: str
    last_name: str
    phone_number: str
    email: Optional[str]
    sex: Sex
    date_of_birth: datetime.date
    status: RequestStatus
    # concatenated_address: str
    street_address: str
    subdistrict: str
    district: str
    province: str
    postal_code: str
    request_datetime: datetime.datetime
    channel: Channel
    has_covid_test_document: bool
    covid_test_result_image_url: Optional[str]
    covid_test_location_type: CovidTestLocationType
    covid_test_location_name: str
    covid_test_date: datetime.date
    covid_test_confirmation_date: Optional[datetime.date]
    symptoms: List[Symptom]
    other_symptoms: Optional[str]
    # is_looking_for_care: bool
    # is_given_care: bool
    care_location: Optional[str]
    care_given_on: Optional[datetime.datetime]
    # location: str
    location_latitude: decimal.Decimal
    location_longitude: decimal.Decimal
    caretaker_first_name: str
    caretaker_last_name: str
    caretaker_phone_number: str
    caretaker_relationship: str
    checker: Optional[str]
    note: Optional[str]
    last_status_change_datetime: Optional[datetime.datetime]

    def location(self):
        return f"{self.location_latitude},{self.location_longitude}"

    def concatenated_address(self):
        return f"{self.street_address} {self.subdistrct} {self.district} {self.province} {self.postal_code}"


class Response(BaseModel):
    data: List[Request]
    offset: Optional[str]


@app.get("/openapi.json", tags=["documentation"])
async def get_open_api_endpoint(api_key: APIKey = Depends(get_api_key)):
    response = JSONResponse(
        get_openapi(title='BKKCOVID19CONNECT API', version=1, routes=app.routes)
    )
    return response


@app.get("/documentation", tags=["documentation"])
async def get_documentation(api_key: APIKey = Depends(get_api_key)):
    response = get_swagger_ui_html(openapi_url="/openapi.json", title="API docs")
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
async def read_requests(last_status_change_since: Optional[datetime.datetime] = None,
                        last_status_change_until: Optional[datetime.datetime] = None,
                        status: Optional[List[RequestStatus]] = Query([RequestStatus.FINISHED]),
                        page_size: Optional[int] = 100,
                        offset: Optional[str] = None, limit: Optional[int] = sys.maxsize, api_key: APIKey = Depends(get_api_key)):

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

    if len(status) > 0:
        status_filter_param = f"{{Status}}=\"{status[0]}\""
        for _status in status[1:]:
            status_filter_param = f"OR({status_filter_param},{{Status}}=\"{_status}\")"
        filter_by_formulas.append(status_filter_param)

    params = {
        'maxRecords': limit,
        'pageSize': page_size,
    }

    if len(filter_by_formulas) > 0:
        filter_by_formula_param = f"{filter_by_formulas[0]}"
        for formula in filter_by_formulas[1:]:
            filter_by_formula_param = f"AND({filter_by_formula_param},{formula})"
        params['filterByFormula'] = filter_by_formula_param

    if offset:
        params['offset'] = offset

    response = requests.get(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER, params=params)
    results = response.json()

    response_data = []
    for records in results['records']:
        fields = records['fields']
        try:
            response_data.append(Request(
                citizen_id=fields.get('Citizen ID').replace("-", ""),
                first_name=fields.get('First Name'),
                last_name=fields.get('Last Name'),
                phone_number=phonenumbers.format_number(phonenumbers.parse(
                    fields.get('Phone Number'), "TH"), phonenumbers.PhoneNumberFormat.E164),
                email=fields.get('Email'),
                sex=fields.get('Sex'),
                date_of_birth=fields.get(
                    'Date of Birth') if fields.get('Date of Birth') else None,
                status=fields.get('Status'),
                # concatenated_address=f"{fields.get('Street Address')} {fields.get('Subdistrict')} {fields.get('District')} {fields.get('Province')} {fields.get('Postal Code')}",
                street_address=fields.get('Street Address'),
                subdistrict=fields.get('Subdistrict'),
                district=fields.get('District'),
                province=fields.get('Province'),
                postal_code=fields.get('Postal Code'),
                request_datetime=datetime.datetime.fromisoformat(
                    f"{fields.get('Request Datetime')[:-1]}+00:00").astimezone(datetime.timezone(datetime.timedelta(hours=7))),
                channel=CHANNEL_NAME,
                has_covid_test_document=True if fields.get('Has Covid Test Document') and fields.get(
                    'Has Covid Test Document') == 'มี' else False,
                covid_test_document_image_url=fields.get('Covid Test Document Image')[0].get(
                    'url') if fields.get('Covid Test Document Image') else None,
                covid_test_location_type=fields.get('Covid Test Location Type'),
                covid_test_location_name=fields.get('Covid Test Location Name'),
                covid_test_date=fields.get(
                    'Covid Test Date') if fields.get('Covid Test Date') else None,
                covid_test_confirmation_date=fields.get(
                    'Covid Test Confirmation Date') if fields.get('Covid Test Confirmation Date') else None,
                symptoms=fields.get('Symptoms', []),
                other_symptoms=fields.get('Other Symptoms', ''),
                is_looking_for_care=fields.get('Is Looking for Care'),
                # is_given_care=fields.get('Is Given Care'),
                # care_location=fields.get('Care Location'),
                # care_given_on=fields.get('Care Given on') if fields.get('Care Given on') else None,
                # location=f"{fields.get('Location Latitude')},{fields.get('Location Longitude')}" if fields.get(
                #     'Location Latitude') and fields.get('Location Longitude') else None,
                location_latitude=fields.get('Location Latitude'),
                location_longitude=fields.get('Location Longitude'),
                caretaker_first_name=fields.get('Caretaker First Name'),
                caretaker_last_name=fields.get('Caretaker Last Name'),
                caretaker_phone_number=phonenumbers.format_number(phonenumbers.parse(
                    fields.get('Caretaker Phone Number'), "TH"), phonenumbers.PhoneNumberFormat.E164),
                caretaker_relationship=fields.get('Caretaker Relationship'),
                checker=fields.get('Checker', ''),
                note=fields.get('Note', ''),
                last_status_change_datetime=datetime.datetime.fromisoformat(f"{fields.get('Last Status Change Datetime')[:-1]}+00:00").astimezone(datetime.timezone(datetime.timedelta(hours=7))) if fields.get(
                    'Last Status Change Datetime') else None
            ))
        except ValidationError as e:
            logging.error('A record was dropped due to a Validation error', exc_info=e)
    if len(results['records']) - len(response_data) > 0:
        logging.warn(f"A total of {len(results['records']) - len(response_data)} was dropped due to a validation error")
    return {
        'offset': 0 if not results.get('offset') else results.get('offset'),
        'data': response_data
    }


@ app.post("/requests")
async def create_request(request: Request):
    pass


@ app.get("/requests/{request_id}")
async def read_request():
    pass

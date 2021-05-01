import datetime
import decimal
import logging
import os
import sys
from enum import Enum
from typing import List, Optional

import dotenv
import requests
from backports.datetime_fromisoformat import MonkeyPatch
from fastapi import FastAPI
from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError

MonkeyPatch.patch_fromisoformat()

dotenv.load_dotenv()
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = "app6QQHLp7ui8gEae"
AIRTABLE_TABLE_NAME = "Care%20Requests"
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_AUTH_HEADER = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

CHANNEL_NAME = 'BKKCOVID19CONNECT'

app = FastAPI()


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
    request_date: datetime.datetime
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

    def location(self):
        return f"{self.location_latitude},{self.location_longitude}"

    def concatenated_address(self):
        return f"{self.street_address} {self.subdistrct} {self.district} {self.province} {self.postal_code}"


@app.get("/requests", response_model=List[Request])
async def read_requests(since: Optional[datetime.datetime] = None, until: Optional[datetime.datetime] = None,
                        skip: Optional[int] = 0, limit: Optional[int] = sys.maxsize):
    params = {
        'maxRecords': limit + skip
    }
    results = requests.get(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER, params=params).json()
    response_data = []
    for records in results['records']:
        fields = records['fields']
        try:
            response_data.append(Request(
                citizen_id=fields.get('Citizen ID'),
                first_name=fields.get('First Name'),
                last_name=fields.get('Last Name'),
                phone_number=fields.get('Phone Number'),
                email=fields.get('Email'),
                sex=fields.get('Sex'),
                date_of_birth=datetime.date.fromisoformat(fields.get(
                    'Date of Birth')) if fields.get('Date of Birth') else None,
                status=fields.get('Status'),
                # concatenated_address=f"{fields.get('Street Address')} {fields.get('Subdistrict')} {fields.get('District')} {fields.get('Province')} {fields.get('Postal Code')}",
                street_address=fields.get('Street Address'),
                subdistrict=fields.get('Subdistrict'),
                district=fields.get('District'),
                province=fields.get('Province'),
                postal_code=fields.get('Postal Code'),
                request_date=fields.get('Request Date'),
                channel=CHANNEL_NAME,
                has_covid_test_document=True if fields.get('Has Covid Test Document') and fields.get(
                    'Has Covid Test Document') == 'มี' else False,
                covid_test_document_image_url=fields.get('Covid Test Document Image')[0].get(
                    'url') if fields.get('Covid Test Document Image') else None,
                covid_test_location_type=fields.get('Covid Test Location Type'),
                covid_test_location_name=fields.get('Covid Test Location Name'),
                covid_test_date=datetime.date.fromisoformat(fields.get(
                    'Covid Test Date')) if fields.get('Covid Test Date') else None,
                covid_test_confirmation_date=datetime.date.fromisoformat(fields.get(
                    'Covid Test Confirmation Date')) if fields.get('Covid Test Confirmation Date') else None,
                symptoms=fields.get('Symptoms', []),
                other_symptoms=fields.get('Other Symptoms', ''),
                is_looking_for_care=fields.get('Is Looking for Care'),
                # is_given_care=fields.get('Is Given Care'),
                # care_location=fields.get('Care Location'),
                # care_given_on=datetime.date.fromisoformat(fields.get('Care Given on')) if fields.get('Care Given on') else None,
                # location=f"{fields.get('Location Latitude')},{fields.get('Location Longitude')}" if fields.get(
                #     'Location Latitude') and fields.get('Location Longitude') else None,
                location_latitude=fields.get('Location Latitude'),
                location_longitude=fields.get('Location Longitude'),
                caretaker_first_name=fields.get('Caretaker First Name'),
                caretaker_last_name=fields.get('Caretaker Last Name'),
                caretaker_phone_number=fields.get('Caretaker Phone Number'),
                caretaker_relationship=fields.get('Caretaker Relationship'),
                checker=fields.get('Checker', ''),
                note=fields.get('Note', '')
            ))
        except ValidationError as e:
            logging.error('A record was dropped due to a Validation error', exc_info=e)
    if len(results['records']) - len(response_data) > 0:
        logging.warn(f"A total of {len(results['records']) - len(response_data)} was dropped due to a validation error")
    return response_data


@app.post("/requests")
async def create_request(request: Request):
    pass


@app.get("/requests/{request_id}")
async def read_request():
    pass

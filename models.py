
import datetime
import decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, constr


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
    symptoms_level: str
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


class CareProvidedReport(BaseModel):
    citizen_id: constr(regex=r'^\d{13}$')
    care_provider_name: str

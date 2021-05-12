import datetime
import logging
import os
import time
from typing import List

import dotenv
import requests

from utils import hyphenate_citizen_id

dotenv.load_dotenv()

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = "Care%20Requests"
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_AUTH_HEADER = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
AIRTABLE_REQUEST_DELAY = 0.5


def build_airtable_formula_chain(formula: str, expressions: List[str]) -> str:
    if len(expressions) == 0:
        return ''
    if len(expressions) == 1:
        return expressions[0]
    return f"{formula}({expressions[0]},{build_airtable_formula_chain(formula, expressions[1:])})"


def build_airtable_datetime_expression(_datetime: datetime.datetime,
                                       timezone: datetime.timezone,
                                       unit_specifier: str = "ms") -> str:
    # Check logic if datetime is aware from
    # https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive
    if _datetime.tzinfo is None or _datetime.tzinfo.utcoffset(_datetime) is None:
        _datetime = _datetime.replace(tzinfo=timezone)
    return f"DATETIME_PARSE(\"{_datetime.strftime('%Y %m %d %H %M %S %z')}\",\"YYYY MM DD HH mm ss ZZ\",\"ms\")"


def get_airtable_records(params) -> List:
    response = requests.get(AIRTABLE_BASE_URL, headers=AIRTABLE_AUTH_HEADER, params=params)
    results = response.json()
    records = results.get('records', [])
    # Loop to handle multi-page query
    while results.get('offset'):
        time.sleep(AIRTABLE_REQUEST_DELAY)
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


def get_citizen_id_matched_airtable_records(citizen_ids: List[str]) -> List:
    RECORDS_PER_REQUEST = 100
    matched_records = []

    for i in range(0, len(citizen_ids), RECORDS_PER_REQUEST):
        citizen_id_filter_str = build_airtable_formula_chain('OR', list(set(
            map(lambda citizen_id: f"{{Citizen ID}}=\"{hyphenate_citizen_id(citizen_id)}\"",
                citizen_ids[i:i + RECORDS_PER_REQUEST]))))
        datetime_expression = build_airtable_datetime_expression(datetime.datetime.now().astimezone(
            datetime.timezone(datetime.timedelta(hours=7))),
            datetime.timezone(datetime.timedelta(hours=7)), unit_specifier='d')
        params = [
            ('fields[]', 'Citizen ID'),
            ('fields[]', 'Care Status'),
            ('fields[]', 'Note'),
            ('filterByFormula', build_airtable_formula_chain('AND', [
                citizen_id_filter_str,
                # Rejecting to update requests older than 21 days
                f"DATETIME_DIFF({datetime_expression}," +
                '{Request Datetime}) > 21',
                '{Status}="FINISHED"'
            ])),
            ('sort[0][field]', 'Request Datetime'),
            ('sort[0][direction]', 'asc'),
        ]
        records = get_airtable_records(params=params)
        matched_records += records

    return matched_records

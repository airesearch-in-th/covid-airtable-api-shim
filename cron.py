import datetime
import json
import logging
import os
from typing import List

import dotenv
import requests
from pydantic import ValidationError
from starlette import status

from main import (CareProvidedReport, build_airtable_datetime_expression,
                  build_airtable_formula_chain, get_airtable_records,
                  hyphenate_citizen_id, report_provided_care)

dotenv.load_dotenv()

CMC_API_BASE_URL = 'http://cmc.bangkok.go.th/cvformapi/api/nawaminsent'
CMC_API_KEY = os.environ.get('CMC_API_KEY')


def poll_for_new_care_status_update():
    if not CMC_API_KEY:
        raise ConnectionAbortedError('Unable to retrieve API key')

    response = requests.get(CMC_API_BASE_URL, params={'token': CMC_API_KEY})
    rows = response.json()

    reports: List[CareProvidedReport] = []

    skipped_rows = []

    for row in rows:
        try:
            if row.get('transfer_status') != '1':
                skipped_rows.append(row)
                continue
            reports.append(CareProvidedReport(citizen_id=row.get('citizen_id'),
                           care_provider_name=row.get('hos_name')))
        except ValidationError as e:
            skipped_rows.append(row)
            logging.error(f'A row was dropped due to a Validation error ({row})', exc_info=e)

    if len(skipped_rows) > 0:
        logging.warn(f"A total of {len(skipped_rows)} rows was unable to be created.")

    response = report_provided_care(reports)

    if response.status_code // 100 != 2:
        logging.error(f'HTTP Response is not 200: got status {response.status_code}')
        raise ConnectionError(f'HTTP Response is not 200: got status {response.status_code}')

    if response.status_code == status.HTTP_207_MULTI_STATUS:
        logging.warn(f'Partial update, skipped records:\n{json.loads(response.body)}')
    logging.warn(f'Updated {len(rows) - len(skipped_rows)} records to Airtable.')


if __name__ == '__main__':
    poll_for_new_care_status_update()

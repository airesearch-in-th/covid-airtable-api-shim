import os

import dotenv
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyCookie, APIKeyHeader, APIKeyQuery
from starlette import status

dotenv.load_dotenv()

TRUSTED_KEYS = []

if os.environ.get('BMA_API_KEY'):
    TRUSTED_KEYS.append(os.environ.get('BMA_API_KEY'))

API_KEY_NAME = 'token'

api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_cookie = APIKeyCookie(name=API_KEY_NAME, auto_error=False)


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

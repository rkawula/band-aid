import time
import jwt
from database_models.models import User
from jwt.exceptions import DecodeError
from decouple import config

JWT_SECRET = config("JWT_SECRET")
JWT_ALGORITHM = config("JWT_ALGORITHM")


def sign_jwt(user: User):
    payload = {
        "user_id": user.id,
        # 30 days
        "expiration": time.time() + 30 * 24 * 60 * 60 * 1000
    }
    token = jwt.encode(payload, JWT_SECRET)
    return token


def decode_jwt(token: str):
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return decoded_token if decoded_token['expiration'] >= time.time() else None
    except DecodeError:
        return {}

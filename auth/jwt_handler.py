import time
import jwt
from fastapi import HTTPException

from database_models.models import User
from decouple import config

JWT_SECRET = config("jwt_secret")
JWT_ALGORITHM = config("jwt_algorithm")


def generate_token(token: str):
    return {
        "access token": token
    }


def sign_jwt(user: User):
    payload = {
        "user_id": user.id,
        "expiration": time.time() + 30 * 24 * 60 * 60 * 1000
    }
    token = jwt.encode(payload, JWT_SECRET)
    return token


def decode_jwt(token: str):
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return decoded_token if decoded_token['expiration'] >= time.time() else None
    except:
        return {}

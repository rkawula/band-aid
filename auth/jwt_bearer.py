from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth.jwt_handler import decode_jwt


class JwtBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super(JwtBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super(JwtBearer, self).__call__(request)
        if credentials:
            if not (credentials.scheme == "Bearer" and self._verify_jwt(credentials.credentials)):
                raise HTTPException(status_code=401, detail="Invalid token")
            return credentials.credentials
        else:
            raise HTTPException(status_code=400, detail="No credentials present")

    def _verify_jwt(self, token: str) -> bool:
        payload = decode_jwt(token)
        if payload and payload is not {}:
            return True
        return False


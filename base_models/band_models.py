from pydantic import BaseModel

class PostBandRequest(BaseModel):
    name: str
    location: str

class PostUserRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    location: str | None = None
    longitude: str | None = None
    latitude: str | None = None

class PostSendInvite(BaseModel):
    user_id:int
    band_id:int

class PostAcceptInvite(BaseModel):
    code:str

class PostUserLogin(BaseModel):
    email: str
    password: str

class JwtUser(BaseModel):
    user_id: int
    email: str | None = None

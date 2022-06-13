from pydantic import BaseModel


class PostBandRequest(BaseModel):
    id: int | None = None
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
    invite_code: str | None = None
    band_id: int | None = None


class PostSendInvite(BaseModel):
    user_id: int
    band_id: int


class PostAcceptInvite(BaseModel):
    code: str


class GetUserLogin(BaseModel):
    email: str
    password: str


class JwtUser(BaseModel):
    user_id: int | None = None
    email: str | None = None


class GetSearchRequest(BaseModel):
    name: str | None
    location: str | None
    talent: str | None

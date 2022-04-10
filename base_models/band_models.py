from pydantic import BaseModel

class PostBandRequest(BaseModel):
    name: str
    admin: str
    members: str | None = None
    location: str

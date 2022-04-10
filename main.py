from fastapi import FastAPI

from models.band import Band
from base_models.band_models import *

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/band")
async def get_band():
    return {"some": "band"}

@app.post("/band")
async def post_band(post_band_request: PostBandRequest):
    return Band(post_band_request)

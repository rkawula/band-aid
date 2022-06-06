import logging.config
import uvicorn
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from emails import Email
from base_models.band_models import (
    PostUserRequest,
    PostBandRequest,
    PostSendInvite,
    PostAcceptInvite, PostUserLogin,
    JwtUser
)
from database_models.db_connector import engine, DbSession
from database_models.models import (
    Base,
    User,
    BandMember,
    BandInvite,
    EmailVerification,
    Band
)
from auth.jwt_handler import sign_jwt, decode_jwt
from auth.jwt_bearer import JwtBearer
from sqlalchemy.orm import exc
from security.security import hash_password, verify_password
import random

# TODO make this work
logger = logging.getLogger(__name__)

app = FastAPI()


def get_database():
    try:
        db = DbSession()
        yield db
    finally:
        db.close()


def generate_code():
    chars = "ABCDEFGHJKLMNPRSTWXYZ2346789"
    code = ''.join(random.choice(chars) for i in range(8))
    return code


async def get_current_user(token: str = Depends(JwtBearer())):
    decoded = decode_jwt(token)
    user = JwtUser(user_id=decoded['user_id'])
    return user


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/band/{id}")
async def get_band(id: int, db: Session = Depends(get_database)):
    band = db.query(Band).where(Band.id == id).first()
    return band

@app.get("/bandmembers/{band_id}")
async def get_band_members(band_id: int, db: Session = Depends(get_database)):
    members = db.query(User.id, User.first_name, User.last_name).where(User.id.in_(
        db.query(BandMember.user_id).where(band_id == BandMember.band_id))).all()
    return members

@app.post("/band")
async def post_create_band(post_band_request: PostBandRequest, user: JwtUser = Depends(get_current_user),
                           db: Session = Depends(get_database)):
    band = Band(
        name=post_band_request.name,
        location=post_band_request.location
    )
    try:
        add_and_flush(db, band)
        bm = BandMember(user_id=user.user_id, band_id=band.id, admin=True)
        db.add(bm)
        db.commit()
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Unable to create band")
    return {"Success"}


@app.post("/register")
async def register_user(user_request: PostUserRequest, db: Session = Depends(get_database)):
    user_request.email = user_request.email.lower()
    dup = db.query(User).where(User.email == user_request.email).first()
    if dup:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        first_name=user_request.first_name,
        last_name=user_request.last_name,
        email=user_request.email,
        password_hash=hash_password(user_request.password),
        location=user_request.location
    )

    try:
        add_and_flush(db, user)
        try:
            code = generate_code()
            ev = EmailVerification(user_id=user.id, code=code)
            add_and_flush(db, ev)
        except exc.sa_exc.SQLAlchemyError as err:
            db.rollback()
            raise HTTPException(status_code=500, detail="Could not create verification code entry")
    except exc.sa_exc.SQLAlchemyError as err:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create user entry")
    db.commit()

    # TODO get new app password for gmail
    # mail = Email()
    # mail.send_invite_email(ev.code, user_request.email)

    # TODO redirect to login page or return JWT
    # from starlette.responses import RedirectResponse
    # response = RedirectResponse(url='/login')
    return sign_jwt(user)


def add_and_flush(db, row):
    db.add(row)
    db.flush()


@app.get("/user/{id}")
async def get_user(id: int, db: Session = Depends(get_database)):
    try:
        user = db.query(User).where(User.id == id).first()
    except exc.sa_exc.SQLAlchemyError as err:
        raise HTTPException(status_code=500, detail="Could get user")
    return user


@app.get("/verify/{code}")
async def verify_user_email(code: str, db: Session = Depends(get_database)):
    email_verification = db.query(EmailVerification).where(EmailVerification.code == code).first()
    if email_verification:
        user = db.query(User).where(User.id == email_verification.id).first()
        user.email_verified = True
        db.delete(email_verification)
        db.commit()
    return "Success"


@app.post("/accept_invite", dependencies=[Depends(JwtBearer())])
async def accept_invite(pai: PostAcceptInvite, db: Session = Depends(get_database)):
    pass


@app.post("/send_invite", dependencies=[Depends(JwtBearer())])
async def send_invite(psi: PostSendInvite, db: Session = Depends(get_database), user: JwtUser = Depends(get_current_user)):
    try:
        band_member = db.query(BandMember).where(BandMember.user_id == user.user_id). \
            where(BandMember.band_id == psi.band_id).first()
        if not band_member.admin:
            raise HTTPException(status_code=400, detail="Not admin")
        is_current_band_member = db.query(BandMember).where(BandMember.band_id == psi.band_id). \
            where(BandMember.user_id == psi.user_id).first()
        if is_current_band_member:
            raise HTTPException(status_code=400, detail="Already a member")

        invite = BandInvite(band_id=psi.band_id, user_id=psi.user_id, code=generate_code())
        db.add(invite)
        db.commit()
    except exc.sa_exc.SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Some database error")


@app.post("/login")
async def user_login(pul: PostUserLogin, db: Session = Depends(get_database)):
    user = db.query(User).where(User.email == pul.email).first()
    if verify_password(pul.password, user.password_hash):
        return sign_jwt(user)
    raise HTTPException(status_code=400, detail="Email/Password does not exist")


# =====TESTING =====
@app.get("/users", tags=['test'])
async def print_users(db: Session = Depends(get_database)):
    results = db.query(User).all()
    return results


@app.get("/bands", tags=['test'])
async def print_bands(db: Session = Depends(get_database)):
    results = db.query(Band).all()
    return results


@app.get("/band_members", tags=['test'])
async def print_band_members(db: Session = Depends(get_database)):
    results = db.query(BandMember).all()
    return results


@app.get("/verifications", tags=['test'])
async def print_verifications(db: Session = Depends(get_database)):
    results = db.query(EmailVerification).all()
    return results


def populate_db():
    db = next(get_database())
    user1 = User(
        first_name="Jason",
        last_name="Bourne",
        email="jason@gmail.com",
        password_hash=hash_password("test"),
        location="CA"
    )
    user2 = User(
        first_name="Dexter",
        last_name="Morgan",
        email="dexter@gmail.com",
        password_hash=hash_password("test"),
        location="FL"
    )
    user3 = User(
        first_name="Dean",
        last_name="Winchester",
        email="dw@gmail.com",
        password_hash=hash_password("test"),
        location="KS"
    )
    user1_band = Band(name="Assassins", location="Spain")

    db.add(user1)
    db.add(user2)
    db.add(user3)
    db.add(user1_band)
    db.flush()
    bm = BandMember(band_id=user1_band.id,user_id=user1.id,admin=True)
    bm2 = BandMember(band_id=user1_band.id, user_id=user2.id, admin=False)
    db.add(bm)
    db.add(bm2)
    db.commit()
# =====TESTING =====


if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    populate_db()
    uvicorn.run(app, host="localhost", port=8000)

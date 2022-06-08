import logging.config
import string
import time
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request
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
    chars = string.ascii_letters + string.digits
    code = ''.join(random.choice(chars) for i in range(8))
    return code


def get_current_user(token: str = Depends(JwtBearer())):
    try:
        decoded = decode_jwt(token)
    except:
        return None
    if decoded != {}:
        return JwtUser(user_id=decoded['user_id'])
    return None


def get_current_user_partially_protected(request: Request):
    def has_auth_header():
        try:
            a:str=request.headers["authorization"]
            return a[7:]
        except:
            return None

    auth = has_auth_header()
    if auth:
        token:str = auth
        decoded = decode_jwt(token)
        return JwtUser(user_id=decoded['user_id'])
    else:
        return None



@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/band/{id}")
async def get_band(id: int, db: Session = Depends(get_database)):
    try:
        band = db.query(Band).where(Band.id == id).first()
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Unable to get band")
    return band


@app.get("/bandmembers/{band_id}")
async def get_band_members(band_id: int, db: Session = Depends(get_database)):
    try:
        members = db.query(User.id, User.first_name, User.last_name).where(User.id.in_(
            db.query(BandMember.user_id).where(band_id == BandMember.band_id))).all()
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Unable get band members")
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

@app.get("/verify_band_code/{band_id}/{invite_code}")
async def verify_band_code(band_id: int, invite_code: str, db: Session = Depends(get_database),
                           user:JwtUser = Depends(get_current_user_partially_protected)):

    # user: JwtUser = get_current_user(False)
    band_invite = db.query(BandInvite).where(BandInvite.band_id == band_id).\
        where(BandInvite.code == invite_code).first()

    if band_invite is None:
        raise HTTPException(status_code=404, detail="Invalid invite")

    if band_invite.expiration < time.time():
        raise HTTPException(status_code=400, detail="Expired invite")

    if user is not None:
        #band_invite meant for some user that is not the current user
        if band_invite.user_id is not None and band_invite.user_id != user.user_id:
            raise HTTPException(status_code=403, detail="Invalid invite")
        #logged in and invite is meant for no userID then allow it
        if band_invite.user_id is None:
            return {"Success"}
        return
    else:
        #Not logged in and invite is for no user id then allow it
        if band_invite.user_id is None:
            return {"Success"}
        else:
            raise HTTPException(status_code=403, detail="Invalid invite")

    return


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
        raise HTTPException(status_code=500, detail="Could not get user")
    return user


@app.put("/update_user")
async def update_user(user_request: PostUserRequest, db: Session = Depends(get_database),user: JwtUser = Depends(get_current_user)):
    try:
        dbuser = db.query(User).where(User.id == user.user_id).first()
        dbuser.first_name = user_request.first_name
        dbuser.last_name = user_request.last_name
        dbuser.email = user_request.email
        if user_request.password:
            dbuser.password_hash = hash_password(user_request.password)
        dbuser.location = user_request.location
        db.commit()

        # TODO update long/lat with new updated location
        # TODO if email changes set verified to false
        #  and send out new verification code + email
        #  and remove any existing verification code entries if not verified
    except exc.sa_exc.SQLAlchemyError as err:
        raise HTTPException(status_code=500, detail="Could not update user")
    return {"Success"}


@app.put("/update_band")
async def update_band(band_request: PostBandRequest, db: Session = Depends(get_database),user: JwtUser = Depends(get_current_user)):
    try:
        bm = db.query(BandMember).where(BandMember.band_id == band_request.id).where(BandMember.user_id == user.user_id).first()
        if not bm.admin:
            raise HTTPException(status_code=400, detail="Not and admin")
        band = db.query(Band).where(Band.id == band_request.id).first()

        band.name = band_request.name
        band.location = band_request.location
        db.commit()
    except exc.sa_exc.SQLAlchemyError as err:
        raise HTTPException(status_code=500, detail="Could not update band")
    return {"Success"}


@app.delete("/delete_band")
async def delete_band(band_request: PostBandRequest, db: Session = Depends(get_database),user: JwtUser = Depends(get_current_user)):
    try:
        bm = db.query(BandMember).where(BandMember.band_id == band_request.id).where(BandMember.user_id == user.user_id).first()
        if not bm.admin:
            raise HTTPException(status_code=400, detail="Not and admin")
        band = db.query(Band).where(Band.id == band_request.id).first()

        db.delete(BandMember).where(BandMember.user_id.in_(db.query(BandMember.user_id).where(BandMember.band_id == band_request.id)))
        db.delete(band)
        db.commit()
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Could not delete band")
    return {"Success"}

@app.get("/verify/{code}")
async def verify_user_email(code: str, db: Session = Depends(get_database)):
    try:
        email_verification = db.query(EmailVerification).where(EmailVerification.code == code).first()
        if email_verification:
            user = db.query(User).where(User.id == email_verification.id).first()
            user.email_verified = True
            db.delete(email_verification)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Invalid verification code")
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Could not verify email, try again later")
    return "Success"


@app.post("/accept_invite")
async def accept_invite(pai: PostAcceptInvite, db: Session = Depends(get_database),user: JwtUser = Depends(get_current_user)):
    try:
        invite = db.query(BandInvite).where(BandInvite.code == pai.code).where(user.user_id == BandInvite.user_id).first()
        if invite:
            bm = BandMember(band_id=invite.band_id, user_id=user.user_id, admin=False)
            db.add(bm)
            db.delete(invite)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Invalid invite")
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Could verify invite, try again later")
    pass


@app.post("/decline_invite")
async def decline_invite(pai: PostAcceptInvite, db: Session = Depends(get_database),user: JwtUser = Depends(get_current_user)):
    try:
        invite = db.query(BandInvite).where(BandInvite.code == pai.code).where(user.user_id == BandInvite.user_id).first()
        if invite:
            db.delete(invite)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Invalid invite")
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Could verify invite, try again later")
    pass


@app.post("/send_invite")
async def send_invite(psi: PostSendInvite, db: Session = Depends(get_database), user: JwtUser = Depends(get_current_user())):
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
        first_name="Dextera",
        last_name="Morgana",
        email="dexter@gmail.com",
        password_hash=hash_password("test"),
        location="FL"
    )
    user3 = User(
        first_name="Sire",
        last_name="Denathrius",
        email="sire@gmail.com",
        password_hash=hash_password("test"),
        location="Revendreth"
    )
    user1_band = Band(name="Assassins", location="Spain")

    db.add_all([user1, user2, user3, user1_band])
    db.flush()
    bm = BandMember(band_id=user1_band.id,user_id=user1.id,admin=True)
    bm2 = BandMember(band_id=user1_band.id, user_id=user2.id, admin=False)
    db.add_all([bm, bm2])
    db.commit()
# =====TESTING =====


if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    populate_db()
    uvicorn.run(app, host="localhost", port=8000)

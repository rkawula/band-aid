import json
import logging.config
import string
import time
from types import SimpleNamespace

import uvicorn
import googlemaps
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import or_, and_
from starlette.websockets import WebSocket, WebSocketDisconnect

from database_models.db_connector import get_database
from sqlalchemy.orm import Session

from emails import Email
from base_models.band_models import (
    PostUserRequest,
    PostBandRequest,
    PostSendInvite,
    PostAcceptInvite, GetUserLogin,
    JwtUser, Message
)
from database_models.db_connector import engine, DbSession
from database_models.models import (
    Base,
    User,
    BandMember,
    BandInvite,
    EmailVerification,
    Band, DBNotification, LookingForMember, LookingForBand, LocationCache, BandInviteByEmail, DBMessage,
    NotificationPriority
)
from auth.jwt_handler import sign_jwt, decode_jwt
from auth.jwt_bearer import JwtBearer
from sqlalchemy.orm import exc

from notifications.notifications import Notification
from security.password_security import hash_password, verify_password
import random
from fastapi.middleware.cors import CORSMiddleware
from decouple import config

GEOCODE_API_KEY = config("GEOCODE_API_KEY")
# TODO make this work
logger = logging.getLogger(__name__)

app = FastAPI()

origins = [
    "http://localhost:8000",
    "http://localhost:3000"
]
app.add_middleware(CORSMiddleware,
                   allow_origins=origins,
                   allow_credentials=True,
                   allow_methods=["*"],
                   allow_headers=["*"])

ONE_DAY_IN_SECONDS = 60 * 60 * 24
THIRTY_DAYS_IN_SECONDS = 30 * ONE_DAY_IN_SECONDS

open_sockets = {}


def location_to_coords(location: str, db):
    # TODO Check with stored cache before going to google
    dup = db.query(LocationCache).where(LocationCache.location == location.lower()).first()
    if dup:
        return {"lng": dup.lng, "lat": dup.lat}

    geocode_api = googlemaps.Client(key=GEOCODE_API_KEY)
    result = geocode_api.geocode(location)
    coordinates = result[0]['geometry']['location']
    if result:
        db.add(LocationCache(lng=coordinates['lng'], lat=coordinates['lat'], location=location))
    return coordinates


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
            a: str = request.headers["authorization"]
            return a[7:]
        except:
            return None

    token = has_auth_header()
    if token:
        decoded = decode_jwt(token)
        if decoded == {}:
            raise HTTPException(status_code=401, detail="Invalid token")
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
                           user: JwtUser = Depends(get_current_user_partially_protected)):
    band_invite = db.query(BandInvite).where(BandInvite.band_id == band_id). \
        where(BandInvite.code == invite_code).first()

    if band_invite is None:
        raise HTTPException(status_code=404, detail="Invalid invite")

    if band_invite.expiration < time.time():
        raise HTTPException(status_code=400, detail="Expired invite")

    if user is not None:
        # band_invite meant for some user that is not the current user
        if band_invite.user_id is not None and band_invite.user_id != user.user_id:
            raise HTTPException(status_code=403, detail="Invalid invite")
        # logged in and invite is meant for no userID then allow it
        if band_invite.user_id is None:
            return {"Success"}
        return
    else:
        # Not logged in and invite is for no user id then allow it
        if band_invite.user_id is None:
            return {"Success"}
        else:
            raise HTTPException(status_code=403, detail="Invalid invite")


@app.get("/test/{location}", tags=['test'])
async def geotest(location: str):
    return location_to_coords(location)


@app.post("/register")
async def register_user(user_request: PostUserRequest, db: Session = Depends(get_database)):
    user_request.email = user_request.email.lower()
    dup = db.query(User).where(User.email == user_request.email).first()
    if dup:
        raise HTTPException(status_code=400, detail="Email already exists")
    lng_lat = None
    if user_request.location is not None:
        lng_lat = location_to_coords(user_request.location, db)

    user = User(
        first_name=user_request.first_name,
        last_name=user_request.last_name,
        email=user_request.email,
        password_hash=hash_password(user_request.password),
        location=user_request.location,
        longitude=lng_lat['lng'] if lng_lat else None,
        latitude=lng_lat['lat'] if lng_lat else None

    )

    try:
        add_and_flush(db, user)
        try:
            code = generate_code()
            ev = EmailVerification(user_id=user.id, code=code)
            add_and_flush(db, ev)
            try:
                band_invites = db.query(BandInviteByEmail).where(BandInviteByEmail.email == user.email,
                                                                 time.time() < BandInviteByEmail.expiration).all()
                if band_invites:
                    for invite in band_invites:
                        db.add(BandMember(user_id=user.id, band_id=invite.band_id))
                    db.delete(BandInviteByEmail).where(BandInviteByEmail.email == user.email)
            except exc.sa_exc.SQLAlchemyError as err:
                db.rollback()
                raise HTTPException(status_code=500, detail="Inviting to band error")
        except exc.sa_exc.SQLAlchemyError as err:
            db.rollback()
            raise HTTPException(status_code=500, detail="Could not create verification code entry")
    except exc.sa_exc.SQLAlchemyError as err:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create user entry")

    db.commit()

    # TODO get new app password for gmail
    mail = Email()
    mail.send_invite_email(ev.code, user_request.email)

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


@app.delete("/user/")
async def delete_user(db: Session = Depends(get_database),
                      user: JwtUser = Depends(get_current_user)):
    try:
        db.delete(BandInvite).where(BandInvite.user_id == user.user_id)
        db.delete(DBNotification).where(DBNotification.recipient_user_id == user.user_id)
        db.delete(BandMember).where(BandMember.user_id == user.user_id)
        db.delete(LookingForBand).where(LookingForBand.user_id == user.user_id)
        db.delete(User).where(User.id == user.user_id)
    except exc.sa_exc.SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not get user")
    db.commit()
    return {"Success"}


@app.put("/update_user")
async def update_user(user_request: PostUserRequest, db: Session = Depends(get_database),
                      user: JwtUser = Depends(get_current_user)):
    try:
        dbuser = db.query(User).where(User.id == user.user_id).first()
        dbuser.first_name = user_request.first_name
        dbuser.last_name = user_request.last_name
        dbuser.email = user_request.email
        if user_request.password:
            dbuser.password_hash = hash_password(user_request.password)
        if user_request.location and dbuser.location != user_request.location:
            dbuser.location = user_request.location
            lng_lat = location_to_coords(user_request.location, db)
            dbuser.longitude = lng_lat.lng
            dbuser.latitude = lng_lat.lat
        db.commit()

        # TODO To revoke tokens, add date column to user for rejecting tokens given before x date
        # TODO update long/lat with new updated location
        # TODO if email changes set verified to false
        #  and send out new verification code + email
        #  and remove any existing verification code entries if not verified
    except exc.sa_exc.SQLAlchemyError as err:
        raise HTTPException(status_code=500, detail="Could not update user")
    return {"Success"}


@app.put("/update_band")
async def update_band(band_request: PostBandRequest, db: Session = Depends(get_database),
                      user: JwtUser = Depends(get_current_user)):
    try:
        bm = db.query(BandMember).where(BandMember.band_id == band_request.id).where(
            BandMember.user_id == user.user_id).first()
        if not bm.admin:
            raise HTTPException(status_code=400, detail="Not and admin")
        band = db.query(Band).where(Band.id == band_request.id).first()

        band.name = band_request.name

        if band.location != band_request.location:
            band.location = band_request.location
            lng_lat = location_to_coords(band.location, db)
            band.longitude = lng_lat.lng
            band.latitude = lng_lat.lat

        db.commit()
    except exc.sa_exc.SQLAlchemyError as err:
        raise HTTPException(status_code=500, detail="Could not update band")
    return {"Success"}


@app.delete("/delete_band")
async def delete_band(band_request: PostBandRequest, db: Session = Depends(get_database),
                      user: JwtUser = Depends(get_current_user)):
    try:
        bm = db.query(BandMember).where(BandMember.band_id == band_request.id).where(
            BandMember.user_id == user.user_id).first()
        if not bm.admin:
            raise HTTPException(status_code=400, detail="Not and admin")
        band = db.query(Band).where(Band.id == band_request.id).first()
        usr = db.query(User).where(User.id == user.user_id).first()
        members = db.query(User).where(
            User.id.in_(db.query(BandMember).where(BandMember.band_id == band_request.id)).all())
        notify_band_members(members, band.name + " has been disbanded by " + usr.first_name + " " + usr.last_name, NotificationPriority.high, THIRTY_DAYS_IN_SECONDS)
        db.delete(BandMember).where(
            BandMember.user_id.in_(db.query(BandMember.user_id).where(BandMember.band_id == band_request.id)))
        db.delete(LookingForMember).where(LookingForMember.band_id == band_request.id)
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
async def accept_invite(pai: PostAcceptInvite, db: Session = Depends(get_database),
                        user: JwtUser = Depends(get_current_user)):
    try:
        invite = db.query(BandInvite).where(BandInvite.code == pai.code).where(
            user.user_id == BandInvite.user_id).first()
        if invite:
            band = db.query(Band).where(Band.id == invite.band_id).first()
            username = db.query(User.first_name, User.last_name).where(User.id == user.user_id).first()
            notify_band_admins(db, invite.band_id, "Accepted",
                               username.first_name + " " + username.last_name + " has joined " + band.name + "!")
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
async def decline_invite(pai: PostAcceptInvite, db: Session = Depends(get_database),
                         user: JwtUser = Depends(get_current_user)):
    try:
        invite = db.query(BandInvite).where(BandInvite.code == pai.code).where(
            user.user_id == BandInvite.user_id).first()
        if invite:
            db.delete(invite)
            db.commit()

            band = db.query(Band).where(Band.id == invite.band_id).first()
            username = db.query(User.first_name, User.last_name).where(User.id == user.user_id).first()
            notify_band_admins(db, invite.band_id, "Declined",
                               username.first_name + " " + username.last_name + " has declined your invite to join " + band.name + ".")
        else:
            raise HTTPException(status_code=400, detail="Invalid invite")
    except exc.sa_exc.SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Could verify invite, try again later")
    pass


def notify_band_admins(db, band_id, subject, body, priority=NotificationPriority.normal, expiry=THIRTY_DAYS_IN_SECONDS):
    admins = db.query(User).where(User.id.in_(
        db.query(BandMember.user_id).where(BandMember.band_id == band_id, BandMember.admin == True))).all()
    notify_users(admins, subject, body, priority, expiry)


def notify_band_members(db, band_id, subject, body, priority=NotificationPriority.normal,
                        expiry=THIRTY_DAYS_IN_SECONDS):
    members = db.query(User).where(User.id.in_(
        db.query(BandMember.user_id).where(BandMember.band_id == band_id))).all()
    notify_users(members, subject, body, priority, expiry)


def notify_users(users, subject, msg, priority=NotificationPriority.normal, expiration=ONE_DAY_IN_SECONDS * 7):
    notification = Notification()
    email = Email()
    for user in users:
        if user.email_notification_opt_in:
            email.send_notification_email(user.id, subject, msg)
        notification.send(user.id, msg, time.time() + expiration, priority)


@app.post("/send_invite")
async def send_invite(psi: PostSendInvite, db: Session = Depends(get_database),
                      user: JwtUser = Depends(get_current_user())):
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
async def user_login(gul: GetUserLogin, db: Session = Depends(get_database)):
    user = db.query(User).where(User.email == gul.email).first()
    if user and verify_password(gul.password, user.password_hash):
        return sign_jwt(user)
    raise HTTPException(status_code=400, detail="Email/Password does not exist")


@app.put("/read_notification/{id}")
async def read_notification(id: int, db: Session = Depends(get_database), user: JwtUser = Depends(get_current_user)):
    notif: DBNotification = db.query(DBNotification).where(DBNotification.id == id,
                                                           DBNotification.recipient_user_id == user.user_id).first()
    if notif is None:
        raise HTTPException(status_code=404, detail="DBNotification does not exist")
    if notif.recipient_user_id != user.user_id:
        raise HTTPException(status_code=401, detail="That is not your message, but you already know this")
    notif.read = True
    db.commit()
    return {"Success"}


def get_range_coordinates(lat, lng, range):
    lat_offset = range / 69
    lng_offset = range / 52
    return (lat - lat_offset, lat + lat_offset), (lng - lng_offset, lng + lng_offset)


@app.get("/search")
async def search(location: str, type: str, distance: int, roles, db: Session = Depends(get_database)):
    loc = location_to_coords(location, db)
    coord_range = get_range_coordinates(loc['lat'], loc['lng'], distance)
    arr_roles = roles.split(",")
    lat_range = coord_range[0]
    lng_range = coord_range[1]
    if type == "Band":
        res = db.query(Band).where(
            Band.id.in_(db.query(LookingForMember.band_id).where(LookingForMember.talent.in_(arr_roles)))). \
            where(lat_range[0] < Band.latitude, Band.latitude < lat_range[1],
                  lng_range[0] < Band.longitude, Band.longitude < lng_range[1]).all()
    elif type == "Member":
        res = db.query(User).where(
            User.id.in_(db.query(LookingForBand.band_id).where(LookingForBand.talent.in_(arr_roles)))). \
            where(lat_range[0] < User.latitude, User.latitude < lat_range[1],
                  lng_range[0] < User.longitude, User.longitude < lng_range[1]).all()
    else:
        raise HTTPException(status_code=400, detail="Bruh, that's not a priority")
    return res


@app.get("/user_online/{id}")
async def user_online(id: int):
    user = open_sockets.get(id)
    return user is not None


async def send_message(sender_user_id: int, message: Message, db: Session):
    # get recipient_user_id
    recipient_user_id = message.recipient_user_id
    # get message text
    msg = message.message
    recipient_ws = open_sockets.get(recipient_user_id)
    db_msg = DBMessage(sender_user_id=sender_user_id, recipient_user_id=recipient_user_id, message=msg)
    if recipient_ws:
        db_msg.read = True
    db.add(db_msg)
    db.commit()

    # notify all open websockets of recipient and sender of new message
    sender_ws = open_sockets.get(sender_user_id)
    if recipient_ws:
        broken_links = []
        for socket in recipient_ws:
            try:
                await socket.send_json(db_msg.json())
            except RuntimeError:
                print("Broken link")
                broken_links.append(socket)

        if broken_links:
            for broken_link in broken_links:
                recipient_ws.remove(broken_link)
    else:
        notif = Notification()
        user = db.query(User).where(User.id == sender_user_id).first()
        notif.send(recipient_user_id, "You have a new message from " + user.first_name + " " + user.last_name,
                   time.time() + ONE_DAY_IN_SECONDS * 7, NotificationPriority.normal)
    if sender_ws:
        broken_links = []
        for socket in sender_ws:
            try:
                await socket.send_json(db_msg.json())
            except RuntimeError:
                print("Broken link")
                broken_links.append(socket)

        if broken_links:
            for broken_link in broken_links:
                sender_ws.remove(broken_link)


@app.get("/messages/{target_user_id}")
async def get_messages(target_user_id: int, db: Session = Depends(get_database),
                       user: JwtUser = Depends(get_current_user)):
    messages = db.query(DBMessage).where(or_(and_(DBMessage.recipient_user_id == user.user_id,
                                                  DBMessage.sender_user_id == target_user_id),
                                             and_(DBMessage.sender_user_id == user.user_id,
                                                  DBMessage.recipient_user_id == target_user_id))) \
        .order_by(DBMessage.sent.asc()).all()
    return messages


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_database)):
    await websocket.accept()
    jwt = await websocket.receive_text()
    user = get_current_user(jwt)
    if not user:
        await websocket.close()
        return

    user_id = user.user_id
    user_sockets = open_sockets.get(user_id)
    if user_sockets:
        user_sockets.append(websocket)
    else:
        open_sockets[user_id] = [websocket]

    while True:
        try:
            message: Message = json.loads(await websocket.receive_text(), object_hook=lambda d: SimpleNamespace(**d))
            await send_message(user_id, Message(recipient_user_id=message.recipient_user_id, message=message.message),
                               db)
        except WebSocketDisconnect:
            try:
                user_sockets.remove(websocket)
            except:
                print("Socket already removed")
                pass
            break


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


@app.get("/lfms", tags=['test'])
async def print_looking_for_members(db: Session = Depends(get_database)):
    results = db.query(LookingForMember).all()
    return results


@app.get("/lfbs", tags=['test'])
async def print_looking_for_bands(db: Session = Depends(get_database)):
    results = db.query(LookingForBand).all()
    return results


@app.get("/bibe", tags=['test'])
async def print_band_invite_by_email(db: Session = Depends(get_database)):
    results = db.query(BandInviteByEmail).all()
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
        location="Revendreth",
    )

    user1_band = Band(name="Assassins", location="Spain", longitude=-122.4, latitude=37.8)

    db.add_all([user1, user2, user3, user1_band])
    db.flush()
    band1_lfm = LookingForMember(band_id=user1_band.id, talent="bass")
    band1_lfm2 = LookingForMember(band_id=user1_band.id, talent="piano")
    bm = BandMember(band_id=user1_band.id, user_id=user1.id, admin=True)
    bm2 = BandMember(band_id=user1_band.id, user_id=user2.id, admin=False)
    bibe = BandInviteByEmail(email="invite@gmail.com", band_id=user1_band.id,
                             expiration=time.time() + THIRTY_DAYS_IN_SECONDS)
    db.add_all([bm, bm2, band1_lfm, band1_lfm2, bibe])
    db.commit()


# =====TESTING =====


if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    populate_db()
    uvicorn.run(app, host="localhost", port=8000)

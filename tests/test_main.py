import json
import time
import main
import pytest
import asyncio
from starlette.websockets import WebSocket
from unittest import mock
from unittest.mock import patch, MagicMock, Mock
from fastapi.testclient import TestClient
from pytest_mock import mocker
from sqlalchemy import create_engine
from sqlalchemy.orm import exc, Session
from sqlalchemy.orm import sessionmaker
from websockets.exceptions import ConnectionClosed

from auth.jwt_handler import sign_jwt, decode_jwt
from database_models.models import User, EmailVerification, Base, Band, BandMember, BandInvite, DBMessage, \
    LookingForMember, Notification, NotificationType
from main import get_database, app
from security.password_security import hash_password

DATABASE_URL = "sqlite:///./test_database.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=True
)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
DbSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


def override_get_db():
    try:
        db = DbSession()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_database] = override_get_db

valid_data = {
    "first_name": "Jason",
    "last_name": "Bourne",
    "email": "jbourne@gmail.com",
    "password": "test123"
}
invalid_data = {
    "first_name": [],
    "last_name": "Bourne",
    "email": "jbourne@gmail.com",
    "password": "test123"
}


def test_valid_register_user():
    resp = client.post("/register", json=valid_data)
    assert resp.status_code == 200
    user = decode_jwt(resp.content.decode().replace("\"", ""))
    db = next(override_get_db())
    assert len(db.query(EmailVerification).where(EmailVerification.user_id == user['user_id']).all()) == 1
    assert len(db.query(User).where(User.id == user['user_id']).all()) == 1

@pytest.fixture(scope="session", autouse=True)
def populate_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = next(override_get_db())
    user1 = create_user("Jason", "Bourne", "jason@gmail.com", "test", "CA", db)
    user2 = create_user("Dexter", "Morgan", "dexter@gmail.com", "test", "FL", db)
    user3 = create_user("Sire", "Denathrius", "sire@gmail.com", "test", "Revendreth", db)
    user4 = create_user("Joe", "Schmo", "joe@gmail.com", "test", "MS", db)
    user5 = create_user("John", "Doe", "john@gmail.com", "test", "KS", db)
    user1_band = Band(name="Assassins", location="Spain")
    user5_band = Band(name="IDK", location="KS")
    db.add_all([user1_band, user5_band, user4])
    db.flush()
    user4_band1_invite = BandInvite(band_id=user1_band.id, user_id=user4.id, code="ABCD1234")
    user4_band5_invite = BandInvite(band_id=user5_band.id, user_id=user4.id, code="ABCD1235")
    ev = EmailVerification(user_id=user4.id, code="ABCD1234")
    bm = BandMember(band_id=user1_band.id, user_id=user1.id, admin=True)
    bm2 = BandMember(band_id=user1_band.id, user_id=user2.id, admin=False)
    bm5 = BandMember(band_id=user5_band.id, user_id=user5.id, admin=True)
    user5_notification = Notification(recipient_user_id=user5.id, message="You have been invited to join a band!", type=NotificationType.normal, expiration=time.time() + 600)
    user1_notification = Notification(recipient_user_id=user1.id, message="You have been invited to join a band!",
                                      type=NotificationType.normal, expiration=time.time() + 600)
    user1_notification_read = Notification(recipient_user_id=user1.id, message="You have been invited to join a band!",
                                      type=NotificationType.normal, read=True, expiration=time.time() + 600)
    band1_lfm = LookingForMember(band_id=user1_band.id, talent="Drums")
    band2_lfm = LookingForMember(band_id=user5_band.id, talent="Double Guitar")
    db.add_all([bm, bm2, bm5, band1_lfm, ev,user4_band1_invite, user4_band5_invite,
                band2_lfm, user5_notification, user1_notification, user1_notification_read])
    db.commit()


def test_duplicate_email_register_user():
    resp = client.post("/register", json=valid_data)
    assert resp.status_code == 400


def test_invalid_data_register_user():
    resp = client.post("/register", json=invalid_data)
    assert resp.status_code == 422


def test_bad_db_register_user():
    with mock.patch.object(Session, "add", side_effect=exc.sa_exc.SQLAlchemyError) as mock_close:
        valid_data["email"] = "newemail@gmail.com"
        resp = client.post("/register", json=valid_data)
        assert resp.status_code == 500


def create_user(f, l, e, p, loc, db):
    user = User(
        first_name=f,
        last_name=l,
        email=e,
        password_hash=hash_password(p),
        location=loc
    )
    db.add(user)
    db.flush()
    return user


def test_get_band():
    resp = client.get("/band/1")
    db = next(override_get_db())
    band = db.query(Band).where(Band.id == 1).first()
    resp_bad = json.loads(resp.content)
    assert resp.status_code == 200
    assert band.id == resp_bad['id']


def test_get_band_members():
    resp = client.get("/bandmembers/2")
    data = json.loads(resp.content)
    assert len(data) == 1


def test_create_band():
    band_req = {
        "name": "Prince",
        "location": "MN"
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 3).first()

    header = {
        "Authorization": "Bearer " + sign_jwt(user)
    }
    resp = client.post("/band", json=band_req, headers=header)
    assert resp.status_code == 200
    assert len(db.query(Band).where(Band.id == 2).all()) == 1
    assert len(db.query(BandMember).where(Band.id == 2).where(BandMember.user_id == user.id).all()) == 1


def test_invalid_token():
    band_req = {
        "name": "a",
        "location": "b"
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 1).first()
    header = {
        "Authorization": "Bearer " + sign_jwt(user) + 'invalid_token'
    }
    resp = client.post("/band", json=band_req, headers=header)
    assert resp.status_code == 401


def test_get_user():
    resp = client.get("/user/1")
    dict_resp = json.loads(resp.content)
    assert resp.status_code == 200
    assert dict_resp['email'] == 'jason@gmail.com'


def test_update_user():
    # TODO update with email and password changes
    user_req = {
        'first_name': 'DexterChange',
        'last_name': 'MorganChange',
        'email': 'dexter@gmail.com',
        'password': 'test'
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 2).first()
    assert user.first_name == 'Dexter'
    assert user.last_name == 'Morgan'
    header = {
        "Authorization": "Bearer " + sign_jwt(user)
    }
    resp = client.put("/update_user", json=user_req, headers=header)
    assert resp.status_code == 200
    db = next(override_get_db())
    changed_user = db.query(User).where(User.id == 2).first()
    assert changed_user.first_name == user_req['first_name']
    assert changed_user.last_name == user_req['last_name']


def test_verify_band_code_no_user_and_no_user_is_req():
    db = next(override_get_db())
    band = Band(name="test1", location="home")
    db.add(band)
    db.flush()
    db.commit()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    url = "/verify_band_code/{0}/{1}".format(band.id, bi.code)
    resp = client.get(url)
    assert resp.status_code == 200
    # 200


def test_verify_band_code_has_user_and_no_user_req():
    db = next(override_get_db())
    header = create_auth_header(1)
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code), headers=header)
    assert resp.status_code == 200
    # 200


def test_verity_band_code_invite_expired():
    db = next(override_get_db())
    header = create_auth_header(1)
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() - 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code), headers=header)
    assert resp.status_code == 400


def test_verify_band_code_invalid_band_id():
    db = next(override_get_db())
    header = create_auth_header(1)
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id + 1000, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code), headers=header)
    assert resp.status_code == 404
    # 404


def test_verify_band_code_invalid_code():
    db = next(override_get_db())
    header = create_auth_header(1)
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="AAAAAAAA", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code + 'a'), headers=header)
    assert resp.status_code == 404


def test_verify_band_code_no_user_and_user_is_req():
    db = next(override_get_db())
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, user_id=2, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code))
    assert resp.status_code == 403
    # 403


def test_verify_band_code_has_user_and_different_user_is_req():
    db = next(override_get_db())
    authuser = 1
    header = create_auth_header(authuser)
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, user_id=authuser + 1, code="AAAAAAAA", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code), headers=header)
    assert resp.status_code == 403
    # 403


def test_verify_band_code_has_invalid_user():
    db = next(override_get_db())
    header = {
        "Authorization": "Bearer " + sign_jwt(db.query(User).where(User.id == 1).first()) + 'a'
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id, bi.code), headers=header)
    assert resp.status_code == 401


def test_update_band():
    # TODO test not admin
    pass


def test_delete_user():
    # No functional code present
    pass


def create_auth_header(user_id):
    db = next(override_get_db())
    return {
        "Authorization": "Bearer " + sign_jwt(db.query(User).where(User.id == user_id).first())
    }


def test_delete_band_not_member():
    header = create_auth_header(3)
    band_id = 1
    resp = client.delete("/delete_band?band_id={0}".format(band_id), headers=header)
    assert resp.status_code == 400
    data = json.loads(resp.text)
    assert data["detail"] == "Not a member"


def test_delete_band_not_admin():
    header = create_auth_header(2)
    band_id = 1
    resp = client.delete("/delete_band?band_id={0}".format(band_id), headers=header)
    assert resp.status_code == 400
    data = json.loads(resp.text)
    assert data["detail"] == "Not an admin"


def test_delete_band_success():
    header = create_auth_header(5)
    band_id = 2
    db = next(override_get_db())
    before_band = db.query(Band).where(Band.id == band_id).all()
    before_bm = db.query(BandMember).filter(BandMember.band_id == band_id).all()
    before_lfm = db.query(LookingForMember).where(LookingForMember.band_id == band_id).all()
    resp = client.delete("/delete_band?band_id={0}".format(band_id), headers=header)
    after_bm = db.query(BandMember).filter(BandMember.band_id == band_id).all()
    after_lfm = db.query(LookingForMember).where(LookingForMember.band_id == band_id).all()
    after_band = db.query(Band).where(Band.id == band_id).all()
    assert len(before_bm) > 0
    assert len(after_bm) == 0
    assert len(before_lfm) > 0
    assert len(after_lfm) == 0
    assert len(before_band) > 0
    assert len(after_band) == 0
    assert resp.status_code == 200


def test_delete_band_band_does_not_exist():
    header = create_auth_header(2)
    band_id = 10000
    resp = client.delete("/delete_band?band_id={0}".format(band_id), headers=header)
    assert resp.status_code == 400
    data = json.loads(resp.text)
    assert data["detail"] == "Not a member"


def test_verify_user_email_invalid_code():
    resp = client.put("/verify_email?code={0}".format("INVALID"))
    assert resp.status_code == 400


def test_verify_user_email_success():
    resp = client.put("/verify_email?code={0}".format("ABCD1234"))
    assert resp.status_code == 200


def test_accept_invite_success():
    header = create_auth_header(4)
    resp = client.post("/accept_invite?code={0}".format("ABCD1234"), headers=header)
    assert resp.status_code == 200


def test_accept_invite_invalid_code():
    header = create_auth_header(4)
    resp = client.post("/accept_invite?code={0}".format("INVALID"), headers=header)
    assert resp.status_code == 400


def test_decline_invite_success():
    header = create_auth_header(4)
    resp = client.post("/decline_invite?code={0}".format("ABCD1235"), headers=header)
    assert resp.status_code == 200


def test_decline_invite_invalid_code():
    header = create_auth_header(4)
    resp = client.post("/decline_invite?code={0}".format("INVALID"), headers=header)
    assert resp.status_code == 400


def test_send_invite_target_already_member():
    header = create_auth_header(1)
    resp = client.post("/send_invite?user_id={0}&band_id={1}".format(2, 1), headers=header)
    assert resp.status_code == 400
    assert json.loads(resp.text)["detail"] == "Already a member"


def test_send_invite_not_admin():
    header = create_auth_header(2)
    resp = client.post("/send_invite?user_id={0}&band_id={1}".format(5, 1), headers=header)
    assert resp.status_code == 400
    assert json.loads(resp.text)["detail"] == "Not allowed"


def test_send_invite_not_member():
    header = create_auth_header(3)
    resp = client.post("/send_invite?user_id={0}&band_id={1}".format(5, 1), headers=header)
    assert resp.status_code == 400
    assert json.loads(resp.text)["detail"] == "Not allowed"


def test_send_invite_success():
    header = create_auth_header(1)
    resp = client.post("/send_invite?user_id={0}&band_id={1}".format(5, 1), headers=header)
    assert resp.status_code == 200


def test_user_login_success():
    # TODO test invalid credentials
    data = {
        "email": "jason@gmail.com",
        "password": "test"
    }
    resp = client.get("/login", json=data)
    assert resp.status_code == 200
    jwt = resp.content.decode().replace("\"", "")
    user = decode_jwt(jwt)
    assert user["user_id"] == 1


def test_user_login_invalid_email():
    # TODO test invalid credentials
    data = {
        "email": "INVALID@gmail.com",
        "password": "test"
    }
    resp = client.get("/login", json=data)
    assert resp.status_code == 400


def test_user_login_invalid_password():
    # TODO test invalid credentials
    data = {
        "email": "jason@gmail.com",
        "password": "INVALID"
    }
    resp = client.get("/login", json=data)
    assert resp.status_code == 400


def test_read_notification_success():
    header = create_auth_header(5)
    resp = client.put("/read_notification/{0}".format(1), headers=header)
    assert resp.status_code == 200


def test_read_notification_notif_does_not_exist():
    header = create_auth_header(1)
    resp = client.put("/read_notification/{0}".format(1000), headers=header)
    assert resp.status_code == 404


def test_read_notification_wrong_user():
    header = create_auth_header(1)
    resp = client.put("/read_notification/{0}".format(1), headers=header)
    assert resp.status_code == 401


def test_read_notification_already_read():
    header = create_auth_header(1)
    resp = client.put("/read_notification/{0}".format(3), headers=header)
    assert resp.status_code == 400


def test_get_notifications():
    # No functional code
    pass


def test_search():
    # TODO BIG TODO
    pass


def test_user_online():
    # TODO implement
    pass


def test_get_messages():
    # No functional code
    pass


def create_ws_session(user_1_id, user_2_id, db):
    session = client.websocket_connect("/ws")
    session.send_text(sign_jwt(db.query(User).where(User.id == user_1_id).first()))
    session.send_text(user_2_id)
    return session


@pytest.mark.asyncio
async def test_open_websocket_and_send_message():
    # User 1 sends message to user 2
    db = next(override_get_db())
    session = create_ws_session(1, 2, db)
    session.send_text("Hello")
    await asyncio.sleep(.1)
    one_to_two = db.query(DBMessage).filter(DBMessage.sender_user_id == 1, DBMessage.recipient_user_id == 2).all()
    assert len(one_to_two) == 1
    session.close()


@pytest.mark.asyncio
async def test_send_message():
    db = next(override_get_db())
    session = create_ws_session(1, 3, db)
    session.send_text("Hello")
    await asyncio.sleep(.1)
    one_to_two = db.query(DBMessage).filter(DBMessage.sender_user_id == 1, DBMessage.recipient_user_id == 2).all()
    assert len(one_to_two) == 1
    session.close()


@pytest.mark.asyncio
async def test_invalid_jwt():
    db = next(override_get_db())

    with mock.patch.object(WebSocket, "close") as mock_close:
        session = client.websocket_connect("/ws")
        session.send_text(sign_jwt(db.query(User).where(User.id == 1).first()) + 'invalid')
        await asyncio.sleep(.1)
        mock_close.assert_called_once()
        # real.close.assert_called_times(1)

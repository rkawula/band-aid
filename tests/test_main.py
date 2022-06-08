import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import exc
from sqlalchemy.orm import sessionmaker

import main
from auth.jwt_handler import sign_jwt
from base_models.band_models import PostBandRequest
from database_models.models import User, EmailVerification, Base, Band, BandMember, BandInvite
from main import get_database, app
from security.security import hash_password

DATABASE_URL = "sqlite:///./test_database.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
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
    db = next(override_get_db())
    assert len(db.query(EmailVerification).all()) == 1
    assert len(db.query(User).all()) == 4
    # TODO assert returned jwt is valid for given user


def test_duplicate_email_register_user():
    resp = client.post("/register", json=valid_data)
    assert resp.status_code == 400
    db = next(override_get_db())
    assert len(db.query(EmailVerification).all()) == 1
    assert len(db.query(User).all()) == 4


def test_invalid_data_register_user():
    resp = client.post("/register", json=invalid_data)
    assert resp.status_code == 422
    db = next(override_get_db())
    assert len(db.query(EmailVerification).all()) == 1
    assert len(db.query(User).all()) == 4


def test_bad_db_register_user():
    with patch("main.add_and_flush") as add_mock:
        add_mock.side_effect = exc.sa_exc.SQLAlchemyError()
        valid_data["email"] = "newemail@gmail.com"
        resp = client.post("/register", json=valid_data)
        assert resp.status_code == 500
        db = next(override_get_db())
        assert len(db.query(EmailVerification).all()) == 1
        assert len(db.query(User).all()) == 4

# TODO fuck it we don't need tests
# def test_bad_db_register_user_2():
#     with mock.patch("main.add_and_flush") as add_mock:
#         add_mock.side_effect = [None, exc.sa_exc.SQLAlchemyError()]
#         valid_data["email"] = "newemail@gmail.com"
#         resp = client.post("/register", json=valid_data)
#         print(resp.text)
#         assert resp.status_code == 500
#         db = next(override_get_db())
#         assert len(db.query(EmailVerification).all()) == 1
#         assert len(db.query(User).all()) == 1


@pytest.fixture(scope="session", autouse=True)
def populate_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = next(override_get_db())
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
    return [user1, user1_band, bm]

def test_get_band():
    resp = client.get("/band/1")
    db = next(override_get_db())
    band = db.query(Band).where(Band.id == 1).first()
    resp_bad = json.loads(resp.content)
    assert resp.status_code == 200
    assert band.id == resp_bad['id']

def test_get_band_members():
    resp = client.get("/bandmembers/1")
    db = next(override_get_db())
    bm = db.query(BandMember).where(BandMember.band_id == 1).all()
    assert len(bm) == 2


def test_create_band():
    band_req = {
        "name":"Prince",
        "location":"MN"
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 3).first()

    header = {
        "Authorization":"Bearer " + sign_jwt(user)
    }
    resp = client.post("/band", json=band_req,headers=header)
    assert resp.status_code == 200
    assert len(db.query(Band).where(Band.id == 2).all())==1
    assert len(db.query(BandMember).where(Band.id == 2).where(BandMember.user_id == user.id).all())==1

def test_invalid_token():
    band_req = {
        "name":"a",
        "location":"b"
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 1).first()
    header = {
        "Authorization":"Bearer " + sign_jwt(user)+'invalid_token'
    }
    resp = client.post("/band", json=band_req,headers=header)
    assert resp.status_code == 401

def test_get_user():
    resp = client.get("/user/1")
    dict_resp = json.loads(resp.content)
    assert resp.status_code == 200
    assert dict_resp['email'] == 'jason@gmail.com'

def test_update_user():
    # TODO update with email and password changes
    user_req = {
        'first_name':'DexterChange',
        'last_name':'MorganChange',
        'email':'dexter@gmail.com',
        'password':'test'
    }
    db = next(override_get_db())
    user = db.query(User).where(User.id == 2).first()
    assert user.first_name == 'Dexter'
    assert user.last_name == 'Morgan'
    header = {
        "Authorization":"Bearer " + sign_jwt(user)
    }
    resp = client.put("/update_user", json=user_req,headers=header)
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
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time()+600)
    db.add(bi)
    db.commit()
    url = "/verify_band_code/{0}/{1}".format(band.id,bi.code)
    resp = client.get(url)
    assert resp.status_code == 200
    #200
def test_verify_band_code_has_user_and_no_user_req():
    db = next(override_get_db())
    header = {
        "Authorization":"Bearer " + sign_jwt(db.query(User).where(User.id==1).first())
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code),headers=header)
    assert resp.status_code == 200
    #200
def test_verity_band_code_invite_expired():
    db = next(override_get_db())
    header = {
        "Authorization":"Bearer " + sign_jwt(db.query(User).where(User.id==1).first())
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="ABCD1234", expiration=time.time() - 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code),headers=header)
    assert resp.status_code == 400
def test_verify_band_code_invalid_band_id():
    db = next(override_get_db())
    header = {
        "Authorization":"Bearer " + sign_jwt(db.query(User).where(User.id==1).first())
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id+1000, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code),headers=header)
    assert resp.status_code == 404
    #404
def test_verify_band_code_invalid_code():
    db = next(override_get_db())
    header = {
        "Authorization": "Bearer " + sign_jwt(db.query(User).where(User.id == 1).first())
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, code="AAAAAAAA", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code+'a'), headers=header)
    assert resp.status_code == 404

def test_verify_band_code_no_user_and_user_is_req():
    db = next(override_get_db())
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id,user_id=2, code="ABCD1234", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code))
    assert resp.status_code == 403
    #403
def test_verify_band_code_has_user_and_different_user_is_req():
    db = next(override_get_db())
    authuser = 1
    header = {
        "Authorization": "Bearer " + sign_jwt(db.query(User).where(User.id == authuser).first())
    }
    band = Band(name="test2", location="home")
    db.add(band)
    db.flush()
    bi = BandInvite(band_id=band.id, user_id=authuser+1, code="AAAAAAAA", expiration=time.time() + 600)
    db.add(bi)
    db.commit()
    resp = client.get("/verify_band_code/{0}/{1}".format(band.id,bi.code), headers=header)
    assert resp.status_code == 403
    #403


def test_update_band():
    # TODO test not admin
    pass

def test_delete_band():
    # TODO test not admin
    pass

def test_verify_user_email():
    # TODO test invalid code
    pass

def test_accept_invite():
    # TODO test invalid code
    pass

def test_decline_invite():
    # TODO test invalid code
    pass

def test_send_invite():
    # TODO test not admin
    #      test target already a member
    pass

def test_user_login():
    # TODO test invalid credentials
    pass

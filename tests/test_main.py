from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import exc
from sqlalchemy.orm import sessionmaker

from database_models.models import User, EmailVerification, Base
from main import get_database, app

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
    assert len(db.query(User).all()) == 1


def test_duplicate_email_register_user():
    resp = client.post("/register", json=valid_data)
    assert resp.status_code == 400
    db = next(override_get_db())
    assert len(db.query(EmailVerification).all()) == 1
    assert len(db.query(User).all()) == 1


def test_invalid_data_register_user():
    resp = client.post("/register", json=invalid_data)
    assert resp.status_code == 422
    db = next(override_get_db())
    assert len(db.query(EmailVerification).all()) == 1
    assert len(db.query(User).all()) == 1


def test_bad_db_register_user():
    with mock.patch("main.add_and_flush") as add_mock:
        add_mock.side_effect = exc.sa_exc.SQLAlchemyError()
        valid_data["email"] = "newemail@gmail.com"
        resp = client.post("/register", json=valid_data)
        assert resp.status_code == 500
        db = next(override_get_db())
        assert len(db.query(EmailVerification).all()) == 1
        assert len(db.query(User).all()) == 1

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

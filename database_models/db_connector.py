from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=True
)

DbSession = sessionmaker(bind=engine)

Base = declarative_base()


def get_database():
    try:
        db = DbSession()
        yield db
    finally:
        db.close()
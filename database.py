from sqlmodel import SQLModel, Session, create_engine

from config import settings

engine = create_engine(settings.db_url, echo=False)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)

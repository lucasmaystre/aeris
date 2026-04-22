from sqlalchemy import create_engine

from aeris.config import settings
from aeris.database.models import Base

engine = create_engine(settings.database_url)


def create_tables() -> None:
    Base.metadata.create_all(engine)

from contextlib import contextmanager
from utils.db import SessionLocal

@contextmanager
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

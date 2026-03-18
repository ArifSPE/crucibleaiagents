import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv('DATABASE_URL', f"postgresql+psycopg://{os.getenv('DB_USER', 'admin')}:{os.getenv('DB_PASSWORD', 'secret123')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'crucibleaiagents')}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()



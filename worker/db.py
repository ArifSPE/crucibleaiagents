import os
import sys
from pathlib import Path

# Allow worker process to import API db/session modules.
API_DIR = Path(__file__).resolve().parent.parent / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from utils.db import SessionLocal  # noqa: E402


def get_session_local():
    return SessionLocal

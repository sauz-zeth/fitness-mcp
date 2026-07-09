from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DB_PATH = Path("data/fitness_coach.sqlite")


def get_db_path() -> Path:
    return Path(os.environ.get("FITNESS_COACH_DB", DEFAULT_DB_PATH))

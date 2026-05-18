import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EPISODES_DIR = DATA_DIR / "episodes"

load_dotenv(PROJECT_ROOT / ".env", override=False)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_REDIS = os.getenv("USE_REDIS", "false").lower() in ("1", "true", "yes")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "game.db"))

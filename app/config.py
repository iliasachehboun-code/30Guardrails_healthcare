import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

# override=True so the key in .env wins over any stale system-wide OPENAI_API_KEY.
load_dotenv(ROOT_DIR / ".env", override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MAIN_MODEL = os.getenv("MAIN_MODEL", "gpt-6.1-sol")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-6-luna")
MODERATION_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

DATA_DIR = ROOT_DIR / "data"
AGNO_DB_FILE = DATA_DIR / "agno.db"
AUDIT_DB_FILE = DATA_DIR / "guardrail_log.db"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)

import os
import logging


def _load_env_file(path=".env"):
    """Minimal, forgiving .env loader — tolerates spaces around '=',
    quoted or unquoted values, UTF-8 BOM, and blank/comment lines.
    Replaces python-dotenv, which fails on some Windows-saved files."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # strip matching surrounding quotes, straight or curly
            if len(value) >= 2 and value[0] in "\"'\u201c\u201d" and value[-1] in "\"'\u201c\u201d":
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)


_load_env_file()

# Copyright push2006 for modifications. See LICENSE.
PORT = int(os.environ.get("PORT", "10000"))
OWNER_ID = int(os.environ["OWNER_ID"])
MSG_EFFECT = 5046509860389126442
SHORT_URL = os.environ.get("SHORT_URL", "")
SHORT_API = os.environ.get("SHORT_API", "")
SHORT_TUT = os.environ.get("SHORT_TUT", "")
SESSION = "push2006"
TOKEN = os.environ["TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
WORKERS = int(os.environ.get("WORKERS", "5"))
AUTO_CLEAN_HOURS = 60
AUTO_CLEAN_PENDING_HOURS = 60
DB_URI = os.environ["DB_URI"]
DB_NAME = os.environ["DB_NAME"]
FSUBS = []
DB_CHANNEL = int(os.environ.get("DB_CHANNEL", "0"))
DB_CHANNELS = {}
AUTO_DEL = 300
ADMINS = list(dict.fromkeys([OWNER_ID] + [int(x) for x in os.environ.get("ADMINS", "").replace(",", " ").split()]))
DISABLE_BTN = True
PROTECT = True
MESSAGES = {
    "START": "Welcome, {first}. Browse the catalog or use /business.",
    "FSUB": "Please join the required channels to continue.",
    "ABOUT": "push2006 • Digital marketplace",
    "REPLY": "Use /start or /business to get started.",
    "SHORT_MSG": "Your link is ready.",
    "START_PHOTO": "", "FSUB_PHOTO": "", "SHORT_PIC": "", "SHORT": ""
}

def LOGGER(name: str, client_name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid stacking duplicate handlers when LOGGER() is called
    # multiple times with the same name (each call used to add
    # another handler, causing every message to print N times).
    if not logger.handlers:
        formatter = logging.Formatter(
            f"[%(asctime)s - %(levelname)s] - {client_name} - %(name)s - %(message)s",
            datefmt='%d-%b-%y %H:%M:%S'
        )
        # No local file logging — writing to a growing log file on disk
        # fills up hosting storage (e.g. Render) for no real benefit.
        # Console output is enough; Render/most hosts already capture and
        # let you view stdout/stderr in their own dashboard.
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger

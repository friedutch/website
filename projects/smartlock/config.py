import os

import resend
from itsdangerous import URLSafeTimedSerializer


SESSION_TIMEOUT = 3600
MAGIC_LINK_TTL_SECONDS = 300
HARDWARE_UNLOCK_SECONDS = 5
HARDWARE_EVENT_LOG_PATH = os.getenv(
    "SMARTLOCK_HARDWARE_EVENT_LOG",
    "/tmp/friedutchplus_smartlock_hardware_events.jsonl",
)

_serializer = None


def init_smartlock_config(secret_key):
    global _serializer
    _serializer = URLSafeTimedSerializer(secret_key)
    resend.api_key = get_resend_api_key()


def get_serializer():
    if _serializer is None:
        raise RuntimeError("Smart Lock serializer is not initialized.")
    return _serializer


def get_resend_api_key():
    return os.getenv("RESEND_API_KEY", "").strip()


def get_mail_from_address():
    return os.getenv("MAIL_FROM", "").strip()


def get_hardware_api_key():
    return os.getenv("SMARTLOCK_HARDWARE_API_KEY", "").strip()


def get_hardware_event_log_path():
    return os.getenv("SMARTLOCK_HARDWARE_EVENT_LOG", HARDWARE_EVENT_LOG_PATH)

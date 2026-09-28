import json
import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
PORT = int(os.getenv("GATEWAY_PORT", "5000"))
CLOUD_ENDPOINT = os.getenv("CLOUD_ENDPOINT", "").strip()
CLOUD_TIMEOUT_SECONDS = int(os.getenv("CLOUD_TIMEOUT_SECONDS", "5"))
RETRY_INTERVAL_SECONDS = int(os.getenv("RETRY_INTERVAL_SECONDS", "15"))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "10"))
DB_PATH = os.getenv("DB_PATH", "data/gateway.db")
LOG_PATH = os.getenv("LOG_PATH", "logs/gateway.log")
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")

try:
    DEVICE_SECRETS = json.loads(os.getenv("DEVICE_SECRETS", "{}"))
except json.JSONDecodeError:
    DEVICE_SECRETS = {}

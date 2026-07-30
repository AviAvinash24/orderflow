import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (
    f"postgresql://{os.environ['POSTGRES_USER']}:"
    f"{os.environ['POSTGRES_PASSWORD']}@"
    f"{os.environ.get('POSTGRES_HOST', 'db')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ['POSTGRES_DB']}"
)

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# How long a placed order holds stock before auto-expire
RESERVATION_MINUTES = int(os.environ.get("RESERVATION_MINUTES", "10"))

# How often the background job scans for expired reservations
EXPIRY_JOB_INTERVAL_SECONDS = int(os.environ.get("EXPIRY_JOB_INTERVAL_SECONDS", "30"))

# RQ / outbox worker
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
OUTBOX_POLL_SECONDS = int(os.environ.get("OUTBOX_POLL_SECONDS", "5"))
OUTBOX_BATCH_SIZE = int(os.environ.get("OUTBOX_BATCH_SIZE", "100"))

# Order placement rate limit (per user)
ORDER_RATE_LIMIT = int(os.environ.get("ORDER_RATE_LIMIT", "5"))
ORDER_RATE_WINDOW_SECONDS = int(os.environ.get("ORDER_RATE_WINDOW_SECONDS", "60"))
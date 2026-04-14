import os
from pathlib import Path

# Root of this package — always resolves relative to this file, not the caller
_HERE = Path(__file__).parent

# --- Database ---
# DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE_URL = "postgresql://database_test_7bbz_user:t4s49VnZPe18YM2STG4yO1tbYImbHK5K@dpg-d7ak6jruibrs739slbm0-a.oregon-postgres.render.com/database_test_7bbz"

# --- ONNX Captcha Model ---
# Place model_*.onnx inside erome_liker/weights/ when running standalone
ONNX_MODEL_PATH = Path(os.environ.get("ONNX_MODEL_PATH", str(_HERE / "weights" / "model_0.7200.onnx")))
IMG_WIDTH = 120
IMG_HEIGHT = 36
CAPTCHA_LENGTH = 4
# Place labels.json inside erome_liker/ when running standalone
LABELS_FILE = Path(os.environ.get("LABELS_FILE", str(_HERE / "labels.json")))

# --- Temp paths ---
CAPTCHA_PATH = Path(os.environ.get("CAPTCHA_PATH", "/tmp/liker_captcha.png"))

# --- Liking behaviour ---
# Only like posts uploaded more than this many seconds ago (avoid instant-like detection)
# Set to 0 for local testing, 1200 (20 min) for production
LIKE_DELAY_SECONDS = int(os.environ.get("LIKE_DELAY_SECONDS", 1200))

# Random sleep between each account like (seconds)
LIKE_SLEEP_MIN = float(os.environ.get("LIKE_SLEEP_MIN", 3))
LIKE_SLEEP_MAX = float(os.environ.get("LIKE_SLEEP_MAX", 8))

# Cookie age before considered stale and requiring re-login (seconds)
COOKIE_MAX_AGE_SECONDS = int(os.environ.get("COOKIE_MAX_AGE_SECONDS", 86400))  # 24 hours

# --- Notifications ---
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1493670069694238760/aqDmmi709RdVKQdJoZsfz3wKv1qWFAnHvX47Bk6nulleCfCFsv6EmJL2AM_FmaUHEcNp"

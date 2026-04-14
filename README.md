# erome_liker

Standalone Lambda that polls a database every 5 minutes for newly uploaded Erome albums and likes them using a pool of 10 accounts.

Completely independent from the uploader bot — the only shared resource is the database.

---

## How it works

1. **EventBridge** triggers `handler.py` every 5 minutes
2. Queries `uploaded_post` table for rows where `liked = False` and `uploaded_at` is older than `LIKE_DELAY_SECONDS` (default 20 min)
3. For each pending post, loops through all active accounts in `liker_account` table:
   - Loads stored cookies → checks if session is still valid
   - If cookies are stale → performs full login using ONNX captcha solver → saves fresh cookies back to DB
   - POSTs a like to `https://www.erome.com/album/like/{guid}`
   - Sleeps a random delay between accounts to avoid bot detection
4. Marks the post as `liked = True` in DB
5. Sends a Discord notification with the result

---

## Folder structure

```
erome_liker/
├── config.py            — all configuration (env vars with defaults)
├── db_models.py         — LikerAccount + UploadedPost SQLAlchemy models
├── erome_liker.py       — EromeLiker class (login, cookie management, like)
├── inference_liker.py   — ONNX captcha inference (self-contained)
├── handler.py           — Lambda entry point
├── init_cookies.py      — one-time script: logs in all accounts, stores cookies
├── seed_accounts.py     — one-time script: inserts your 10 accounts into DB
├── record_upload.py     — utility for manually inserting posts (testing/backfill)
├── requirements.txt
├── weights/
│   └── model_0.7200.onnx   ← copy from uploader repo
└── labels.json             ← copy from uploader repo
```

---

## Setup (one-time)

### 1. Copy required model files
```bash
cp ../weights/model_0.7200.onnx weights/
cp ../labels.json .
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set environment variables
```bash
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."  # optional
```

### 4. Add your 10 liker accounts
Edit `seed_accounts.py` with your account credentials and proxies, then run **once**:
```bash
python seed_accounts.py
```
This only needs to run once (or when adding/removing accounts).

### 5. Initialise cookies
Run **once** (or when cookies expire) to log in all accounts and store cookies:
```bash
python init_cookies.py
```
This uses the ONNX model to solve captchas and stores session cookies in the DB.
After this, the Lambda no longer needs to log in on every run — it reuses stored cookies.

---

## Running locally (testing)

```bash
# Override delay to 0 so it processes posts immediately (no 20 min wait)
export LIKE_DELAY_SECONDS=0
export DATABASE_URL="your_db_url"

python handler.py
```

---

## Deploying as AWS Lambda

1. Package the folder:
```bash
pip install -r requirements.txt -t package/
cp -r *.py weights/ labels.json package/
cd package && zip -r ../erome_liker.zip .
```

2. Upload `erome_liker.zip` to Lambda, set handler to `handler.handler`

3. Set environment variables in Lambda console:
   - `DATABASE_URL`
   - `DISCORD_WEBHOOK` (optional)
   - `LIKE_DELAY_SECONDS` (default: 1200)
   - `LIKE_SLEEP_MIN` / `LIKE_SLEEP_MAX` (default: 3 / 8)
   - `COOKIE_MAX_AGE_SECONDS` (default: 86400)

4. Create EventBridge rule: `rate(5 minutes)` → target this Lambda

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL or SQLite connection string |
| `ONNX_MODEL_PATH` | `weights/model_0.7200.onnx` | Path to ONNX captcha model |
| `LABELS_FILE` | `labels.json` | Path to captcha labels file |
| `CAPTCHA_PATH` | `/tmp/liker_captcha.png` | Temp path for captcha image |
| `LIKE_DELAY_SECONDS` | `1200` | Min age of post before liking (seconds) |
| `LIKE_SLEEP_MIN` | `3` | Min sleep between account likes (seconds) |
| `LIKE_SLEEP_MAX` | `8` | Max sleep between account likes (seconds) |
| `COOKIE_MAX_AGE_SECONDS` | `86400` | Cookie max age before re-login (seconds) |
| `DISCORD_WEBHOOK` | *(optional)* | Discord webhook URL for notifications |

---

## DB tables (managed by uploader's Alembic migrations)

**`liker_account`** — your 10 liker accounts
```
id | email | password | proxy | cookies (JSON) | cookies_updated_at | is_active
```

**`uploaded_post`** — albums uploaded by the uploader bot
```
id | album_guid | album_title | uploaded_at | liked | liked_at | like_count
```

---

## FAQ

**Does `seed_accounts.py` run on every scheduled invocation?**
No. It runs **once only** to insert your 10 accounts into the DB. After that, the Lambda picks them up automatically from the `liker_account` table on every run.

**Does `init_cookies.py` run on every invocation?**
No. It runs **once** to pre-populate cookies. After that, the Lambda reuses stored cookies and only triggers a fresh login (with ONNX) when a cookie has expired. Cookie expiry is controlled by `COOKIE_MAX_AGE_SECONDS`.

**What if a like fails for some accounts?**
The post stays `liked = False` if all accounts fail. On the next 5-minute tick, the Lambda retries automatically.

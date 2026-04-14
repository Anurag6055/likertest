"""
seed_accounts.py — One-time script to insert liker accounts into the DB.

Edit the ACCOUNTS list below with your 10 accounts, then run:
    python seed_accounts.py

Proxy format: host:port:user:password  (same as the uploader)
Set proxy to None if no proxy is needed for a particular account.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db_models import LikerAccount, SessionLocal, create_tables

# ---------------------------------------------------------------------------
# Edit this list with your 10 liker accounts
# ---------------------------------------------------------------------------
ACCOUNTS = [
    {"email": "emma.brown221@outlook.com", "password": "Codebenjy", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "synerngothe0lstq@outlook.com", "password": "sV8MYED7SjExN", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "colynsleibezdwis@outlook.com", "password": "aiCnmLZGu3jC", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "depotfpaytecx7h@outlook.com", "password": "xzkc2RPsKu4", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "jureztselvywrhlx@outlook.com", "password": "IGnsvsTnBtMuK", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "nailaysiacaui1@outlook.com", "password": "ZZUEIAWjpE", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "dubinyknehrpu4y@outlook.com", "password": "MN2NmihPGhbbr", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "mixergrichymmxj@outlook.com", "password": "EyZLTB9Y44mgB", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "reece.williams23@outlook.com", "password": "chillmike27", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "oliviaharris0105@outlook.com", "password": "sarahsmiles88", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
    {"email": "liam.bennett991@outlook.com", "password": "pixel.sophie24", "proxy": "isp.decodo.com:10002:sp1o4wkwj0:~JXPxswoaL4pge7t13"},
]
# ---------------------------------------------------------------------------


def main():
    create_tables()
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for acc_data in ACCOUNTS:
            existing = db.query(LikerAccount).filter(LikerAccount.email == acc_data["email"]).first()
            if existing:
                print(f"[SKIP] {acc_data['email']} already exists.")
                skipped += 1
                continue
            acc = LikerAccount(
                email=acc_data["email"],
                password=acc_data["password"],
                proxy=acc_data.get("proxy"),
                is_active=True,
            )
            db.add(acc)
            inserted += 1
            print(f"[ADD]  {acc_data['email']}")
        db.commit()
        print(f"\nDone: {inserted} inserted, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

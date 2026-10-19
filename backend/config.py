import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(BASE_DIR / ".env")

RIOT_API_KEY = os.environ["RIOT_API_KEY"]

ACCOUNTS_FILE = BASE_DIR / "accounts.json"
DB_PATH = BASE_DIR / "data" / "cache.db"

# Platform routing values (per-server) -> regional routing cluster used by
# account-v1 and match-v5. Only the clusters we actually use are listed.
PLATFORM_TO_REGION = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "oc1": "americas",
    "kr": "asia",
    "jp1": "asia",
    "eun1": "europe",
    "euw1": "europe",
    "tr1": "europe",
    "ru": "europe",
}


def load_accounts() -> list[dict]:
    with open(ACCOUNTS_FILE, encoding="utf-8") as f:
        accounts = json.load(f)
    for account in accounts:
        account["region"] = PLATFORM_TO_REGION[account["platform"]]
    return accounts

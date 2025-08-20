import os
import base64
import json
from typing import Tuple
import pandas as pd
import requests

CSV_PATH = os.getenv("TRACKER_CSV_PATH", "data/orders_tracker.csv")
CONFIG_PATH = os.getenv("TRACKER_CONFIG_PATH", "data/config.json")

SCHEMA = [
    "Date of eComm Request",
    "Order Number",
    "In-Correct",
    "Store - Fitment Completed",
    "Status",
    "Date Finance Updated",
    "Amount",
    "Amount Type",
    "Requested By",
    "Reason",
    "Email Subject",
    "Email Body",
    "Email Sent At",
    "Archived",
    "Last Modified By",
    "Last Modified At",
]

DEFAULT_CONFIG = {
    "duplicate_check": "pair"  # 'pair' or 'order_only'
}

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        # fill defaults
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def load_tracker() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        pd.DataFrame(columns=SCHEMA).to_csv(CSV_PATH, index=False)
    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    for c in SCHEMA:
        if c not in df.columns:
            df[c] = ""
    df = df[SCHEMA]
    return df

def save_tracker(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    cols = [c for c in SCHEMA if c in df.columns]
    df[cols].to_csv(CSV_PATH, index=False)

# --- GitHub Integration (optional) ---
def _gh_headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def github_upsert_file(owner_repo: str, path: str, content_bytes: bytes, token: str, commit_message: str = "chore: update tracker data from Streamlit") -> Tuple[bool, str]:
    """Create or update a file via GitHub Contents API. Returns (success, message)."""
    api_base = f"https://api.github.com/repos/{owner_repo}/contents/{path}"
    headers = _gh_headers(token)

    sha = None
    get_resp = requests.get(api_base, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
    elif get_resp.status_code not in (200, 404):
        return False, f"GitHub GET error: {get_resp.status_code} {get_resp.text}"

    payload = {
        "message": commit_message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": os.getenv("GITHUB_TARGET_BRANCH", "main")
    }
    if sha:
        payload["sha"] = sha

    put_resp = requests.put(api_base, headers=headers, data=json.dumps(payload))
    if put_resp.status_code in (200, 201):
        return True, "Committed to GitHub."
    else:
        return False, f"GitHub PUT error: {put_resp.status_code} {put_resp.text}"

def push_tracker_to_github() -> Tuple[bool, str]:
    owner_repo = os.getenv("GITHUB_OWNER_REPO", "")
    token = os.getenv("GITHUB_TOKEN", "")
    target_path = os.getenv("GITHUB_TARGET_PATH", "data/orders_tracker.csv")

    if not (owner_repo and token):
        return False, "GitHub env not configured. Skipping."
    try:
        df = load_tracker()
        content = df.to_csv(index=False).encode("utf-8")
        ok, msg = github_upsert_file(owner_repo, target_path, content, token)
        return ok, msg
    except Exception as e:
        return False, f"Exception during GitHub push: {e}"
# Bob Jane T-Marts — Inter-Store Transfer Tracker (Streamlit)

A lightweight, internal tracker for managing eCommerce inter-store transfer requests. Built with Streamlit, Pandas, and optional GitHub integration for daily backups and collaboration.

## Features
- Simple form to **log new requests**
- **Filter** by status, date range, and store names
- **Inline edits** with audit fields (last modified by/at)
- **Color-coded statuses** (via column config) and tooltips
- **Basic authentication** using Streamlit Secrets
- **CSV persistence** with optional **GitHub push**
- Optional **GitHub Actions** workflow for daily CSV backups

## Data Schema
| Column                      | Type         | Notes |
|----------------------------|--------------|------|
| Date of eComm Request      | date         | auto-captured or selectable |
| Order Number               | text         | required |
| In-Correct                 | text         | store ID/name |
| Store - Fitment Completed  | text         | store ID/name |
| Status                     | select       | Flagged, In-Progress, Completed |
| Date Finance Updated       | date (opt.)  | optional |
| Last Modified By           | text         | auto-filled from login |
| Last Modified At           | ISO datetime | UTC timestamp |

## Quickstart (Local)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Configure Secrets (Authentication & GitHub)
Create `.streamlit/secrets.toml`:
```toml
app_password = "replace-me"
allowed_users = ["accounts@bobjane.com.au", "finance@bobjane.com.au"]

# Optional GitHub integration
GITHUB_TOKEN = "ghp_your_token_with_repo_scope"
GITHUB_OWNER_REPO = "your-org/bjt-orders-tracker"
GITHUB_TARGET_PATH = "data/orders_tracker.csv"
GITHUB_TARGET_BRANCH = "main"
```

## Deploy on Streamlit Cloud
1. Push this repo to GitHub.
2. On Streamlit Cloud, create a new app from the repo.
3. Set **Secrets** using the contents above.
4. (Optional) Configure environment variables in Streamlit if you want to override paths.

## GitHub Actions (Daily Backup)
A workflow at `.github/workflows/daily-backup.yml` copies `data/orders_tracker.csv` into a timestamped file under `backups/` each day and pushes the change.

## Contributing
- Use feature branches and open PRs.
- Keep UI changes small and accessible for Accounts team desktop usage.
- Add tests where helpful.

## Notes
- CSV edits in Streamlit persist on the running instance. Pushing to GitHub is manual (via button) unless you add your own automation.
- Duplicate protection is based on `(Order Number, Date of eComm Request)` pair.
- For private deployments, consider adding SSO in front of the app or integrating Streamlit's community-auth packages.
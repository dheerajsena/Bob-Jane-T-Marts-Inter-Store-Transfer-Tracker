import os
import streamlit as st
import pandas as pd
from datetime import datetime, date
from utils.storage import load_tracker, save_tracker, push_tracker_to_github

APP_TITLE = "Bob Jane T-Marts — Inter-Store Transfer Tracker"
STATUS_OPTIONS = ["Flagged", "In-Progress", "Completed"]

def authenticate():
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if st.session_state.auth_ok:
        with st.sidebar:
            st.success("Authenticated")
            if st.button("Sign out"):
                st.session_state.auth_ok = False
                st.rerun()
        return True

    st.sidebar.title("Sign in")
    user = st.sidebar.text_input("Email", placeholder="name@bobjane.com.au")
    pwd = st.sidebar.text_input("Password", type="password")

    configured_pwd = st.secrets.get("app_password", None)
    allowed_users = st.secrets.get("allowed_users", [])

    if st.sidebar.button("Sign in"):
        if configured_pwd and pwd == configured_pwd and (not allowed_users or user in allowed_users):
            st.session_state.auth_ok = True
            st.session_state.user_email = user
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials.")
    st.stop()

def render_header():
    st.set_page_config(page_title=APP_TITLE, page_icon="📦", layout="wide")
    st.title(APP_TITLE)
    st.caption("Centralised view of eComm inter-store transfer requests for Accounts & E‑Commerce teams.")

def load_data():
    df = load_tracker()
    for col in [
        "Date of eComm Request",
        "Order Number",
        "In-Correct",
        "Store - Fitment Completed",
        "Status",
        "Date Finance Updated",
        "Last Modified By",
        "Last Modified At"
    ]:
        if col not in df.columns:
            df[col] = ""
    return df

def filters_ui(df: pd.DataFrame):
    with st.expander("🔎 Filters", expanded=True):
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            status = st.multiselect("Status", STATUS_OPTIONS, help="Filter by progress state.")
        with c2:
            store_incorrect = st.text_input("In‑Correct Store contains", help="Filter by part of a store name or ID.")
        with c3:
            store_fitment = st.text_input("Fitment Completed Store contains", help="Filter by part of a store name or ID.")
        with c4:
            date_range = st.date_input("eComm Request date range", value=(), help="Filter by request date.")

        q = st.text_input("Search all text", placeholder="Order number, store, etc.")

    mask = pd.Series([True]*len(df))
    if status:
        mask &= df["Status"].isin(status)
    if store_incorrect:
        mask &= df["In-Correct"].str.contains(store_incorrect, case=False, na=False)
    if store_fitment:
        mask &= df["Store - Fitment Completed"].str.contains(store_fitment, case=False, na=False)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        if start and end:
            def _parse_d(d):
                try:
                    return pd.to_datetime(d).date()
                except Exception:
                    return None
            req_dates = df["Date of eComm Request"].apply(_parse_d)
            mask &= req_dates.apply(lambda d: d is not None and start <= d <= end)
    if q:
        ql = q.lower()
        mask &= df.apply(lambda r: any(str(v).lower().find(ql) >= 0 for v in r.values), axis=1)

    return df[mask].copy()

def new_entry_form(user_email: str):
    with st.form("new_entry"):
        st.subheader("➕ Log a new transfer request")
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            req_date = st.date_input("Date of eComm Request", value=date.today(), help="When the eCommerce team raised the request.")
        with c2:
            order_num = st.text_input("Order Number", placeholder="e.g., BJ123456", help="Unique order or invoice identifier.", max_chars=50)
        with c3:
            status = st.selectbox("Status", STATUS_OPTIONS, index=0, help="Set to 'Flagged' when first created.")

        c4, c5, c6 = st.columns([1,1,1])
        with c4:
            incorrect_store = st.text_input("In‑Correct", placeholder="Store ID or name", help="The store originally assigned incorrectly.")
        with c5:
            fitment_store = st.text_input("Store - Fitment Completed", placeholder="Store ID or name", help="The store that completed the fitment.")
        with c6:
            finance_date = st.date_input("Date Finance Updated", value=None, help="Leave blank if not applicable or unknown.", format="YYYY-MM-DD")

        submitted = st.form_submit_button("Add request", use_container_width=True)
        if submitted:
            if not order_num:
                st.warning("Order Number is required.")
                return None
            return {
                "Date of eComm Request": str(req_date),
                "Order Number": order_num.strip(),
                "In-Correct": incorrect_store.strip(),
                "Store - Fitment Completed": fitment_store.strip(),
                "Status": status,
                "Date Finance Updated": str(finance_date) if finance_date else "",
                "Last Modified By": user_email,
                "Last Modified At": datetime.utcnow().isoformat(timespec="seconds") + "Z"
            }
    return None

def edit_selected_rows(df: pd.DataFrame, user_email: str):
    st.subheader("✏️ Edit selected rows")
    st.caption("Edit directly and then click 'Save changes'.")
    ed = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Status": st.column_config.SelectboxColumn(options=STATUS_OPTIONS, help="Progress state."),
            "Date of eComm Request": st.column_config.DateColumn(format="YYYY-MM-DD", help="Date eComm raised the request."),
            "Date Finance Updated": st.column_config.DateColumn(format="YYYY-MM-DD", help="Optional; when Finance updated."),
        },
        hide_index=True,
        key="data_editor",
    )

    if st.button("💾 Save changes", type="primary"):
        ed["Last Modified By"] = user_email
        ed["Last Modified At"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        save_tracker(ed)
        st.success("Saved edits.")
        return ed
    return df

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📦", layout="wide")
    render_header()
    authenticate()

    user_email = st.session_state.get("user_email", "unknown@internal")

    tabs = st.tabs([
        "📋 Tracker",
        "➕ New Entry",
        "⚙️ Admin / Export",
        "❓ Help"
    ])

    with tabs[0]:
        df = load_data()
        filtered = filters_ui(df)
        st.subheader("📦 Current Requests")
        st.caption("Use filters above to narrow results. Click a cell to edit, then 'Save changes'.")

        st.dataframe(
            filtered,
            use_container_width=True,
            column_config={
                "Status": st.column_config.TextColumn(help="Flagged / In‑Progress / Completed"),
                "In-Correct": st.column_config.TextColumn(help="Store originally assigned incorrectly."),
                "Store - Fitment Completed": st.column_config.TextColumn(help="Store that completed the fitment."),
                "Date of eComm Request": st.column_config.TextColumn(help="Date the request was created."),
                "Date Finance Updated": st.column_config.TextColumn(help="Date Finance updated (optional)."),
                "Last Modified By": st.column_config.TextColumn(help="Last editor."),
                "Last Modified At": st.column_config.TextColumn(help="UTC timestamp of last change."),
            },
            hide_index=True
        )

        st.divider()
        st.subheader("Inline Edit Mode")
        st.caption("Edit directly below, then save.")
        updated = edit_selected_rows(df, user_email)
        if len(updated) != len(df):
            save_tracker(updated)

    with tabs[1]:
        new = new_entry_form(user_email)
        if new:
            df = load_data()
            key_cols = ["Order Number", "Date of eComm Request"]
            if ((df[key_cols] == pd.Series({k:new[k] for k in key_cols})).all(axis=1)).any():
                st.warning("Duplicate: that Order Number & Date of eComm Request already exists.")
            else:
                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                save_tracker(df)
                st.success("Added new request.")

    with tabs[2]:
        st.subheader("Admin / Export")
        df = load_data()
        st.download_button("⬇️ Download CSV", data=df.to_csv(index=False), file_name="orders_tracker.csv", mime="text/csv", use_container_width=True)

        if st.button("⬆️ Push latest CSV to GitHub"):
            ok, msg = push_tracker_to_github()
            if ok:
                st.success(msg)
            else:
                st.info(msg)

        st.markdown("""**Environment variables (optional) for GitHub integration:**  
- `GITHUB_OWNER_REPO`: e.g. `your-org/bjt-orders-tracker`  
- `GITHUB_TOKEN`: Personal Access Token with `repo` scope (store in Streamlit Secrets)  
- `GITHUB_TARGET_PATH`: e.g. `data/orders_tracker.csv`  
- `GITHUB_TARGET_BRANCH`: e.g. `main`
- `TRACKER_CSV_PATH`: override local CSV location if desired
        """)

    with tabs[3]:
        st.subheader("How to use")
        st.markdown("""- Use **New Entry** to log a new transfer request.  
- **Tracker** tab lists and filters all requests. Use **Inline Edit Mode** to update statuses or fix mistakes, then click **Save changes**.  
- Status meanings:
  - **Flagged** — request created and awaiting action.
  - **In-Progress** — being processed.
  - **Completed** — fully resolved.
- **Admin / Export** lets you download a CSV snapshot and optionally push to GitHub if configured.

**Tooltips:** Hover over a field label for help on that field.

**Authentication:** Protected with a password and optional allow‑list. Configure in Streamlit Secrets:
```toml
app_password = "set-a-strong-password"
allowed_users = ["accounts@bobjane.com.au","finance@bobjane.com.au"]
GITHUB_TOKEN = "ghp_..."
```
        """)

if __name__ == "__main__":
    main()
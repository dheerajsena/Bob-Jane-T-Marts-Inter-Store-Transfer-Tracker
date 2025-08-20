import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from utils.storage import load_tracker, save_tracker, push_tracker_to_github, load_config, save_config

APP_TITLE = "Bob Jane T-Marts — Inter-Store Transfer Tracker"
STATUS_OPTIONS = ["Flagged", "In-Progress", "Completed"]
AMOUNT_TYPE_OPTIONS = ["To be Paid", "Refunded", "Partially Refunded"]
REQUESTED_BY_OPTIONS = ["eComm", "Accounts", "Store", "Other"]

# --------------------------
# Email helpers (SMTP via secrets)
# --------------------------
def email_configured():
    secrets = st.secrets
    required = ["SMTP_SERVER", "SMTP_USER", "SMTP_PASSWORD", "FROM_EMAIL", "ACCOUNTS_TO"]
    missing = [k for k in required if k not in secrets or not secrets.get(k)]
    return len(missing) == 0, missing

def send_email(subject: str, body: str, to_override: str = "") -> tuple[bool, str]:
    ok, missing = email_configured()
    if not ok:
        return False, f"Email not configured. Missing secrets: {', '.join(missing)}"

    server = st.secrets["SMTP_SERVER"]
    port = int(st.secrets.get("SMTP_PORT", 587))
    user = st.secrets["SMTP_USER"]
    pwd = st.secrets["SMTP_PASSWORD"]
    from_email = st.secrets["FROM_EMAIL"]
    to_emails = [e.strip() for e in (to_override or st.secrets["ACCOUNTS_TO"]).split(",") if e.strip()]
    cc_emails = [e.strip() for e in st.secrets.get("ACCOUNTS_CC", "").split(",") if e.strip()]

    try:
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(server, port) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(from_email, to_emails + cc_emails, msg.as_string())
        return True, "Email sent."
    except Exception as e:
        return False, f"SMTP error: {e}"

def build_email_template(template: str, amount: str, store: str, reason: str, order_no: str, greeting: str) -> tuple[str, str]:
    # Subject
    subject = "Collect Money from the Store | Credit Note"
    # Body from scenarios
    if template == "Scenario 2":
        body = f"""{greeting}

Collect Money from the Store | Credit Note

Can you please create a credit note of {amount} from {store}. Attached is the receipt. 
Reason: {reason}
"""
    elif template == "Scenario 3":
        body = f"""{greeting}

Collect Money from the Store | Credit Note

Can you please create a credit note of {amount} from {store}
Reason: {reason}
"""
    elif template == "Scenario 4":
        body = f"""{greeting}

A partial refund of {amount} has been issued to the customer.
Please note that Accounts will process the remittance of the original order amount once this job is completed. Since the adjusted order value has changed, the difference of {amount} will need to be recovered from your store.

Collect Money from the Store | Credit Note

Can you please create a credit note of {amount} from {store}
Reason: {reason}
"""
    else:
        body = f"""{greeting}

Collect Money from the Store | Credit Note

Can you please create a credit note of {amount} from {store}
Reason: {reason} Order #{order_no}
"""
    return subject, body.strip()

# --------------------------
# Authentication
# --------------------------
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

# --------------------------
# Helpers
# --------------------------
def render_header():
    st.title(APP_TITLE)
    st.caption("Centralised view of eComm inter-store transfer requests for Accounts & E-Commerce teams.")

def load_data():
   def load_data():
    df = load_tracker()

    # --- Coerce types for editor compatibility ---
    # Dates: to datetime.date (NaT allowed)
    for dc in ["Date of eComm Request", "Date Finance Updated"]:
        df[dc] = pd.to_datetime(df[dc], errors="coerce").dt.date

    # Archived: to bool (accepts strings like "true/false", "1/0", "yes/no")
    df["Archived"] = (
        df["Archived"]
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y"])
    )

    # Ensure other fields are plain strings (avoids pandas categories etc.)
    for col in [
        "Order Number", "In-Correct", "Store - Fitment Completed", "Status",
        "Amount", "Amount Type", "Requested By", "Reason",
        "Email Subject", "Email Body", "Email Sent At",
        "Last Modified By", "Last Modified At",
    ]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("")

    return df


def filters_ui(df: pd.DataFrame):
    with st.expander("🔎 Filters", expanded=True):
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            status = st.multiselect("Status", STATUS_OPTIONS, help="Filter by progress state.")
        with c2:
            store_incorrect = st.text_input("In-Correct Store contains", help="Filter by part of a store name or ID.")
        with c3:
            store_fitment = st.text_input("Fitment Completed Store contains", help="Filter by part of a store name or ID.")
        with c4:
            date_range = st.date_input("eComm Request date range", value=(), help="Filter by request date.")
        c5, c6 = st.columns([1,1])
        with c5:
            show_archived = st.checkbox("Show archived", value=False, help="Include soft-deleted records")
        with c6:
            q = st.text_input("Search all text", placeholder="Order number, store, reason, etc.")

    mask = pd.Series([True]*len(df))
    if not show_archived:
        mask &= ~df["Archived"].fillna(False)
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
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            req_date = st.date_input("Date of eComm Request", value=date.today(), help="When the eCommerce team raised the request.")
        with c2:
            order_num = st.text_input("Order Number", placeholder="e.g., BJ123456", help="Unique order or invoice identifier.", max_chars=50)
        with c3:
            status = st.selectbox("Status", STATUS_OPTIONS, index=0, help="Set to 'Flagged' when first created.")
        with c4:
            requested_by = st.selectbox("Requested By", REQUESTED_BY_OPTIONS, index=0, help="Who logged or requested this.")

        c5, c6, c7, c8 = st.columns([1,1,1,1])
        with c5:
            incorrect_store = st.text_input("In-Correct", placeholder="Store ID or name", help="The store originally assigned incorrectly.")
        with c6:
            fitment_store = st.text_input("Store - Fitment Completed", placeholder="Store ID or name", help="The store that completed the fitment.")
        with c7:
            amount = st.text_input("Amount", placeholder="$0.00", help="Dollar amount involved. Leave blank if N/A.")
        with c8:
            amount_type = st.selectbox("Amount Type", [""] + AMOUNT_TYPE_OPTIONS, index=0, help="Leave blank if N/A.")

        c9, c10 = st.columns([1,1])
        with c9:
            finance_date = st.date_input("Date Finance Updated", value=None, help="Leave blank if not applicable or unknown.", format="YYYY-MM-DD")
        with c10:
            auto_email = st.checkbox("Auto-email Accounts on submit (for eComm)", value=True if requested_by == "eComm" else False)

        # Email & Reason
        st.markdown("**Reason & Email Template (optional):**")
        t1, t2, t3, t4 = st.columns([1,1,1,1])
        with t1:
            template = st.selectbox("Template", ["Standard", "Scenario 2", "Scenario 3", "Scenario 4"], help="Choose the email wording style.")
        with t2:
            greeting = st.text_input("Greeting", value="Hi Accounts Team," if template != "Scenario 3" else "Hey Noosh,")
        with t3:
            reason = st.text_input("Reason", placeholder="e.g., Partial Refund for an order that you will be paying out today.")
        with t4:
            override_to = st.text_input("To (override)", placeholder="leave blank to use ACCOUNTS_TO secrets")

        subject_preview, body_preview = build_email_template(template, amount or "<amount>", (fitment_store or incorrect_store or "<store>"), reason or "<reason>", order_num or "<order>", greeting or "Hi Accounts Team,")
        with st.expander("📧 Email Preview"):
            st.code(f"Subject: {subject_preview}\n\n{body_preview}", language="text")

        submitted = st.form_submit_button("Add request", use_container_width=True)
        if submitted:
            if not order_num:
                st.warning("Order Number is required.")
                return None, False, "", ""

            new_row = {
                "Date of eComm Request": str(req_date) if req_date else "",
                "Order Number": order_num.strip(),
                "In-Correct": (incorrect_store or "").strip(),
                "Store - Fitment Completed": (fitment_store or "").strip(),
                "Status": status or "",
                "Date Finance Updated": str(finance_date) if finance_date else "",
                "Amount": (amount or "").strip(),
                "Amount Type": amount_type or "",
                "Requested By": requested_by or "",
                "Reason": (reason or "").strip(),
                "Email Subject": subject_preview,
                "Email Body": body_preview,
                "Email Sent At": "",
                "Archived": False,
                "Last Modified By": user_email,
                "Last Modified At": datetime.utcnow().isoformat(timespec="seconds") + "Z"
            }
            send_flag = (requested_by == "eComm") and auto_email
            return new_row, send_flag, subject_preview, (override_to or "")
    return None, False, "", ""

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
            "Amount": st.column_config.TextColumn(help="Dollar amount. e.g., $1640.26"),
            "Amount Type": st.column_config.SelectboxColumn(options=AMOUNT_TYPE_OPTIONS, help="To be Paid / Refunded / Partially Refunded"),
            "Requested By": st.column_config.SelectboxColumn(options=REQUESTED_BY_OPTIONS, help="Origin of request."),
            "Reason": st.column_config.TextColumn(help="Short reason for listing."),
            "Email Subject": st.column_config.TextColumn(help="Email subject (if used)."),
            "Email Body": st.column_config.TextColumn(help="Email body (if used)."),
            "Email Sent At": st.column_config.TextColumn(help="Timestamp when email sent."),
            "Archived": st.column_config.CheckboxColumn(help="Soft-delete / archive this record."),
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

def kpi_bar(df: pd.DataFrame):
    # compute "this week" as Monday -> today
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    def to_date(s):
        try:
            return pd.to_datetime(s).date()
        except Exception:
            return None

    completed = df[(df["Status"] == "Completed") & (df["Date Finance Updated"].apply(to_date).apply(lambda d: d is not None and start_of_week <= d <= today))]
    new_this_week = df[df["Date of eComm Request"].apply(to_date).apply(lambda d: d is not None and start_of_week <= d <= today)]
    open_now = df[(df["Status"].isin(["Flagged", "In-Progress"])) & (~df["Archived"])]
    archived = df[df["Archived"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed this week", len(completed))
    c2.metric("New this week", len(new_this_week))
    c3.metric("Open now", len(open_now))
    c4.metric("Archived", len(archived))

def analytics_section(df: pd.DataFrame):
    st.subheader("📊 Analytics")
    c1, c2 = st.columns(2)

    # Top reasons
    reasons = df["Reason"].dropna().astype(str).str.strip()
    reasons = reasons[reasons != ""]
    reason_counts = reasons.value_counts().head(10)
    with c1:
        st.markdown("**Top Reasons** (Top 10)")
        if not reason_counts.empty:
            st.bar_chart(reason_counts)
        else:
            st.info("No reasons recorded yet.")

    # Store counts
    with c2:
        st.markdown("**Stores marked as 'In-Correct' (Top 10)**")
        inc_counts = df["In-Correct"].dropna().astype(str).str.strip()
        inc_counts = inc_counts[inc_counts != ""].value_counts().head(10)
        if not inc_counts.empty:
            st.bar_chart(inc_counts)
        else:
            st.info("No 'In-Correct' store data yet.")

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**Transfers made to (Fitment Completed) — Top 10**")
        fit_counts = df["Store - Fitment Completed"].dropna().astype(str).str.strip()
        fit_counts = fit_counts[fit_counts != ""].value_counts().head(10)
        if not fit_counts.empty:
            st.bar_chart(fit_counts)
        else:
            st.info("No fitment store data yet.")

    with c4:
        # Status distribution for quick glance
        st.markdown("**Status Distribution**")
        status_counts = df["Status"].value_counts()
        if not status_counts.empty:
            st.bar_chart(status_counts)
        else:
            st.info("No status data yet.")

def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="📦", layout="wide")
    render_header()
    authenticate()

    user_email = st.session_state.get("user_email", "unknown@internal")

    tabs = st.tabs([
        "📋 Tracker",
        "➕ New Entry",
        "📧 Email Tools",
        "📊 Analytics",
        "⚙️ Admin / Export",
        "❓ Help"
    ])

    with tabs[0]:
        df = load_data()
        kpi_bar(df)
        filtered = filters_ui(df)
        st.subheader("📦 Current Requests")
        st.caption("Use filters above to narrow results. Click a cell to edit, then 'Save changes'.")

        st.dataframe(
            filtered.drop(columns=["Email Body"], errors="ignore"),
            use_container_width=True,
            column_config={
                "Status": st.column_config.TextColumn(help="Flagged / In-Progress / Completed"),
                "In-Correct": st.column_config.TextColumn(help="Store originally assigned incorrectly."),
                "Store - Fitment Completed": st.column_config.TextColumn(help="Store that completed the fitment."),
                "Date of eComm Request": st.column_config.TextColumn(help="Date the request was created."),
                "Date Finance Updated": st.column_config.TextColumn(help="Date Finance updated (optional)."),
                "Amount": st.column_config.TextColumn(help="Dollar amount involved."),
                "Amount Type": st.column_config.TextColumn(help="To be Paid / Refunded / Partially Refunded"),
                "Requested By": st.column_config.TextColumn(help="Origin of request."),
                "Reason": st.column_config.TextColumn(help="Short reason."),
                "Email Subject": st.column_config.TextColumn(help="Email subject (if used)."),
                "Email Sent At": st.column_config.TextColumn(help="Timestamp when email sent."),
                "Archived": st.column_config.TextColumn(help="Archived (soft-delete)."),
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
        new, send_flag, subj, to_override = new_entry_form(user_email)
        if new:
            df = load_data()
            cfg = load_config()
            dupe_mode = cfg.get("duplicate_check", "pair")
            if dupe_mode == "order_only":
                dup_exists = df["Order Number"].astype(str).str.strip().eq(new["Order Number"]).any()
            else:
                key_cols = ["Order Number", "Date of eComm Request"]
                dup_exists = ((df[key_cols] == pd.Series({k:new[k] for k in key_cols})).all(axis=1)).any()
            if dup_exists:
                st.warning("Duplicate detected based on current settings.")
            else:
                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                if send_flag:
                    ok, msg = send_email(new["Email Subject"], new["Email Body"], to_override)
                    if ok:
                        df.at[df.index[-1], "Email Sent At"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                        st.success("Auto-email sent to Accounts.")
                    else:
                        st.info(msg)
                save_tracker(df)
                st.success("Added new request.")

    with tabs[2]:
        st.subheader("Email Tools")
        st.caption("Generate or send emails for existing entries.")
        df = load_data()
        if df.empty:
            st.info("No entries yet.")
        else:
            selection = st.selectbox("Pick an Order Number", options=df["Order Number"].unique().tolist())
            row = df[df["Order Number"] == selection].iloc[-1].to_dict()

            st.markdown("**Completion Email (Accounts → eCommerce)**")
            complete_subject = f"Completed: Inter-Store Transfer for Order {row.get('Order Number','')}"
            amount_line = f"{row.get('Amount','')}"
            if row.get("Amount Type",""):
                amount_line += f" ({row.get('Amount Type','')})"
            complete_body = f"""Hi Dheeraj,

The inter-store transfer for Order #{row.get('Order Number','')} has been completed.

Status: {row.get('Status','')}
Amount: {amount_line}
In-Correct: {row.get('In-Correct','')}
Store - Fitment Completed: {row.get('Store - Fitment Completed','')}
Date Finance Updated: {row.get('Date Finance Updated','')}

Regards,
Accounts Team
"""
            st.code(f"Subject: {complete_subject}\n\n{complete_body}", language="text")
            if st.button("Send completion email to Dheeraj now"):
                to = st.secrets.get("ECOMMERCE_TO", "dheeraj@example.com")
                ok, msg = send_email(complete_subject, complete_body, to_override=to)
                if ok:
                    df = load_data()
                    ix = df[df["Order Number"] == selection].index[-1]
                    df.at[ix, "Email Sent At"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                    save_tracker(df)
                    st.success("Completion email sent.")
                else:
                    st.info(msg)

    with tabs[3]:
        df = load_data()
        analytics_section(df)

    with tabs[4]:
        st.subheader("Admin / Export")
        df = load_data()
        st.download_button("⬇️ Download CSV", data=df.to_csv(index=False), file_name="orders_tracker.csv", mime="text/csv", use_container_width=True)

        st.markdown("**Duplicate detection**")
        cfg = load_config()
        mode = st.radio("Choose duplicate detection mode", options=["Order + Date of Request (pair)", "Order Number only"], index=0 if cfg.get("duplicate_check","pair")=="pair" else 1, horizontal=True)
        if st.button("Save duplicate detection setting"):
            cfg["duplicate_check"] = "order_only" if "only" in mode else "pair"
            save_config(cfg)
            st.success(f"Saved duplicate detection: {cfg['duplicate_check']}")

        if st.button("⬆️ Push latest CSV to GitHub"):
            ok, msg = push_tracker_to_github()
            if ok:
                st.success(msg)
            else:
                st.info(msg)

        st.markdown("""
**Environment variables / secrets:**  
- `GITHUB_OWNER_REPO`, `GITHUB_TOKEN`, `GITHUB_TARGET_PATH`, `GITHUB_TARGET_BRANCH`, `TRACKER_CSV_PATH`, `TRACKER_CONFIG_PATH`  
- **Email (SMTP)**: `SMTP_SERVER`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL`, `ACCOUNTS_TO`, optional `ACCOUNTS_CC`, optional `ECOMMERCE_TO`
        """)

    with tabs[5]:
        st.subheader("How to use")
        st.markdown("""
- Use **New Entry** to log a new transfer request. Only **Order Number** is mandatory; other fields can be blank if not applicable.  
- **Tracker** shows KPIs, filters (including **Show archived**), and the main list.  
- **Inline Edit Mode** lets you update statuses, reasons, and toggle **Archived** (soft-delete).  
- **Auto-email:** If **Requested By = eComm** and the checkbox is on, the app sends the email shown in the preview to Accounts.
- **Email Tools** tab lets Accounts generate a **completion email** to Dheeraj when finishing a request.
- **Analytics** shows top reasons and store counts for both In-Correct and Fitment Completed.
- **Admin / Export:** download the CSV, push to GitHub, and set **Duplicate detection** to either *Order + Date* or *Order only*.
        """)

if __name__ == "__main__":
    main()

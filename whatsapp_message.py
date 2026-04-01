import os
import sqlite3
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st
from twilio.rest import Client

DB_PATH = "gst_clients.db"

# -----------------------------
# Database Functions
# -----------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firm_name TEXT NOT NULL,
            contact_name TEXT,
            mobile TEXT,
            email TEXT,
            gst_number TEXT,
            return_type TEXT NOT NULL,
            due_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def add_client(data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO clients
        (firm_name, contact_name, mobile, email, gst_number, return_type, due_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["firm_name"],
            data.get("contact_name", ""),
            data.get("mobile", ""),
            data.get("email", ""),
            data.get("gst_number", ""),
            data["return_type"],
            data["due_date"],
            data.get("notes", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()

def update_client(client_id, data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE clients
        SET firm_name = ?, contact_name = ?, mobile = ?, email = ?,
            gst_number = ?, return_type = ?, due_date = ?, notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            data["firm_name"], data.get("contact_name", ""), data.get("mobile", ""),
            data.get("email", ""), data.get("gst_number", ""), data["return_type"],
            data["due_date"], data.get("notes", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            client_id,
        ),
    )
    conn.commit()
    conn.close()

def delete_client(client_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()

def fetch_clients():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM clients ORDER BY due_date ASC", conn)
    conn.close()
    if df.empty:
        return df
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce").dt.date
    df["days_left"] = (df["due_date"] - date.today()).apply(lambda x: x.days)
    return df

def import_clients_from_dataframe(df):
    required = ["firm_name", "return_type", "due_date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    for _, row in df.iterrows():
        add_client({
            "firm_name": str(row.get("firm_name", "")).strip(),
            "contact_name": str(row.get("contact_name", "")).strip(),
            "mobile": str(row.get("mobile", "")).strip(),
            "email": str(row.get("email", "")).strip(),
            "gst_number": str(row.get("gst_number", "")).strip(),
            "return_type": str(row.get("return_type", "")).strip(),
            "due_date": pd.to_datetime(row.get("due_date")).date().isoformat(),
            "notes": str(row.get("notes", "")).strip(),
        })

# -----------------------------
# Twilio WhatsApp API Helper
# -----------------------------
def send_bulk_whatsapp(client_list, template_body):
    # Setup environment variables in your system or .env file
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_whatsapp_number = os.getenv("TWILIO_FROM_NUMBER", "whatsapp:+14155238886") # Twilio Sandbox default

    if not account_sid or not auth_token:
        return False, "Twilio credentials missing. Please set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in environment variables."

    try:
        client = Client(account_sid, auth_token)
        results = []
        for person in client_list:
            to_number = f"whatsapp:+91{person['mobile']}"
            
            # Format the message using dictionary keys
            msg_body = template_body.format(
                firm_name=person['firm_name'],
                return_type=person['return_type'],
                due_date=person['due_date'].strftime("%d-%m-%Y") if hasattr(person['due_date'], "strftime") else str(person['due_date'])
            )
            
            message = client.messages.create(
                body=msg_body,
                from_=from_whatsapp_number,
                to=to_number
            )
            results.append({"Firm Name": person['firm_name'], "Mobile": person['mobile'], "Status": "Sent ✅", "Message ID": message.sid})
        
        return True, results
    except Exception as e:
        return False, str(e)

# -----------------------------
# Email Helpers
# -----------------------------
def build_gst_request_message(firm_name, return_type, due_date, contact_name=""):
    salutation = f"Dear {contact_name}," if contact_name else f"Dear {firm_name},"
    return (
        f"{salutation}\n\n"
        f"Aapke {return_type} filing ke liye GST data pending hai.\n"
        f"Last date: {due_date}\n\n"
        f"Kripya required details/document bhej dein taaki filing time par complete ki ja sake.\n\n"
        f"Regards,\nYour CA/Tax Team"
    )

def build_gst_reminder_subject(firm_name, return_type):
    return f"GST Data Required - {firm_name} - {return_type}"

def send_email(to_email, subject, body):
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        return False, "SMTP settings missing. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD."

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Email failed: {e}"

def normalize_phone(phone):
    return str(phone).replace(" ", "").replace("-", "").replace("+91", "").strip()

def filter_due_clients(df, days_before):
    if df.empty:
        return df
    temp = df.copy()
    temp["due_date"] = pd.to_datetime(temp["due_date"], errors="coerce").dt.date
    temp = temp.dropna(subset=["due_date"])
    temp["days_left"] = (temp["due_date"] - date.today()).apply(lambda x: x.days)
    return temp[temp["days_left"] <= days_before].sort_values("due_date")


# -----------------------------
# Streamlit App UI
# -----------------------------
st.set_page_config(page_title="GST Bulk Reminder System", layout="wide")
init_db()

st.title("📊 GST Bulk Reminder System")
st.caption("Fresh client add karo, save rakho, aur ek click mein Bulk WhatsApp & Email reminders bhejo.")

with st.sidebar:
    st.header("⚙️ Settings")
    days_before = st.number_input("Reminder before days", min_value=0, max_value=60, value=3, step=1)
    st.markdown("---")
    st.info("💡 **Tip:** WhatsApp API use karne ke liye `TWILIO_ACCOUNT_SID` aur `TWILIO_AUTH_TOKEN` environment variables set karein.")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 Add Client", "📥 Import", "📋 Clients Data", "💬 Bulk WhatsApp", "📧 Send Email"
])

# -----------------------------
# Tab 1: Add Client
# -----------------------------
with tab1:
    st.subheader("Naya client add karein")
    with st.form("add_client_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            firm_name = st.text_input("Firm Name *")
            contact_name = st.text_input("Contact Person")
            mobile = st.text_input("Mobile Number (10 digits)")
        with c2:
            email = st.text_input("Email")
            gst_number = st.text_input("GST Number")
            return_type = st.selectbox("Return Type *", ["GSTR-1", "GSTR-3B", "CMP-08", "Annual Return", "Other"])
            due_date = st.date_input("Last Date of Filing *", value=date.today())

        notes = st.text_area("Notes")
        save_btn = st.form_submit_button("Save Client")

    if save_btn:
        if not firm_name.strip():
            st.error("Firm Name required hai.")
        else:
            add_client({
                "firm_name": firm_name.strip(),
                "contact_name": contact_name.strip(),
                "mobile": normalize_phone(mobile),
                "email": email.strip(),
                "gst_number": gst_number.strip(),
                "return_type": return_type,
                "due_date": due_date.isoformat(),
                "notes": notes.strip(),
            })
            st.success("Client saved successfully.")

# -----------------------------
# Tab 2: Import
# -----------------------------
with tab2:
    st.subheader("Excel/CSV se clients import karein")
    st.write("File me columns hone chahiye: `firm_name`, `contact_name`, `mobile`, `email`, `gst_number`, `return_type`, `due_date`, `notes`")
    uploaded = st.file_uploader("Upload Excel/CSV", type=["xlsx", "csv"])

    if uploaded is not None:
        try:
            if uploaded.name.endswith(".csv"):
                df_import = pd.read_csv(uploaded)
            else:
                df_import = pd.read_excel(uploaded)
            st.dataframe(df_import, use_container_width=True)

            if st.button("Import Now"):
                import_clients_from_dataframe(df_import)
                st.success("Import completed.")
        except Exception as e:
            st.error(f"Import failed: {e}")

# -----------------------------
# Tab 3: Clients Data
# -----------------------------
with tab3:
    st.subheader("Saved Clients")
    df = fetch_clients()

    if df.empty:
        st.info("Abhi koi client save nahi hua hai.")
    else:
        show_cols = ["id", "firm_name", "contact_name", "mobile", "email", "gst_number", "return_type", "due_date", "days_left", "notes"]
        st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

        st.download_button("Download Client Data CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="gst_clients.csv", mime="text/csv")

        st.markdown("### Edit / Delete Client")
        client_id = st.selectbox("Select Client ID to Edit/Delete", df["id"].tolist())
        selected = df[df["id"] == client_id].iloc[0]

        with st.form("edit_client_form"):
            e1, e2 = st.columns(2)
            with e1:
                e_firm_name = st.text_input("Firm Name", value=str(selected["firm_name"]))
                e_contact_name = st.text_input("Contact Person", value=str(selected["contact_name"] if pd.notna(selected["contact_name"]) else ""))
                e_mobile = st.text_input("Mobile Number", value=str(selected["mobile"] if pd.notna(selected["mobile"]) else ""))
            with e2:
                e_return_type = st.selectbox("Return Type", ["GSTR-1", "GSTR-3B", "CMP-08", "Annual Return", "Other"], index=["GSTR-1", "GSTR-3B", "CMP-08", "Annual Return", "Other"].index(str(selected["return_type"]) if str(selected["return_type"]) in ["GSTR-1", "GSTR-3B", "CMP-08", "Annual Return", "Other"] else "Other"))
                e_due_date = st.date_input("Last Date", value=pd.to_datetime(selected["due_date"]).date())
            update_btn = st.form_submit_button("Update Client")

        if update_btn:
            update_client(int(client_id), {
                "firm_name": e_firm_name.strip(), "contact_name": e_contact_name.strip(), "mobile": normalize_phone(e_mobile),
                "email": selected["email"], "gst_number": selected["gst_number"], "return_type": e_return_type,
                "due_date": e_due_date.isoformat(), "notes": selected["notes"]
            })
            st.success("Client updated successfully.")
            st.rerun()

        if st.button("Delete Selected Client", type="primary"):
            delete_client(int(client_id))
            st.success("Client deleted.")
            st.rerun()

# -----------------------------
# Tab 4: Bulk WhatsApp Messages
# -----------------------------
with tab4:
    st.subheader("🚀 One-Click Bulk WhatsApp (Twilio API)")
    df = fetch_clients()

    if df.empty:
        st.info("Pehle client add/import karein.")
    else:
        due_df = filter_due_clients(df, days_before)

        if due_df.empty:
            st.success(f"Khushi ki baat hai! Agle {days_before} din mein kisi ki return pending nahi hai.")
        else:
            st.write(f"**{len(due_df)} Clients pending hain:**")
            
            # 1. Multi-Select for Clients
            selected_ids = st.multiselect(
                "Clients select karein jinhe message bhejna hai:",
                options=due_df["id"].tolist(),
                default=due_df["id"].tolist(),
                format_func=lambda x: f"{due_df[due_df['id'] == x]['firm_name'].iloc[0]} ({due_df[due_df['id'] == x]['return_type'].iloc[0]})"
            )

            # 2. Template Editor
            st.markdown("### 📝 Message Template")
            st.caption("Aap in variables ka use kar sakte hain: `{firm_name}`, `{return_type}`, `{due_date}`")
            
            default_template = (
                "Dear {firm_name},\n\n"
                "Aapka {return_type} filing pending hai. Last date: {due_date} hai.\n"
                "Kripya documents jaldi bhej dein taaki penalty se bacha ja sake.\n\n"
                "Regards,\nYour CA Team"
            )
            message_template = st.text_area("Edit Template Here:", value=default_template, height=150)

            # 3. Send Logic
            if st.button("🚀 Send WhatsApp to Selected Clients", type="primary"):
                if not selected_ids:
                    st.warning("Koi client select nahi kiya gaya hai.")
                else:
                    with st.spinner("Messages bheje ja rahe hain... Kripya pratiksha karein..."):
                        to_send = due_df[due_df["id"].isin(selected_ids)].to_dict('records')
                        
                        success, result_data = send_bulk_whatsapp(to_send, message_template)
                        
                        if success:
                            st.success("Bulk Messages processing complete!")
                            st.dataframe(pd.DataFrame(result_data), use_container_width=True)
                        else:
                            st.error(f"Error: {result_data}")

# -----------------------------
# Tab 5: Email Send
# -----------------------------
with tab5:
    st.subheader("📧 Email Reminder")
    df = fetch_clients()

    if df.empty:
        st.info("Client data add karein.")
    else:
        due_df = filter_due_clients(df, days_before)
        if due_df.empty:
            st.success("Abhi email bhejne ke liye koi due client nahi hai.")
        else:
            sel_id = st.selectbox("Client select karein", due_df["id"].tolist(), format_func=lambda x: due_df[due_df['id'] == x]['firm_name'].iloc[0])
            row = due_df[due_df["id"] == sel_id].iloc[0]

            due_date_str = row["due_date"].strftime("%d-%m-%Y") if hasattr(row["due_date"], "strftime") else str(row["due_date"])
            subject = build_gst_reminder_subject(str(row["firm_name"]), str(row["return_type"]))
            body = build_gst_request_message(
                firm_name=str(row["firm_name"]), return_type=str(row["return_type"]),
                due_date=due_date_str, contact_name=str(row["contact_name"]) if pd.notna(row["contact_name"]) else ""
            )

            st.text_input("Subject", value=subject, key="subject_view")
            st.text_area("Body", value=body, height=180, key="body_view")

            if st.button("Send Email Now"):
                email_to = str(row["email"]).strip()
                if not email_to or email_to == "nan":
                    st.error("Is client ka email missing hai.")
                else:
                    with st.spinner("Email bhej rahe hain..."):
                        ok, detail = send_email(email_to, subject, body)
                        if ok:
                            st.success(detail)
                        else:
                            st.error(detail)

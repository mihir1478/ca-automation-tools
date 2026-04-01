import streamlit as st
import pandas as pd
import io
from datetime import datetime

st.title("📝 GST Registration - Master Draft Form")
st.write("Portal par entry karne se pehle yahan saara data aaram se fill karein. Submit karne par ek Excel file banegi jahan se aap direct Copy-Paste kar sakte hain.")

# ==========================================
# 🚀 GST FORM UI
# ==========================================
with st.form("gst_draft_form"):
    
    st.subheader("🏢 1. Business Details (Part A & B)")
    col1, col2 = st.columns(2)
    with col1:
        legal_name = st.text_input("Legal Name of Business (As per PAN)")
        trade_name = st.text_input("Trade Name")
        pan_no = st.text_input("PAN Number", max_chars=10)
        constitution = st.selectbox("Constitution of Business", ["Proprietorship", "Partnership", "Private Limited Company", "Public Limited Company", "LLP", "HUF", "Others"])
    with col2:
        reason_reg = st.selectbox("Reason to Obtain Registration", ["Crossing the Threshold", "Voluntary Basis", "Inter-State Supply", "E-Commerce Operator", "Death of Proprietor", "Others"])
        commencement_date = st.date_input("Date of Commencement of Business", value=None)
        liability_date = st.date_input("Date on which liability to register arises", value=None)
        jurisdiction = st.text_input("State / Center Jurisdiction (Ward/Circle/Sector)")

    st.markdown("---")
    
    st.subheader("👤 2. Promoter / Partner / Director Details")
    col3, col4 = st.columns(2)
    with col3:
        promoter_name = st.text_input("Full Name (First, Middle, Last)")
        father_name = st.text_input("Father's Name")
        dob = st.date_input("Date of Birth", value=None, min_value=datetime(1930, 1, 1))
        gender = st.selectbox("Gender", ["Male", "Female", "Other"])
        designation = st.text_input("Designation / Status (e.g., Proprietor, Director)")
    with col4:
        mobile = st.text_input("Mobile Number", max_chars=10)
        email = st.text_input("Email Address")
        promoter_pan = st.text_input("Promoter's PAN Number", max_chars=10)
        aadhaar = st.text_input("Aadhaar Number", max_chars=12)
        din = st.text_input("DIN (If Company)", help="Director Identification Number")
    
    promoter_address = st.text_area("Residential Address (Building, Street, City, PIN, State)")

    st.markdown("---")

    st.subheader("📍 3. Principal Place of Business (PPOB)")
    col5, col6 = st.columns(2)
    with col5:
        ppob_address = st.text_area("PPOB Full Address (Building, Street, City, PIN, State)")
        ppob_email = st.text_input("PPOB Official Email")
        ppob_phone = st.text_input("PPOB Office Phone Number")
    with col6:
        nature_possession = st.selectbox("Nature of Possession of Premises", ["Owned", "Rented", "Leased", "Consent", "Shared", "Others"])
        proof_document = st.selectbox("Proof of PPOB Document", ["Electricity Bill", "Rent / Lease Agreement", "Consent Letter", "Property Tax Receipt", "Municipal Khata Copy"])
        nature_activity = st.multiselect("Nature of Business Activity", ["Factory / Manufacturing", "Wholesale Business", "Retail Business", "Warehouse / Depot", "Service Provision", "Office / Sale Office", "E-Commerce", "Works Contract"])

    st.markdown("---")

    st.subheader("📦 4. HSN / SAC Codes (Top 5)")
    hsn1 = st.text_input("Item 1: HSN/SAC Code & Description")
    hsn2 = st.text_input("Item 2: HSN/SAC Code & Description")
    hsn3 = st.text_input("Item 3: HSN/SAC Code & Description")
    hsn4 = st.text_input("Item 4: HSN/SAC Code & Description")
    hsn5 = st.text_input("Item 5: HSN/SAC Code & Description")

    st.markdown("---")

    st.subheader("🗺️ 5. State Specific Information")
    col7, col8 = st.columns(2)
    with col7:
        pt_ec_no = st.text_input("Professional Tax Employee Certificate (EC) No.")
        pt_rc_no = st.text_input("Professional Tax Registration Certificate (RC) No.")
    with col8:
        excise_no = st.text_input("State Excise License No.")

    # Form Submit Button
    submit_btn = st.form_submit_button("💾 Save & Generate Excel", type="primary")

# ==========================================
# 💻 DATA PROCESSING & EXCEL GENERATION
# ==========================================
if submit_btn:
    with st.spinner("Excel file ban rahi hai..."):
        
        # Formating Data Vertically for Easy Copy-Pasting
        gst_data = {
            "--- 1. BUSINESS DETAILS ---": "",
            "Legal Name of Business": legal_name,
            "Trade Name": trade_name,
            "PAN Number": pan_no,
            "Constitution of Business": constitution,
            "Reason to Obtain Registration": reason_reg,
            "Date of Commencement": commencement_date.strftime('%d-%m-%Y') if commencement_date else "",
            "Liability Date": liability_date.strftime('%d-%m-%Y') if liability_date else "",
            "Jurisdiction (Ward/Circle)": jurisdiction,
            
            "--- 2. PROMOTER DETAILS ---": "",
            "Promoter Full Name": promoter_name,
            "Father's Name": father_name,
            "Date of Birth": dob.strftime('%d-%m-%Y') if dob else "",
            "Gender": gender,
            "Designation / Status": designation,
            "Mobile Number": mobile,
            "Email Address": email,
            "Promoter PAN": promoter_pan,
            "Aadhaar Number": aadhaar,
            "DIN": din,
            "Residential Address": promoter_address,
            
            "--- 3. PPOB DETAILS ---": "",
            "PPOB Full Address": ppob_address,
            "PPOB Email": ppob_email,
            "PPOB Phone": ppob_phone,
            "Nature of Possession": nature_possession,
            "Proof of PPOB Document": proof_document,
            "Nature of Business Activity": ", ".join(nature_activity),
            
            "--- 4. HSN / SAC CODES ---": "",
            "HSN 1": hsn1,
            "HSN 2": hsn2,
            "HSN 3": hsn3,
            "HSN 4": hsn4,
            "HSN 5": hsn5,

            "--- 5. STATE SPECIFIC INFO ---": "",
            "PT Employee Certificate (EC) No.": pt_ec_no,
            "PT Registration Certificate (RC) No.": pt_rc_no,
            "State Excise License No.": excise_no
        }

        # Convert dictionary to DataFrame (2 Columns: Field Name, Value)
        df = pd.DataFrame(list(gst_data.items()), columns=["GST Portal Field", "Client Data"])

        # Create Excel in Memory
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name="GST_Draft_Data")
            
            # Auto-adjust column width for better readability
            worksheet = writer.sheets["GST_Draft_Data"]
            worksheet.column_dimensions['A'].width = 40
            worksheet.column_dimensions['B'].width = 60

        excel_bytes = excel_buffer.getvalue()

        st.success("✅ Data saved! Niche diye gaye button se Excel download karein.")
        
        st.download_button(
            label="📥 Download GST Draft Excel",
            data=excel_bytes,
            file_name=f"GST_Draft_{trade_name.replace(' ', '_')}.xlsx" if trade_name else "GST_Draft_Data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

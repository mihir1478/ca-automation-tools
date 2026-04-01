import streamlit as st
import pandas as pd
import json
import re

st.set_page_config(page_title="GST Refund Automator", page_icon="🧾", layout="wide")
st.title("🧾 GST Refund JSON (Live Editor Mode)")
st.markdown("Yeh app aapki Tally Excel ko read kargi. **Niche di gayi table mein jo bhi Shipping ya EGM details missing hain, aap unhe seedha yahan click karke type kar sakte hain!**")
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    gstin_input = st.text_input("GSTIN", value="27AACFB8280B1ZP").strip()
with col2:
    from_fp_input = st.text_input("From Period (MMYYYY)", value="012025").strip()
with col3:
    to_fp_input = st.text_input("To Period (MMYYYY)", value="092025").strip()

st.markdown("---")
uploaded_file = st.file_uploader("Upload your Tally/Speqta Excel File", type=["xlsx", "xls"])

# ==========================================
# ☢️ DATA CLEANERS (Tally ka kachra saaf karne ke liye)
# ==========================================
def nuke_string(val):
    if pd.isna(val) or str(val).strip().lower() in ['nan', '']: return ""
    return re.sub(r'[\n\r\t\xa0\u200B]', '', str(val)).strip()

def nuke_invoice_no(val):
    val = nuke_string(val)
    if not val: return ""
    return re.sub(r'[^a-zA-Z0-9\-/]', '', val)

def nuke_port_code(val):
    val = nuke_string(val)
    if not val: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', val).upper()

def nuke_sb_number(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    try:
        val = str(int(float(val))) 
    except:
        val = nuke_string(val)
    return re.sub(r'[^0-9]', '', val) 

def nuke_date(val):
    if pd.isna(val) or str(val).strip() == "": return ""
    try:
        dt = pd.to_datetime(val, dayfirst=True)
        return dt.strftime('%d-%m-%Y')
    except:
        val = nuke_string(val)
        return re.sub(r'[^0-9\-]', '', val)[:10]

def nuke_amount(val):
    if pd.isna(val): return 0
    try:
        val_str = nuke_string(val).replace(',', '')
        f_val = float(re.sub(r'[^\d.]', '', val_str)) 
        return int(f_val) if f_val.is_integer() else round(f_val, 2)
    except:
        return 0

def is_date_in_period(date_str, from_fp, to_fp):
    try:
        d_m, d_y = int(date_str[3:5]), int(date_str[6:])
        f_m, f_y = int(from_fp[:2]), int(from_fp[2:])
        t_m, t_y = int(to_fp[:2]), int(to_fp[2:])
        return ((f_y * 12) + f_m) <= ((d_y * 12) + d_m) <= ((t_y * 12) + t_m)
    except:
        return False

# ==========================================
# 🚀 MAIN APP LOGIC
# ==========================================
if uploaded_file is not None:
    try:
        # Excel read karna
        df = pd.read_excel(uploaded_file, sheet_name='GSTR-1-1A_Export', skiprows=4)
        
        # Sirf Export without payment wale filter karna
        if 'Type Of Export' in df.columns:
            valid_types = ['export without payment of gst', 'export without payment of tax']
            df = df[df['Type Of Export'].astype(str).str.strip().str.lower().isin(valid_types)]

        # Agar data blank hai toh rok do
        if df.empty:
            st.warning("Is sheet mein koi Export Without Payment ka data nahi mila.")
            st.stop()

        # ==========================================
        # 📝 EDITABLE DATA PREPARATION
        # ==========================================
        st.markdown("### ✍️ Fill Missing Details Below:")
        st.info("💡 Hint: Kisi bhi box (cell) par double-click karein aur missing Port Code, Shipping Bill, ya EGM type karein. Date format **DD-MM-YYYY** rakhna hai.")

        # Ek nayi clean table banana user ke edit karne ke liye
        edit_df = pd.DataFrame()
        edit_df['Invoice No'] = df['Invoice No'].apply(nuke_invoice_no)
        edit_df['Invoice Date'] = df['Invoice Date'].apply(nuke_date)
        edit_df['Invoice Value'] = df['Invoice Value'].apply(nuke_amount)
        
        # Shipping details fetch karna (agar hain toh theek, warna blank)
        edit_df['Port Code'] = df.get('Shipping Bill Port Code', pd.Series([""] * len(df))).apply(nuke_port_code)
        edit_df['Shipping Bill No'] = df.get('Shipping bill/ bill of export No', pd.Series([""] * len(df))).apply(nuke_sb_number)
        edit_df['Shipping Bill Date'] = df.get('Shipping bill/ bill of export Date', pd.Series([""] * len(df))).apply(nuke_date)
        
        # EGM details hamesha blank columns add karna taaki user bhar sake
        edit_df['EGM Ref No'] = df.get('EGM Ref Number', pd.Series([""] * len(df))).apply(nuke_sb_number)
        edit_df['EGM Date'] = df.get('EGM Ref Date', pd.Series([""] * len(df))).apply(nuke_date)

        # Blank rows hatana
        edit_df = edit_df[edit_df['Invoice No'] != ""]

        # Streamlit ka Editable Table
        edited_df = st.data_editor(edit_df, use_container_width=True, num_rows="dynamic")

        st.markdown("---")

        # ==========================================
        # ⚙️ JSON GENERATION FROM EDITED TABLE
        # ==========================================
        if st.button("🚀 Validate & Generate JSON", type="primary"):
            with st.spinner("Portal Rules check ho rahe hain..."):
                
                json_payload = {
                    "gstin": nuke_invoice_no(gstin_input),
                    "fromFp": re.sub(r'\D', '', from_fp_input),
                    "toFp": re.sub(r'\D', '', to_fp_input),
                    "refundRsn": "EXPWOP",
                    "version": "3.0",
                    "stmt03": []
                }

                sno = 1
                rejected_invoices = []

                # Ab hum original df ki jagah user dwara edit ki gayi table (edited_df) se data lenge
                for index, row in edited_df.iterrows():
                    inv_no = str(row['Invoice No']).strip()
                    inv_date = nuke_date(row['Invoice Date'])
                    invoice_val = float(row['Invoice Value'])
                    
                    sb_port_code = nuke_port_code(row['Port Code'])
                    sb_num = nuke_sb_number(row['Shipping Bill No'])
                    sb_date = nuke_date(row['Shipping Bill Date'])
                    
                    egm_ref = nuke_sb_number(row['EGM Ref No'])
                    egm_date = nuke_date(row['EGM Date'])

                    errors = []

                    # Validations
                    if not is_date_in_period(inv_date, from_fp_input, to_fp_input):
                        errors.append(f"Date {inv_date} is out of period")
                    if not sb_port_code or not sb_num or not sb_date:
                        errors.append("Missing Shipping details (Check Table)")
                    if len(sb_port_code) != 6 and sb_port_code != "":
                        errors.append("Port Code must be 6 chars")
                    if not (3 <= len(sb_num) <= 7) and sb_num != "":
                        errors.append("Shipping Bill must be 3-7 digits")
                    if not egm_ref or not egm_date:
                        errors.append("Missing EGM Details (Portal requires this)")

                    if len(errors) > 0:
                        rejected_invoices.append({"Invoice No": inv_no, "Error": " | ".join(errors)})
                        continue

                    # BASE SCHEMA
                    invoice_data = {
                        "sno": sno,
                        "docType": "Invoice",
                        "inum": inv_no,
                        "idt": inv_date,
                        "val": invoice_val,
                        "type": "G",
                        "sbpcode": sb_port_code,
                        "sbnum": sb_num,
                        "sbdt": sb_date,
                        "egmref": egm_ref,
                        "egmrefdt": egm_date,
                        "fobValue": invoice_val
                    }

                    json_payload["stmt03"].append(invoice_data)
                    sno += 1

                # Results Display
                if len(rejected_invoices) > 0:
                    st.error(f"⚠️ {len(rejected_invoices)} Invoices mein abhi bhi galti hai (Niche table check karein):")
                    st.dataframe(pd.DataFrame(rejected_invoices), use_container_width=True)

                if (sno - 1) > 0:
                    st.success(f"✅ {sno-1} Invoices 100% portal rules se pass ho gaye!")
                    
                    json_string = json.dumps(json_payload, ensure_ascii=True, separators=(',', ':'))
                    
                    st.download_button(
                        label="⬇️ Download Portal-Ready JSON",
                        data=json_string.encode('utf-8'),
                        file_name="Refund_Ready_Live_Edit.json",
                        mime="application/json",
                        type="primary"
                    )
                else:
                    st.warning("Koi bhi valid data nahi bacha. Kripya upar table mein sabhi Shipping aur EGM details sahi bharein.")

    except Exception as e:
        st.error(f"❌ Error: Kripya file format check karein. Detail: {e}")

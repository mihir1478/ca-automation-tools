import io, re
import pandas as pd
import streamlit as st
import pdfplumber
from PIL import Image
import pytesseract
import requests
import xmltodict

# --- Page Config ---
st.set_page_config(page_title="Bank Statement to Tally API", layout="wide")
st.title("🏦 Smart Bank Statement → Tally API Converter")

# ==========================================
# ⚙️ TALLY API CONFIGURATION & FETCHER
# ==========================================
TALLY_URL = "http://localhost:9000"

# Sidebar: Tally Settings
st.sidebar.header("⚙️ Tally Connectivity")
COMPANY_NAME = st.sidebar.text_input("Company Name in Tally", value="GLOBAL SALES")

@st.cache_data(ttl=60) # 1 minute tak cache karega taaki baar-baar fetch na kare
def get_tally_ledgers(company):
    """Tally se live ledgers fetch karne ka function"""
    xml_payload = f"""<ENVELOPE>
        <HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>
        <BODY>
            <EXPORTDATA>
                <REQUESTDESC>
                    <REPORTNAME>List of Accounts</REPORTNAME>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                        <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
                    </STATICVARIABLES>
                </REQUESTDESC>
            </EXPORTDATA>
        </BODY>
    </ENVELOPE>"""
    try:
        response = requests.post(TALLY_URL, data=xml_payload, timeout=5)
        if response.status_code == 200:
            raw_xml = response.text
            # Clean invalid characters
            clean_xml = re.sub(r'&#x[0-1]?[0-9A-Fa-f];', '', raw_xml)
            clean_xml = re.sub(r'&#[0-3]?[0-9];', '', clean_xml)
            
            data_dict = xmltodict.parse(clean_xml)
            messages = data_dict.get('ENVELOPE', {}).get('BODY', {}).get('IMPORTDATA', {}).get('REQUESTDATA', {}).get('TALLYMESSAGE', [])
            if not isinstance(messages, list): messages = [messages]
            
            ledgers = []
            for msg in messages:
                if 'LEDGER' in msg:
                    ledger = msg['LEDGER']
                    if isinstance(ledger, list):
                        ledgers.extend([l.get('@NAME', '') for l in ledger])
                    else:
                        ledgers.append(ledger.get('@NAME', ''))
            return [l for l in ledgers if l] # Remove empty strings
        return []
    except:
        return []

# Live Tally Ledgers fetch karna
with st.spinner("Tally se Ledgers fetch ho rahe hain..."):
    tally_live_ledgers = get_tally_ledgers(COMPANY_NAME)

if tally_live_ledgers:
    st.sidebar.success(f"✅ Tally Connected! ({len(tally_live_ledgers)} Ledgers Found)")
    BANK_LEDGER = st.sidebar.selectbox("Select Target Bank Ledger", [""] + tally_live_ledgers, index=0)
else:
    st.sidebar.error("❌ Tally Disconnected. Kripya Tally open karein aur Company name check karein.")
    BANK_LEDGER = "PRIME CO-OP BANK LTD." # Fallback

# --- Sidebar for Smart Ledger Mapping (CSV) ---
st.sidebar.markdown("---")
st.sidebar.header("📂 Custom Mapping (Optional)")
mapping_file = st.sidebar.file_uploader("Upload Mapping CSV", type=["csv"])
mapping_dict = {}
if mapping_file:
    try:
        mapping_df = pd.read_csv(mapping_file)
        mapping_dict = {str(row['Keyword']).strip().upper(): str(row['Ledger Name']).strip() 
                        for _, row in mapping_df.iterrows() if pd.notna(row['Keyword'])}
    except Exception as e:
        st.sidebar.error("CSV format sahi nahi hai.")

# ==========================================
# 📝 REGEX & PARSING LOGIC (Aapka Original Code)
# ==========================================
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}")
DATE_DATE_RE = re.compile(r"^(?P<trn>\d{2}-\d{2}-\d{4})\s+(?P<value>\d{2}-\d{2}-\d{4})\s+(?P<body>.+)$")
OPEN_RE   = re.compile(r"^\d{2}-\d{2}-\d{4}\s+OPENING BALANCE", re.IGNORECASE)
CLOSE_RE  = re.compile(r"^\d{2}-\d{2}-\d{4}\s+CLOSING BALANCE", re.IGNORECASE)
AMT_RE    = re.compile(r"\d[\d,]*\.\d{2}") 

SKIP_PREFIXES = ("Account Statement From", "Statement from", "TRN. Date", "Page ", "Mobile Banking App.", "hence no signature required")

def clean_line(txt): return re.sub(r"\s+", " ", txt).strip()

def is_noise_line(txt):
    low = txt.lower().strip()
    if not low: return True
    if any(low.startswith(pref.lower()) for pref in SKIP_PREFIXES): return True
    if re.match(r'^\d{9,}\s*-\s*', txt): return True
    return False

def extract_lines_from_pdf(uploaded_file):
    lines = []
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or not text.strip():
                img = page.to_image(resolution=300).original
                text = pytesseract.image_to_string(Image.fromarray(img))
            for ln in text.splitlines():
                ln = clean_line(ln)
                if ln and not is_noise_line(ln): lines.append(ln)
    return lines

def group_lines_to_blocks(lines):
    blocks = []
    curr = []
    for ln in lines:
        if DATE_RE.match(ln) and (DATE_DATE_RE.match(ln) or OPEN_RE.match(ln) or CLOSE_RE.match(ln)):
            if curr: blocks.append(curr)
            curr = [ln]
        else:
            if curr: curr.append(ln)
    if curr: blocks.append(curr)
    return blocks

def parse_amount(s):
    try: return float(s.replace(",", ""))
    except: return None

def extract_ref_and_narr(s):
    tokens = s.split()
    ref, ref_idx = "", -1
    for i, tok in reversed(list(enumerate(tokens))):
        if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", tok) or re.fullmatch(r"\d{5,}", tok):  
            ref, ref_idx = tok, i
            break
    if ref and ref_idx != -1:
        tokens.pop(ref_idx) 
        s = " ".join(tokens).strip() 
    return ref, s

def predict_ledger(narration, m_dict, live_ledgers):
    """🚀 SMART MAPPING ENGINE"""
    narr_upper = narration.upper()
    
    # Priority 1: Check in User's Custom CSV Mapping
    for keyword, ledger in m_dict.items():
        if keyword in narr_upper: return ledger
            
    # Priority 2: Auto-Match with Tally's Live Ledgers (API Magic)
    # Narration me Tally ka direct ledger name dhundna
    for ledger in live_ledgers:
        if len(ledger) > 3 and ledger.upper() in narr_upper: # >3 to avoid short matches like "TO" or "IN"
            return ledger
            
    # Fallback
    return "Suspense"

def parse_block(block, prev_balance=None):
    joined = clean_line(" ".join(block))
    if OPEN_RE.match(joined) or CLOSE_RE.match(joined): return None, prev_balance 
    m = DATE_DATE_RE.match(joined)
    if not m: return None, prev_balance
        
    trn_date, value_date, body = m.group("trn"), m.group("value"), m.group("body").strip()
    amts = AMT_RE.findall(body)
    if not amts: return None, prev_balance
        
    closing_bal = amts[-1]
    txn_amt = amts[-2] if len(amts) >= 2 else ""
    
    narration = body
    if closing_bal: narration = narration[::-1].replace(closing_bal[::-1], "", 1)[::-1]
    if txn_amt: narration = narration[::-1].replace(txn_amt[::-1], "", 1)[::-1]

    narration = clean_line(re.sub(r'\b0\b', '', narration))
    ref_no, narration = extract_ref_and_narr(narration)

    debit = credit = ""
    curr_bal_val = parse_amount(closing_bal)
    txn_val = parse_amount(txn_amt)
    
    if prev_balance is not None and curr_bal_val is not None and txn_val is not None:
        if curr_bal_val < prev_balance: debit = txn_amt
        elif curr_bal_val > prev_balance: credit = txn_amt
        else:
            if any(k in narration.upper() for k in [" BY ", "INFLOW", "CREDIT", "SALARY", "IMPS", "NEFT BY"]): credit = txn_amt
            else: debit = txn_amt
    else:
        if any(k in narration.upper() for k in [" BY ", "INFLOW", "CREDIT", "SALARY", "IMPS", "NEFT BY"]): credit = txn_amt
        else: debit = txn_amt

    # Use the upgraded Smart Mapper
    party_ledger = predict_ledger(narration, mapping_dict, tally_live_ledgers)

    return {
        "TRN Date": trn_date, "Value Date": value_date, "Narration": narration,
        "Chq/Ref.No": ref_no, "Debit": debit, "Credit": credit,
        "Party Ledger": party_ledger, "Closing Bal": closing_bal
    }, curr_bal_val

def convert_pdf_to_df(pdf_file):
    lines = extract_lines_from_pdf(pdf_file)
    blocks = group_lines_to_blocks(lines)
    rows = []
    prev_bal = None
    for blk in blocks:
        row, prev_bal = parse_block(blk, prev_bal)
        if row: rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty: return df
    df = df[~df["Narration"].str.upper().isin(["OPENING BALANCE", "CLOSING BALANCE"])]
    df = df[["TRN Date", "Value Date", "Narration", "Chq/Ref.No", "Debit", "Credit", "Party Ledger", "Closing Bal"]]
    return df

# ==========================================
# 📝 TALLY VOUCHER XML GENERATOR
# ==========================================
def generate_tally_xml(df, company_name, bank_ledger):
    xml_parts = []
    xml_parts.append(f"""<ENVELOPE>
 <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
 <BODY>
  <IMPORTDATA>
   <REQUESTDESC>
    <REPORTNAME>Vouchers</REPORTNAME>
    <STATICVARIABLES><SVCURRENTCOMPANY>{str(company_name).replace("&", "&amp;")}</SVCURRENTCOMPANY></STATICVARIABLES>
   </REQUESTDESC>
   <REQUESTDATA>""")

    for index, row in df.iterrows():
        date_str = str(row["TRN Date"])
        if pd.notna(date_str) and len(date_str) >= 10 and date_str.lower() != "nan":
            d, m, y = date_str[:2], date_str[3:5], date_str[6:10]
            tally_date = f"{y}{m}{d}"
        else: continue

        raw_narr = row["Narration"]
        narration = "" if pd.isna(raw_narr) else str(raw_narr).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        raw_party = row.get("Party Ledger", "")
        party_ledger = "Suspense" if pd.isna(raw_party) or str(raw_party).strip() == "" else str(raw_party).strip().replace("&", "&amp;")
        
        # XML break na ho isliye Bank Ledger ko bhi clean karo
        clean_bank_ledger = str(bank_ledger).replace("&", "&amp;")

        debit_val, credit_val = row["Debit"], row["Credit"]

        if pd.notna(debit_val) and str(debit_val).strip() != "" and str(debit_val).lower() != "nan":
            vch_type, amt = "Payment", f"{parse_amount(str(debit_val)):.2f}"
            party_is_deemed, party_amt = "Yes", f"-{amt}"
            bank_is_deemed, bank_amt = "No", amt
        elif pd.notna(credit_val) and str(credit_val).strip() != "" and str(credit_val).lower() != "nan":
            vch_type, amt = "Receipt", f"{parse_amount(str(credit_val)):.2f}"
            party_is_deemed, party_amt = "No", amt
            bank_is_deemed, bank_amt = "Yes", f"-{amt}"
        else: continue

        raw_ref = row["Chq/Ref.No"]
        ref_no = "" if pd.isna(raw_ref) or str(raw_ref).strip().lower() == "nan" else str(raw_ref).strip()
        vch_number = str(index + 1)

        xml_parts.append(f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="{vch_type}" ACTION="Create" OBJVIEW="Accounting Voucher View">
      <DATE>{tally_date}</DATE>
      <NARRATION>{narration}</NARRATION>
      <VOUCHERTYPENAME>{vch_type}</VOUCHERTYPENAME>
      <PARTYLEDGERNAME>{party_ledger}</PARTYLEDGERNAME>
      <VOUCHERNUMBER>{vch_number}</VOUCHERNUMBER>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>{party_ledger}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>{party_is_deemed}</ISDEEMEDPOSITIVE>
       <AMOUNT>{party_amt}</AMOUNT>
      </ALLLEDGERENTRIES.LIST>
      <ALLLEDGERENTRIES.LIST>
       <LEDGERNAME>{clean_bank_ledger}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>{bank_is_deemed}</ISDEEMEDPOSITIVE>
       <AMOUNT>{bank_amt}</AMOUNT>
       <BANKALLOCATIONS.LIST>
        <DATE>{tally_date}</DATE>
        <INSTRUMENTDATE>{tally_date}</INSTRUMENTDATE>
        <TRANSACTIONTYPE>{'Cheque' if ref_no else 'e-Fund Transfer'}</TRANSACTIONTYPE>
        <PAYMENTFAVOURING>{party_ledger}</PAYMENTFAVOURING>
        <INSTRUMENTNUMBER>{ref_no}</INSTRUMENTNUMBER>
        <AMOUNT>{bank_amt}</AMOUNT>
       </BANKALLOCATIONS.LIST>
      </ALLLEDGERENTRIES.LIST>
     </VOUCHER>
    </TALLYMESSAGE>""")

    xml_parts.append("""   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>""")
    return "".join(xml_parts)

# ==========================================
# 🖥️ STREAMLIT UI WORKFLOW
# ==========================================
uploaded = st.file_uploader("Upload Bank Statement PDF", type=["pdf"])

if uploaded:
    if not BANK_LEDGER:
        st.warning("⚠️ Kripya Sidebar se Target Bank Ledger select karein.")
        st.stop()
        
    if "parsed_df" not in st.session_state or st.session_state.get("last_uploaded") != uploaded.name:
        with st.spinner("Processing PDF and applying Smart Match..."):
            st.session_state.parsed_df = convert_pdf_to_df(uploaded)
            st.session_state.last_uploaded = uploaded.name

    df = st.session_state.parsed_df

    if df.empty:
        st.error("No transactions parsed. Check if the PDF is scanned (OCR mode needed).")
    else:
        st.success(f"Parsed {len(df)} transactions. Smart Mapper ne Tally Ledgers se auto-match karne ki koshish ki hai!")
        
        # 🚀 TALLY DROP DOWN MAGIC 
        # Streamlit Column config use karke Party Ledger ko Dropdown banaya gaya hai
        column_config = {}
        if tally_live_ledgers:
            column_config["Party Ledger"] = st.column_config.SelectboxColumn(
                "Party Ledger (Tally Links)", 
                help="Select ledger directly from Tally",
                width="medium",
                options=["Suspense"] + tally_live_ledgers,
                required=True
            )
            
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic", column_config=column_config)
        
        st.write("---")
        col1, col2, col3 = st.columns([1, 1, 1])
        
        # Generate files based on edited_df
        excel_output = io.BytesIO()
        with pd.ExcelWriter(excel_output, engine="openpyxl") as writer:
            edited_df.to_excel(writer, index=False, sheet_name="Transactions")
        excel_output.seek(0)
        
        vouchers_xml_str = generate_tally_xml(edited_df, COMPANY_NAME, BANK_LEDGER)
        xml_output = io.BytesIO(vouchers_xml_str.encode("utf-8"))
        
        with col1:
            st.download_button("⬇️ Excel Download", data=excel_output, file_name="bank_statement.xlsx")
        with col2:
            st.download_button("⬇️ XML Download", data=xml_output, file_name="tally_bank_import.xml", mime="application/xml")
            
        # 🚀 DIRECT PUSH TO TALLY
        with col3:
            if st.button("🚀 Push to Tally", type="primary"):
                with st.spinner("Tally mein Bank Entries ho rahi hain..."):
                    try:
                        response = requests.post(TALLY_URL, data=vouchers_xml_str.encode("utf-8"))
                        if response.status_code == 200:
                            res_text = response.text
                            if "<LINEERROR>" in res_text:
                                st.error("❌ Tally ne data reject kar diya (Master Missing ya Tally Mode Error).")
                                errors = re.findall(r'<LINEERROR>(.*?)</LINEERROR>', res_text)
                                for err in set(errors): st.write(f"👉 **{err.replace('&apos;', '')}**")
                            elif "<CREATED>" in res_text:
                                st.success(f"🎉 Success! Saari bank entries '{BANK_LEDGER}' mein push ho gayi hain.")
                                st.balloons()
                            else:
                                st.warning("Tally Response clear nahi hai. Kripya Tally check karein.")
                        else:
                            st.error(f"HTTP Error {response.status_code}")
                    except Exception as e:
                        st.error("❌ Tally se connect nahi ho pa raha. Kya Tally open hai?")

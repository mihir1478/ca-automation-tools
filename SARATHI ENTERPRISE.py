import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(layout="wide") # Page layout ko wide banaya
st.title("📄 Sarathi Enterprise - Sales PDF to XML")
st.write("Apni Sarathi Enterprise ki Sales Invoices yahan upload karein. Data verify/edit karein aur Excel aur Tally XML generate karein.")

# ==========================================
# ⚙️ CONFIGURATION & HELPERS
# ==========================================
COMPANY_NAME = "SARATHI ENTERPRISE FIRM" 
SELLER_GSTIN = "24AFNFS6943Q1ZO" 

state_codes = {
    '01': 'Jammu & Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab', '04': 'Chandigarh', 
    '05': 'Uttarakhand', '06': 'Haryana', '07': 'Delhi', '08': 'Rajasthan', '09': 'Uttar Pradesh', 
    '10': 'Bihar', '11': 'Sikkim', '12': 'Arunachal Pradesh', '13': 'Nagaland', '14': 'Manipur', 
    '15': 'Mizoram', '16': 'Tripura', '17': 'Meghalaya', '18': 'Assam', '19': 'West Bengal', 
    '20': 'Jharkhand', '21': 'Odisha', '22': 'Chhattisgarh', '23': 'Madhya Pradesh', '24': 'Gujarat', 
    '26': 'Dadra and Nagar Haveli and Daman and Diu', '27': 'Maharashtra', '28': 'Andhra Pradesh', 
    '29': 'Karnataka', '30': 'Goa', '31': 'Lakshadweep', '32': 'Kerala', '33': 'Tamil Nadu', 
    '34': 'Puducherry', '35': 'Andaman and Nicobar Islands', '36': 'Telangana', '37': 'Andhra Pradesh', 
    '38': 'Ladakh'
}

def clean_number(val):
    if not val: return ""
    clean_val = str(val).replace(',', '').strip()
    parts = clean_val.split('.')
    if len(parts) > 2:
        clean_val = "".join(parts[:-1]) + "." + parts[-1]
    return clean_val

def get_state(gstin):
    if pd.isna(gstin) or len(str(gstin)) < 2: return "Gujarat"
    return state_codes.get(str(gstin)[:2], "Gujarat")

# ==========================================
# 📄 PDF EXTRACTION LOGIC
# ==========================================
def parse_sarathi_enterprise(pdf_file_obj):
    data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        g_inv_no, g_inv_date, g_party_name, g_party_gstin = "", "", "", ""
        
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            text_layout = page.extract_text(layout=True)
            if not text: continue
            
            # --- Headers Extraction ---
            inv_match = re.search(r"Invoice No\.?\s*:\s*([A-Za-z0-9/-]+)", text, re.IGNORECASE)
            if inv_match: g_inv_no = inv_match.group(1).strip()
            
            date_match = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
            if date_match: g_inv_date = date_match.group(1).strip()
            
            # --- Party Name ---
            party_match = None
            lines_layout = text_layout.split('\n')
            for line in lines_layout:
                if "M/s." in line or "M/s" in line:
                    party_match = re.search(r"M/s\.?\s*:\s*([^\n]+)", line, re.IGNORECASE)
                    break
            if not party_match:
                party_match = re.search(r"M/s\.?\s*:\s*([^\n]+)", text, re.IGNORECASE)
                
            if party_match:
                raw_party = party_match.group(1).strip()
                clean_party = re.split(r'(?i)\s{3,}|\binvoice\b|\bdate\b', raw_party)[0].strip()
                g_party_name = re.sub(r'[,.\s\-]+$', '', clean_party)
            
            # --- Party GSTIN ---
            gstin_matches = re.findall(r"GSTIN No\.\s*:\s*(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9])", text, re.IGNORECASE)
            for g in gstin_matches:
                if g.upper() != SELLER_GSTIN:
                    g_party_gstin = g.upper()
                    break

            # --- Row Fuser (Y-coordinate logic) ---
            words = sorted(page.extract_words(keep_blank_chars=False), key=lambda w: w['top'])
            rows = []
            for w in words:
                wc = (w['top'] + w['bottom']) / 2
                if rows and (min(x['top'] for x in rows[-1]) - 4) <= wc <= (max(x['bottom'] for x in rows[-1]) + 4):
                    rows[-1].append(w)
                else:
                    rows.append([w])

            # --- Extract Items & Calc Taxes ---
            items = []
            for row in rows:
                clean_line = " ".join([w['text'] for w in sorted(row, key=lambda w: (w['x0'] + w['x1'])/2)])
                tokens = clean_line.split()
                
                if len(tokens) >= 7 and tokens[0].isdigit():
                    try:
                        amt_raw = clean_number(tokens[-1])
                        gst_pct_raw = clean_number(tokens[-2])
                        rate_raw = clean_number(tokens[-3])
                        qty_raw = clean_number(tokens[-4])
                        hsn_raw = tokens[-5]
                        item_name = " ".join(tokens[1:-5])
                        
                        float(amt_raw)
                        float(rate_raw)
                        float(qty_raw)
                    except ValueError:
                        continue 
                    
                    taxable_amt = float(amt_raw)
                    gst_pct = float(gst_pct_raw)
                    total_tax = taxable_amt * (gst_pct / 100)
                    
                    igst_amt, cgst_amt, sgst_amt = "", "", ""
                    if g_party_gstin.startswith("24"):
                        cgst_amt = f"{round(total_tax / 2, 2):.2f}"
                        sgst_amt = f"{round(total_tax / 2, 2):.2f}"
                    else:
                        igst_amt = f"{round(total_tax, 2):.2f}"
                        
                    gst_rate_str = str(int(gst_pct)) if gst_pct.is_integer() else str(gst_pct)

                    items.append({
                        "Voucher Date": g_inv_date, 
                        "Voucher Type": "Sales", 
                        "Voucher Number": g_inv_no,
                        "Party Name": g_party_name, 
                        "Party GSTIN": g_party_gstin,
                        "Item Name": item_name, 
                        "HSN/SAC": hsn_raw,
                        "Billed Qty": qty_raw, 
                        "UOM": "Mtrs", 
                        "Rate": rate_raw,
                        "GST %": gst_rate_str if gst_rate_str != "0" else "", 
                        "Amount": amt_raw,
                        "IGST Amount": igst_amt,
                        "CGST Amount": cgst_amt, 
                        "SGST Amount": sgst_amt, 
                        "Total Invoice Value": "" 
                    })
            data.extend(items)
            
    # --- GLOBAL ROUNDED TOTAL ENGINE ---
    invoice_totals = {}
    for item in data:
        inv = item["Voucher Number"]
        if inv not in invoice_totals: invoice_totals[inv] = 0.0
        invoice_totals[inv] += float(item["Amount"] or 0) + float(item["CGST Amount"] or 0) + float(item["SGST Amount"] or 0) + float(item["IGST Amount"] or 0)
        
    for item in data:
        inv = item["Voucher Number"]
        item["Total Invoice Value"] = f"{round(invoice_totals[inv]):.2f}"
            
    return data

# ==========================================
# 💻 TALLY XML GENERATION LOGIC
# ==========================================
def generate_xml_from_df(df):
    df_xml = df.copy()
    
    # Cleaning
    num_cols = ['Amount', 'CGST Amount', 'SGST Amount', 'IGST Amount', 'Rate', 'Billed Qty', 'GST %']
    for col in num_cols:
        if col in df_xml.columns:
            df_xml[col] = pd.to_numeric(df_xml[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    if 'Voucher Date' in df_xml.columns:
        df_xml['Voucher Date'] = pd.to_datetime(df_xml['Voucher Date'], dayfirst=True, errors='coerce').dt.strftime('%Y%m%d')

    xml_data = f"""<ENVELOPE>
 <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
 <BODY>
  <IMPORTDATA>
   <REQUESTDESC>
    <REPORTNAME>Vouchers</REPORTNAME>
    <STATICVARIABLES><SVCURRENTCOMPANY>{COMPANY_NAME}</SVCURRENTCOMPANY></STATICVARIABLES>
   </REQUESTDESC>
   <REQUESTDATA>
"""
    for vch_no, group in df_xml.groupby('Voucher Number'):
        if pd.isna(vch_no) or str(vch_no).strip() == "": 
            continue # Skip row if voucher number is completely empty after editing

        row = group.iloc[0]
        p_gstin = str(row['Party GSTIN']).strip() if pd.notna(row['Party GSTIN']) else ""
        p_state = get_state(p_gstin)
        p_name = str(row['Party Name']).strip() if pd.notna(row['Party Name']) else ""
        
        taxable = group['Amount'].sum()
        cgst = group['CGST Amount'].sum()
        sgst = group['SGST Amount'].sum()
        igst = group['IGST Amount'].sum()
        
        total_raw = taxable + cgst + sgst + igst
        grand_total = round(total_raw)
        round_off = round(grand_total - total_raw, 2)

        # Voucher Header - Item Invoice
        xml_data += f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Invoice Voucher View">
      <DATE>{row['Voucher Date']}</DATE>
      <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
      <VOUCHERNUMBER>{vch_no}</VOUCHERNUMBER>
      <PARTYLEDGERNAME>{p_name}</PARTYLEDGERNAME>
      <PARTYNAME>{p_name}</PARTYNAME>
      <PARTYGSTIN>{p_gstin}</PARTYGSTIN>
      <STATENAME>{p_state}</STATENAME>
      <PLACEOFSUPPLY>{p_state.upper()}</PLACEOFSUPPLY>
      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
      <ISINVOICE>Yes</ISINVOICE>
      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
      <VCHGSTSTATUSISINCLUDED>Yes</VCHGSTSTATUSISINCLUDED>
      <ISBOENOTAPPLICABLE>Yes</ISBOENOTAPPLICABLE>
      <ISGSTOVERRIDDEN>Yes</ISGSTOVERRIDDEN>
"""
        # Items Loop
        for _, i_row in group.iterrows():
            hsn = str(i_row['HSN/SAC']).split('.')[0]
            gst_val = int(i_row['GST %']) if float(i_row['GST %']).is_integer() else i_row['GST %']
            item_name = f"{hsn}@{gst_val}%"

            # --- UOM Ignored: Only numerical qty ---
            xml_data += f"""      <ALLINVENTORYENTRIES.LIST>
       <STOCKITEMNAME>{item_name}</STOCKITEMNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
       <RATE>{i_row['Rate']:.2f}</RATE>
       <AMOUNT>{i_row['Amount']:.2f}</AMOUNT>
       <BILLEDQTY>{i_row['Billed Qty']:.3f}</BILLEDQTY>
       <ACTUALQTY>{i_row['Billed Qty']:.3f}</ACTUALQTY>
       <ACCOUNTINGALLOCATIONS.LIST>
        <LEDGERNAME>SALES</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{i_row['Amount']:.2f}</AMOUNT>
       </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>
"""
        # Party Ledger
        xml_data += f"""      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{p_name}</LEDGERNAME>
       <GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
       <AMOUNT>-{grand_total:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>
"""
        # Tax Ledgers
        for t_name, t_amt in [("CGST", cgst), ("SGST", sgst), ("IGST", igst)]:
            if t_amt > 0:
                xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>{t_name}</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{t_amt:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""

        # Round Off
        if round_off != 0:
            is_pos = "Yes" if round_off < 0 else "No"
            xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>ROUND OFF</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>{is_pos}</ISDEEMEDPOSITIVE><AMOUNT>{round_off:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""

        xml_data += "     </VOUCHER>\n    </TALLYMESSAGE>\n"

    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""
    return xml_data

# ==========================================
# 🚀 UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload SARATHI ENTERPRISE PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Extract Data from PDFs", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_data = []
            
            for pdf_file in uploaded_pdfs:
                try:
                    extracted = parse_sarathi_enterprise(pdf_file)
                    if extracted:
                        all_data.extend(extracted)
                except Exception as e:
                    st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_data:
                # 1. Create DataFrame
                df = pd.DataFrame(all_data)
                cols = ["Voucher Date", "Voucher Type", "Voucher Number", "Party Name", "Party GSTIN", "Item Name", "HSN/SAC", "Billed Qty", "UOM", "Rate", "GST %", "Amount", "IGST Amount", "CGST Amount", "SGST Amount", "Total Invoice Value"]
                df = df.reindex(columns=cols)
                
                # Save into session state
                st.session_state['sarathi_df'] = df
                st.success(f"✅ Success! {len(uploaded_pdfs)} PDF files processed successfully.")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

# Check if data exists in session state to show the interactive table
if 'sarathi_df' in st.session_state:
    df = st.session_state['sarathi_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields
    empty_vouchers = df[df['Voucher Number'].isna() | (df['Voucher Number'] == "")]
    empty_parties = df[df['Party Name'].isna() | (df['Party Name'] == "")]
    empty_totals = df[df['Total Invoice Value'].isna() | (df['Total Invoice Value'] == "") | (df['Total Invoice Value'] == "0.00")]
    
    if not empty_vouchers.empty or not empty_parties.empty or not empty_totals.empty:
        st.warning("⚠️ **DHYAN DEIN:** Kuch invoices mein Voucher No, Party Name ya Amount theek se extract nahi hua hai. Kripya niche table mein double-click karke theek karein.")
    else:
        st.info("💡 Aap niche diye gaye table mein kisi bhi cell par double-click karke data edit kar sakte hain.")
    
    # Editable Dataframe
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    st.markdown("---")
    st.subheader("💾 Download Final Files")
    st.write("Upar kiye gaye changes automatically niche download hone waali files mein apply ho jayenge.")
    
    # 2. Generate Excel in Memory based on Edited DataFrame
    excel_buffer = io.BytesIO()
    edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_bytes = excel_buffer.getvalue()
    
    # 3. Generate XML String based on Edited DataFrame
    xml_string = generate_xml_from_df(edited_df.copy())
    
    # Download Buttons
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Edited Excel", 
            data=excel_bytes, 
            file_name="Sarathi_Enterprise_Final.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="📥 Download Tally XML", 
            data=xml_string, 
            file_name="Sarathi_Enterprise_ItemInvoice.xml", 
            mime="application/xml"
        )

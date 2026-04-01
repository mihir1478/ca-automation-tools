import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import requests

st.set_page_config(layout="wide", page_title="Mihira Fabric Automation") 

# ==========================================
# ⚙️ TALLY CONFIGURATION & HELPERS
# ==========================================
COMPANY_NAME = "MIHIRA FABRIC" 
SELLER_GST = "24DGGPS3046M1Z1"
TALLY_URL = "http://localhost:9000"

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

def get_state(gstin):
    if pd.isna(gstin) or len(str(gstin)) < 2: return "Gujarat"
    return state_codes.get(str(gstin)[:2], "Gujarat")

def escape_xml(text):
    """Tally XML ko crash hone se bachane ke liye special characters theek karna"""
    if pd.isna(text): return ""
    return str(text).strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

# ==========================================
# 📝 AUTO-CREATE *ALL MASTERS* XML LOGIC (ALTER MODE)
# ==========================================
def generate_masters_xml(df):
    df_xml = df.copy()
    
    if 'IGST Amount' not in df_xml.columns: df_xml['IGST Amount'] = 0
    num_cols = ['Taxable Value', 'CGST Amount', 'SGST Amount', 'IGST Amount']
    for col in num_cols:
        if col in df_xml.columns:
            df_xml[col] = pd.to_numeric(df_xml[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    xml_data = f"""<ENVELOPE>
     <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
     <BODY>
      <IMPORTDATA>
       <REQUESTDESC>
        <REPORTNAME>All Masters</REPORTNAME>
        <STATICVARIABLES><SVCURRENTCOMPANY>{escape_xml(COMPANY_NAME)}</SVCURRENTCOMPANY></STATICVARIABLES>
       </REQUESTDESC>
       <REQUESTDATA>\n"""

    # --- 1. CREATE UNITS OF MEASURE (UOM) ---
    if 'Unit' in df_xml.columns:
        unique_uoms = df_xml['Unit'].dropna().unique()
        for uom in unique_uoms:
            uom_str = escape_xml(uom)
            if not uom_str: continue
            xml_data += f"""        <TALLYMESSAGE xmlns:UDF="TallyUDF">
             <UNIT NAME="{uom_str}" ACTION="Alter">
              <NAME>{uom_str}</NAME>
              <ISSIMPLEUNIT>Yes</ISSIMPLEUNIT>
             </UNIT>
            </TALLYMESSAGE>\n"""

    # --- 2. CREATE COMMON LEDGERS ---
    common_ledgers = [
        ("SALES", "Sales Accounts"), ("CGST", "Duties & Taxes"), 
        ("SGST", "Duties & Taxes"), ("IGST", "Duties & Taxes"), 
        ("ROUND OFF", "Indirect Expenses")
    ]
    for l_name, l_group in common_ledgers:
        xml_data += f"""        <TALLYMESSAGE xmlns:UDF="TallyUDF">
         <LEDGER NAME="{l_name}" ACTION="Alter">
          <NAME.LIST><NAME>{l_name}</NAME></NAME.LIST>
          <PARENT>{l_group}</PARENT>
         </LEDGER>
        </TALLYMESSAGE>\n"""

    # --- 3. CREATE PARTY LEDGERS ---
    unique_parties = df_xml.drop_duplicates(subset=['Party A/c Name'])
    for _, row in unique_parties.iterrows():
        p_name = escape_xml(row['Party A/c Name'])
        if not p_name or p_name.lower() == 'nan': continue 
            
        p_gstin = escape_xml(row.get('Party GSTIN', ''))
        p_state = escape_xml(get_state(row.get('Party GSTIN', '')))

        xml_data += f"""        <TALLYMESSAGE xmlns:UDF="TallyUDF">
         <LEDGER NAME="{p_name}" ACTION="Alter">
          <NAME.LIST><NAME>{p_name}</NAME></NAME.LIST>
          <PARENT>Sundry Debtors</PARENT>
          <STATENAME>{p_state}</STATENAME>
          <PARTYGSTIN>{p_gstin}</PARTYGSTIN>
          <ISBILLWISEON>Yes</ISBILLWISEON>
         </LEDGER>
        </TALLYMESSAGE>\n"""

    # --- 4. CREATE STOCK ITEMS ---
    items_dict = {}
    for _, row in df_xml.iterrows():
        item_taxable = row.get('Taxable Value', 0)
        item_tax = row.get('CGST Amount', 0) + row.get('SGST Amount', 0) + row.get('IGST Amount', 0)
        
        gst_val = int(round((item_tax / item_taxable) * 100)) if item_taxable > 0 else 0
        hsn = escape_xml(str(row.get('HSN/SAC Code', '')).split('.')[0])
        item_name = f"{hsn}@{gst_val}%"
        uom = escape_xml(row.get('Unit', 'PCS')) or "PCS"
        
        if item_name not in items_dict:
            items_dict[item_name] = uom

    for i_name, i_uom in items_dict.items():
        if not i_name or i_name == "@0%": continue
        xml_data += f"""        <TALLYMESSAGE xmlns:UDF="TallyUDF">
         <STOCKITEM NAME="{i_name}" ACTION="Alter">
          <NAME.LIST><NAME>{i_name}</NAME></NAME.LIST>
          <PARENT>Primary</PARENT>
          <BASEUNITS>{i_uom}</BASEUNITS>
         </STOCKITEM>
        </TALLYMESSAGE>\n"""

    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""
    return xml_data


# ==========================================
# 📄 MAIN PAGE: PDF EXTRACTION LOGIC
# ==========================================
st.title("📄 Mihira Fabric - Bulletproof Auto Tally API")
st.write("Ab Masters fail hone ka koi chance nahi! Upload karein aur Push dabayein.")

def parse_mihira_pdf(pdf_file_obj):
    tally_data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            
            if not text or "DELIVERY CHALLAN" in text.upper(): continue
                
            inv_no_match = re.search(r'Invoice No[\s:]+(\d+)', text, re.IGNORECASE)
            inv_no = inv_no_match.group(1) if inv_no_match else ""
            
            date_match = re.search(r'Date[\s:]*(\d{2}-\d{2}-\d{4})', text, re.IGNORECASE)
            inv_date = date_match.group(1) if date_match else ""

            all_gsts = re.findall(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}', text)
            party_gst = next((gst for gst in all_gsts if gst != SELLER_GST), "")

            party_name = ""
            if "NEELMADHAV LIFESTYLE" in text: party_name = "NEELMADHAV LIFESTYLE"
            elif "PARVATI SURAT MILLS" in text: party_name = "PARVATI SURAT MILLS"
            elif "SHRISHTI FASHION" in text: party_name = "SHRISHTI FASHION"
            elif "DEV SHREE TEXTILES" in text: party_name = "DEV SHREE TEXTILES"
            elif "GOPANGANA NX" in text: party_name = "GOPANGANA NX"
            else:
                party_match = re.search(r'M/s:[\s",]*([A-Za-z\s]+?)(?:\\n|Add:|City:|GST|")', text)
                if party_match: party_name = party_match.group(1).strip()

            item_name, hsn, qty, uom, rate = "", "", "", "", ""
            item_match = re.search(r'(P[\*]?.*?\s*63)\s*[\n]*\s*(\d{4})\s*[\n]*\s*\d+\s*[\n]*\s*\d+\s*[\n]*\s*([\d\.]+)\s*[\n]*\s*(MTR|PCS)\s*[\n]*\s*([\d\.]+)', text)
            
            if item_match:
                item_name = " ".join(item_match.group(1).split()) 
                hsn, qty, uom, rate = item_match.group(2).strip(), item_match.group(3).strip(), item_match.group(4).strip(), item_match.group(5).strip()
            else:
                 fallback_match = re.search(r'1\s*[\n]*\s*([A-Za-z\*\s]+?\d*)\s*[\n]*\s*(\d{4})\s*[\n]*\s*.*?([\d\.]+)\s*[\n]*\s*(MTR|PCS)\s*[\n]*\s*([\d\.]+)', text)
                 if fallback_match:
                     item_name = " ".join(fallback_match.group(1).split()) 
                     hsn, qty, uom, rate = fallback_match.group(2).strip(), fallback_match.group(3).strip(), fallback_match.group(4).strip(), fallback_match.group(5).strip()

            taxable_match = re.search(r'Taxable Value[\s:]*([\d\.]+)', text, re.IGNORECASE)
            taxable_val = taxable_match.group(1) if taxable_match else "0.00"

            cgst_match = re.search(r'CGST\s*(?:2\.5%)?\s*([\d\.]+)', text)
            cgst_val = cgst_match.group(1) if cgst_match else "0.00"

            sgst_match = re.search(r'SGST\s*(?:2\.5%)?\s*([\d\.]+)', text)
            sgst_val = sgst_match.group(1) if sgst_match else "0.00"

            total_match = re.search(r'Invoice Total[\s:]*([\d\.]+)', text, re.IGNORECASE)
            total_val = total_match.group(1) if total_match else "0.00"

            if inv_no or party_name: 
                tally_data.append({
                    "Voucher Date": inv_date, "Voucher No": inv_no, "Party A/c Name": party_name,
                    "Party GSTIN": party_gst, "Item Name": item_name, "HSN/SAC Code": hsn,
                    "Billed Qty": qty, "Unit": uom, "Rate": rate,
                    "Taxable Value": float(taxable_val) if taxable_val else 0.00,
                    "CGST Amount": float(cgst_val) if cgst_val else 0.00,
                    "SGST Amount": float(sgst_val) if sgst_val else 0.00,
                    "IGST Amount": 0.00, "Total Invoice Amount": float(total_val) if total_val else 0.00
                })
    return tally_data

# ==========================================
# 📝 TALLY VOUCHER XML GENERATION LOGIC
# ==========================================
def generate_xml_from_df(df):
    df_xml = df.copy()
    if 'IGST Amount' not in df_xml.columns: df_xml['IGST Amount'] = 0
    num_cols = ['Taxable Value', 'CGST Amount', 'SGST Amount', 'IGST Amount', 'Rate', 'Billed Qty', 'Total Invoice Amount']
    for col in num_cols:
        if col in df_xml.columns:
            df_xml[col] = pd.to_numeric(df_xml[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    if 'Voucher Date' in df_xml.columns:
        df_xml['Voucher Date'] = pd.to_datetime(df_xml['Voucher Date'], dayfirst=True, errors='coerce').dt.strftime('%Y%m%d')

    xml_data = f"<ENVELOPE>\n <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>\n <BODY>\n  <IMPORTDATA>\n   <REQUESTDESC>\n    <REPORTNAME>Vouchers</REPORTNAME>\n    <STATICVARIABLES><SVCURRENTCOMPANY>{escape_xml(COMPANY_NAME)}</SVCURRENTCOMPANY></STATICVARIABLES>\n   </REQUESTDESC>\n   <REQUESTDATA>\n"
    
    for vch_no, group in df_xml.groupby('Voucher No'):
        if pd.isna(vch_no) or str(vch_no).strip() == "": continue 

        row = group.iloc[0]
        p_name = escape_xml(row['Party A/c Name'])
        p_gstin = escape_xml(row['Party GSTIN'])
        p_state = escape_xml(get_state(row['Party GSTIN']))
        
        taxable = group['Taxable Value'].sum()
        cgst = group['CGST Amount'].sum()
        sgst = group['SGST Amount'].sum()
        igst = group['IGST Amount'].sum()
        total_raw = taxable + cgst + sgst + igst
        grand_total = round(total_raw)
        round_off = round(grand_total - total_raw, 2)

        xml_data += f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Invoice Voucher View">
      <DATE>{row['Voucher Date']}</DATE>
      <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
      <VOUCHERNUMBER>{vch_no}</VOUCHERNUMBER>
      <PARTYLEDGERNAME>{p_name}</PARTYLEDGERNAME>
      <PARTYNAME>{p_name}</PARTYNAME>
      <PARTYGSTIN>{p_gstin}</PARTYGSTIN>
      <STATENAME>{p_state}</STATENAME>
      <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
      <PLACEOFSUPPLY>{p_state.upper()}</PLACEOFSUPPLY>
      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
      <ISINVOICE>Yes</ISINVOICE>
      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
      <VCHGSTSTATUSISINCLUDED>Yes</VCHGSTSTATUSISINCLUDED>
      <ISBOENOTAPPLICABLE>Yes</ISBOENOTAPPLICABLE>
      <ISGSTOVERRIDDEN>Yes</ISGSTOVERRIDDEN>\n"""
      
        for _, i_row in group.iterrows():
            item_taxable = i_row['Taxable Value']
            item_tax = i_row['CGST Amount'] + i_row['SGST Amount'] + i_row['IGST Amount']
            gst_val = int(round((item_tax / item_taxable) * 100)) if item_taxable > 0 else 0
            hsn = str(i_row['HSN/SAC Code']).split('.')[0]
            item_name = escape_xml(f"{hsn}@{gst_val}%")

            xml_data += f"""      <ALLINVENTORYENTRIES.LIST>
       <STOCKITEMNAME>{item_name}</STOCKITEMNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
       <RATE>{i_row['Rate']:.2f}</RATE>
       <AMOUNT>{i_row['Taxable Value']:.2f}</AMOUNT>
       <BILLEDQTY>{i_row['Billed Qty']}</BILLEDQTY>
       <ACTUALQTY>{i_row['Billed Qty']}</ACTUALQTY>
       <ACCOUNTINGALLOCATIONS.LIST>
        <LEDGERNAME>SALES</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{i_row['Taxable Value']:.2f}</AMOUNT>
       </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>\n"""
      
        xml_data += f"""      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{p_name}</LEDGERNAME>
       <GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
       <AMOUNT>-{grand_total:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>\n"""
      
        for t_name, t_amt in [("CGST", cgst), ("SGST", sgst), ("IGST", igst)]:
            if t_amt > 0:
                xml_data += f"      <LEDGERENTRIES.LIST><LEDGERNAME>{t_name}</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{t_amt:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"

        if round_off != 0:
            is_pos = "Yes" if round_off < 0 else "No"
            xml_data += f"      <LEDGERENTRIES.LIST><LEDGERNAME>ROUND OFF</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>{is_pos}</ISDEEMEDPOSITIVE><AMOUNT>{round_off:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"

        xml_data += "     </VOUCHER>\n    </TALLYMESSAGE>\n"

    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""
    return xml_data

# ==========================================
# 🖥️ UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload MIHIRA FABRIC PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Extract Data from PDFs", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_data = []
            for pdf_file in uploaded_pdfs:
                try:
                    extracted = parse_mihira_pdf(pdf_file)
                    if extracted: all_data.extend(extracted)
                except Exception as e: st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_data:
                st.session_state['raw_df'] = pd.DataFrame(all_data)
                st.success(f"✅ Success! {len(uploaded_pdfs)} PDF files processed.")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

if 'raw_df' in st.session_state:
    df = st.session_state['raw_df']
    st.markdown("---")
    
    empty_vouchers = df[df['Voucher No'].isna() | (df['Voucher No'] == "")]
    if not empty_vouchers.empty:
        st.warning("⚠️ Kuch invoices mein Data theek se extract nahi hua hai. Kripya niche table mein double-click karke theek karein.")
        
    st.info("💡 **Tip for Educational Mode:** Table mein double-click karke sabhi Dates ko '01-02-2026' ya '02-02-2026' kar dein, varna entry nahi hogi!")
    
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    st.markdown("---")
    
    excel_buffer = io.BytesIO()
    edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_bytes = excel_buffer.getvalue()
    
    vouchers_xml_string = generate_xml_from_df(edited_df.copy())
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("⬇️ Download Excel", excel_bytes, "Mihira_Fabric_Final.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with col2:
        st.download_button("⬇️ Download Tally XML", vouchers_xml_string, "Mihira_Fabric_Vouchers.xml", "application/xml")
        
    # ==========================================
    # 🚀 TWO-STEP AUTO PUSH LOGIC (MASTERS -> VOUCHERS)
    # ==========================================
    with col3:
        if st.button("🚀 Push EVERYTHING to Tally"):
            
            # STEP 1: PUSH ALL MASTERS
            with st.spinner("Step 1: Tally mein missing Masters Check/Create ho rahe hain..."):
                masters_xml = generate_masters_xml(edited_df)
                try:
                    master_res = requests.post(TALLY_URL, data=masters_xml.encode('utf-8'))
                    
                    if master_res.status_code == 200:
                        master_text = master_res.text
                        
                        # Tally se stats nikalna
                        created_match = re.search(r'<CREATED>(\d+)</CREATED>', master_text)
                        altered_match = re.search(r'<ALTERED>(\d+)</ALTERED>', master_text)
                        errors_match = re.search(r'<ERRORS>(\d+)</ERRORS>', master_text)
                        
                        created_c = int(created_match.group(1)) if created_match else 0
                        altered_c = int(altered_match.group(1)) if altered_match else 0
                        errors_c = int(errors_match.group(1)) if errors_match else 0

                        if "<LINEERROR>" in master_text:
                            st.error(f"❌ Step 1: Masters (Ledgers/Items) create karte time Tally ne reject kar diya! ({errors_c} Errors)")
                            errors = re.findall(r'<LINEERROR>(.*?)</LINEERROR>', master_text)
                            for err in set(errors): st.write(f"👉 **{err.replace('&apos;', '')}**")
                            
                            with st.expander("Show Tally's Full Master Response"):
                                st.code(master_text)
                        else:
                            st.toast(f"✅ Step 1 Done: {created_c} New Created, {altered_c} Updated.")
                            
                            # STEP 2: PUSH VOUCHERS 
                            with st.spinner("Step 2: Ab Vouchers Tally mein push ho rahe hain..."):
                                vch_res = requests.post(TALLY_URL, data=vouchers_xml_string.encode('utf-8'))
                                
                                if vch_res.status_code == 200:
                                    v_text = vch_res.text
                                    if "<LINEERROR>" in v_text:
                                        st.error("❌ Step 2: Vouchers Push me Error aayi.")
                                        errors = re.findall(r'<LINEERROR>(.*?)</LINEERROR>', v_text)
                                        for err in set(errors): st.write(f"👉 **{err.replace('&apos;', '')}**")
                                    elif "<CREATED>" in v_text or "<ALTERED>" in v_text:
                                        st.success("🎉 Makkhan! Saare Masters aur Vouchers Tally me aagaye bina kisi exception ke!")
                                        st.balloons()
                                else:
                                    st.error("❌ Vouchers push karte time server error.")
                    else:
                        st.error("❌ Masters (Ledgers/Items) request fail ho gayi.")
                        
                except requests.exceptions.ConnectionError:
                    st.error("❌ Connection Error: Kya Tally open hai aur Port 9000 chal raha hai?")

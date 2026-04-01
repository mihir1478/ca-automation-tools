import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(layout="wide") # Page layout wide
st.title("📄 Logwintech - Sales PDF to XML")
st.write("Apni Logwintech Sales Invoices yahan upload karein. SEZ aur Export Invoices automatically handle ho jayengi. Data verify/edit karein aur fir download karein.")

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
COMPANY_NAME = "LOGWINTECH PRIVATE LIMITED"
SELLER_GSTIN = "24AAECL9706D1ZO"

# Tally Ledgers
STANDARD_SALES_LEDGER = "Sale of Services"
ZERO_TAX_SALES_LEDGER = "Export of Service"  

# SEZ GSTINs
SEZ_GSTINS = [
    "32AAGCC0294H1ZX", # Coddle Technologies
]

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
    if pd.isna(gstin) or str(gstin).strip() == "": 
        return "Not Applicable"
    code = str(gstin)[:2]
    if code in state_codes:
        return state_codes[code]
    return "Not Applicable"

def is_summary_line(line):
    lower_line = line.lower()
    keywords = [
        "total qty", "basic amount", "net payable", "bank detail", 
        "bank:", "account no", "rupees only", "igst", "cgst", "sgst", 
        "generated using", "to get pdf", "round off", "authorised signature", 
        "receiver's signature", "filing date", "lut arn", "swift code", "ifs code"
    ]
    return any(lower_line.startswith(kw) or kw in lower_line for kw in keywords)

# ==========================================
# 📄 PDF EXTRACTION LOGIC
# ==========================================
def extract_invoice_data(pdf_file_obj):
    data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text: continue
            
            inv_no_match = re.search(r"Number:\s*([A-Za-z0-9-]+)", text)
            date_match = re.search(r"Date:\s*([0-9]{1,2}\s+[A-Za-z]{3}\s+[0-9]{4})", text)
            
            inv_no = inv_no_match.group(1).strip() if inv_no_match else f"UNKNOWN-{page_num+1}"
            inv_date = date_match.group(1).strip() if date_match else ""
            
            lines = text.split('\n')
            party_name = ""
            for i, line in enumerate(lines):
                if "Bill To:" in line:
                    for j in range(1, 5):
                        if i + j < len(lines):
                            potential_name = lines[i+j].strip()
                            if potential_name and potential_name.lower() != "invoice" and "email:" not in potential_name.lower():
                                party_name = potential_name
                                break
                    break
            
            all_gstins = re.findall(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}[Zz]{1}[0-9A-Z]{1}\b', text.upper())
            party_gstin = ""
            for gstin in all_gstins:
                if gstin != SELLER_GSTIN:
                    party_gstin = gstin
                    break 

            is_sez = False
            if "SEZ" in party_name.upper() or party_gstin in SEZ_GSTINS:
                is_sez = True
            elif re.search(r'\bSEZ\b', text, re.IGNORECASE) or re.search(r'Special Economic Zone', text, re.IGNORECASE):
                is_sez = True
                
            is_export = not party_gstin and not is_sez

            items = []
            current_item = None
            previous_line = ""
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                match = re.search(r"^(?:\d+\s+)?(.*?)\s*(99\d{4})\s+([\d.]+)\s+([A-Za-z]+)\s+([\d.,]+)\s+[\d.,]+\s+([\d.,]+)", line)
                if match:
                    if current_item: items.append(current_item)
                    
                    item_name = match.group(1).strip()
                    if not item_name and previous_line:
                        item_name = re.sub(r'^\d+\s+', '', previous_line).strip()
                    else:
                        item_name = re.sub(r'^\d+\s+', '', item_name).strip()
                    
                    item_amount_str = match.group(6).replace(',', '')
                    try: item_amount = float(item_amount_str)
                    except ValueError: item_amount = 0.0
                    
                    igst_amt, cgst_amt, sgst_amt, gst_pct = "0", "0", "0", "0"
                    
                    if not is_export and not is_sez and party_gstin:
                        gst_pct = "18"
                        tax = item_amount * 0.18
                        if party_gstin.startswith("24"):
                            cgst_amt = f"{round(tax / 2, 2):.2f}"
                            sgst_amt = f"{round(tax / 2, 2):.2f}"
                        else:
                            igst_amt = f"{round(tax, 2):.2f}"
                    
                    current_item = {
                        "Voucher Date": inv_date, "Voucher Type": "Sales", "Voucher Number": inv_no,
                        "Party Name": party_name, "Party GSTIN": party_gstin, "Is SEZ": is_sez, "Is Export": is_export,
                        "Item Name": item_name, "HSN/SAC": match.group(2), "Billed Qty": match.group(3), 
                        "UOM": match.group(4), "Rate": match.group(5).replace(',', ''), "GST %": gst_pct,
                        "Amount": f"{item_amount:.2f}", "IGST Amount": igst_amt,
                        "CGST Amount": cgst_amt, "SGST Amount": sgst_amt, "Total Invoice Value": "" 
                    }
                elif current_item:
                    if is_summary_line(line):
                        items.append(current_item)
                        current_item = None
                    else:
                        if "sac" in line.lower() and "qty" in line.lower() and "amount" in line.lower(): continue 
                        current_item["Item Name"] += f" | {line}"
                previous_line = line
            
            if current_item: items.append(current_item)
            data.extend(items)
            
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
    
    for col in ['CGST Amount', 'SGST Amount', 'IGST Amount']:
        if col not in df_xml.columns: df_xml[col] = 0
            
    num_cols = ['Amount', 'CGST Amount', 'SGST Amount', 'IGST Amount', 'Rate', 'Billed Qty']
    for col in num_cols:
        if col in df_xml.columns:
            df_xml[col] = pd.to_numeric(df_xml[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    if 'Voucher Date' in df_xml.columns:
        df_xml['Voucher Date'] = pd.to_datetime(df_xml['Voucher Date'], format='mixed', dayfirst=True, errors='coerce').dt.strftime('%Y%m%d')

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
            continue # Skip row if voucher number is empty
            
        row = group.iloc[0]
        p_name = str(row['Party Name']).strip() if pd.notna(row['Party Name']) else ""
        p_gstin = str(row['Party GSTIN']).strip() if pd.notna(row['Party GSTIN']) else ""
        
        is_sez = row.get('Is SEZ', False)
        is_export = row.get('Is Export', False)
        
        p_state = get_state(p_gstin)
        
        if is_export:
            reg_type = "Unknown"
            country = "Not Applicable"
            sales_ledger = ZERO_TAX_SALES_LEDGER
        elif is_sez:
            reg_type = "Regular-SEZ"
            country = "India"
            sales_ledger = ZERO_TAX_SALES_LEDGER
        else:
            reg_type = "Regular"
            country = "India"
            sales_ledger = STANDARD_SALES_LEDGER
            
        taxable = group['Amount'].sum()
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
      <PARTYGSTIN>{p_gstin if p_state != "Not Applicable" else ""}</PARTYGSTIN>
      <GSTREGISTRATIONTYPE>{reg_type}</GSTREGISTRATIONTYPE>
      <STATENAME>{p_state}</STATENAME>
      <COUNTRYOFRESIDENCE>{country}</COUNTRYOFRESIDENCE>
      <PLACEOFSUPPLY>{p_state.upper()}</PLACEOFSUPPLY>
      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
      <ISINVOICE>Yes</ISINVOICE>
      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
      <VCHGSTSTATUSISINCLUDED>Yes</VCHGSTSTATUSISINCLUDED>
      <ISBOENOTAPPLICABLE>Yes</ISBOENOTAPPLICABLE>
      <ISGSTOVERRIDDEN>Yes</ISGSTOVERRIDDEN>
"""
        for _, i_row in group.iterrows():
            item_taxable = float(i_row['Amount'])
            item_tax = float(i_row['CGST Amount']) + float(i_row['SGST Amount']) + float(i_row['IGST Amount'])
            
            if is_sez or is_export:
                gst_val = 0
            elif item_taxable > 0 and item_tax > 0:
                gst_val = int(round((item_tax / item_taxable) * 100))
            else:
                gst_val = 0 
                
            hsn = str(i_row['HSN/SAC']).split('.')[0]
            if hsn.lower() == 'nan' or hsn.strip() == '': hsn = '998313'
            
            item_name = f"{hsn}@{gst_val}%"
            
            qty = i_row['Billed Qty']
            rate = i_row['Rate']
            uom = str(i_row['UOM']).strip() if pd.notna(i_row['UOM']) else ""
            if uom.lower() == 'nan': uom = ""

            xml_data += f"""      <ALLINVENTORYENTRIES.LIST>
       <STOCKITEMNAME>{item_name}</STOCKITEMNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
"""
            if qty > 0:
                rate_str = f"{rate:.2f}/{uom}" if uom else f"{rate:.2f}"
                qty_str = f"{qty:.3f} {uom}".strip()
                xml_data += f"""       <RATE>{rate_str}</RATE>
       <BILLEDQTY>{qty_str}</BILLEDQTY>
       <ACTUALQTY>{qty_str}</ACTUALQTY>
"""
            xml_data += f"""       <AMOUNT>{i_row['Amount']:.2f}</AMOUNT>
       <ACCOUNTINGALLOCATIONS.LIST>
        <LEDGERNAME>{sales_ledger}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{i_row['Amount']:.2f}</AMOUNT>
       </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>
"""
        xml_data += f"""      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{p_name}</LEDGERNAME>
       <GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
       <AMOUNT>-{grand_total:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>
"""
        for t_name, t_amt in [("CGST", cgst), ("SGST", sgst), ("IGST", igst)]:
            if t_amt > 0:
                xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>{t_name}</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{t_amt:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""

        if round_off != 0:
            is_pos = "Yes" if round_off < 0 else "No"
            xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>ROUND OFF</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>{is_pos}</ISDEEMEDPOSITIVE><AMOUNT>{round_off:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""

        xml_data += "     </VOUCHER>\n    </TALLYMESSAGE>\n"
    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""

    return xml_data

# ==========================================
# 🚀 STREAMLIT UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload Logwintech PDF files", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Extract Data from PDFs", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_data = []
            
            for pdf_file in uploaded_pdfs:
                try:
                    extracted = extract_invoice_data(pdf_file)
                    if extracted:
                        all_data.extend(extracted)
                except Exception as e:
                    st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_data:
                # 1. Create DataFrame and enforce column order
                df = pd.DataFrame(all_data)
                cols = ["Voucher Date", "Voucher Type", "Voucher Number", "Party Name", "Party GSTIN", "Is SEZ", "Is Export", "Item Name", "HSN/SAC", "Billed Qty", "UOM", "Rate", "GST %", "Amount", "IGST Amount", "CGST Amount", "SGST Amount", "Total Invoice Value"]
                df = df.reindex(columns=cols)
                
                # Save into session state
                st.session_state['logwin_df'] = df
                st.success(f"✅ Success! {len(uploaded_pdfs)} PDF files processed (SEZ/Export handled).")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

# Check if data is present in session state
if 'logwin_df' in st.session_state:
    df = st.session_state['logwin_df']
    
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
    
    # Interactive Data Editor
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
            file_name="Logwintech_Final.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="📥 Download Tally XML", 
            data=xml_string, 
            file_name="Logwintech_ItemInvoice.xml", 
            mime="application/xml"
        )

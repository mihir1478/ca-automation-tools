import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(layout="wide") # Page thoda wide kar diya taaki table achhe se dikhe
st.title("📄 Mihira Fabric - Sales PDF to XML")
st.write("Apni Mihira Fabric ki Sales Invoices yahan upload karein. Data verify karein, edit karein, aur Excel/Tally XML generate karein.")

# ==========================================
# ⚙️ TALLY CONFIGURATION & HELPERS
# ==========================================
COMPANY_NAME = "MIHIRA FABRIC" 
SELLER_GST = "24DGGPS3046M1Z1"

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

# ==========================================
# 📄 PDF EXTRACTION LOGIC
# ==========================================
def parse_mihira_pdf(pdf_file_obj):
    tally_data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            
            # Delivery challan skip karna
            if not text or "DELIVERY CHALLAN" in text.upper():
                continue
                
            # --- Voucher Info ---
            inv_no_match = re.search(r'Invoice No[\s:]+(\d+)', text, re.IGNORECASE)
            inv_no = inv_no_match.group(1) if inv_no_match else ""
            
            date_match = re.search(r'Date[\s:]*(\d{2}-\d{2}-\d{4})', text, re.IGNORECASE)
            inv_date = date_match.group(1) if date_match else ""

            # --- Party GSTIN ---
            all_gsts = re.findall(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}', text)
            party_gst = next((gst for gst in all_gsts if gst != SELLER_GST), "")

            # --- Party Name ---
            party_name = ""
            if "NEELMADHAV LIFESTYLE" in text: party_name = "NEELMADHAV LIFESTYLE"
            elif "PARVATI SURAT MILLS" in text: party_name = "PARVATI SURAT MILLS"
            elif "SHRISHTI FASHION" in text: party_name = "SHRISHTI FASHION"
            elif "DEV SHREE TEXTILES" in text: party_name = "DEV SHREE TEXTILES"
            elif "GOPANGANA NX" in text: party_name = "GOPANGANA NX"
            else:
                party_match = re.search(r'M/s:[\s",]*([A-Za-z\s]+?)(?:\\n|Add:|City:|GST|")', text)
                if party_match: party_name = party_match.group(1).strip()

            # --- SMART Item Details Extraction ---
            item_name, hsn, qty, uom, rate = "", "", "", "", ""
            item_match = re.search(r'(P[\*]?.*?\s*63)\s*[\n]*\s*(\d{4})\s*[\n]*\s*\d+\s*[\n]*\s*\d+\s*[\n]*\s*([\d\.]+)\s*[\n]*\s*(MTR|PCS)\s*[\n]*\s*([\d\.]+)', text)
            
            if item_match:
                raw_item_name = item_match.group(1)
                item_name = " ".join(raw_item_name.split()) 
                hsn, qty, uom, rate = item_match.group(2).strip(), item_match.group(3).strip(), item_match.group(4).strip(), item_match.group(5).strip()
            else:
                 fallback_match = re.search(r'1\s*[\n]*\s*([A-Za-z\*\s]+?\d*)\s*[\n]*\s*(\d{4})\s*[\n]*\s*.*?([\d\.]+)\s*[\n]*\s*(MTR|PCS)\s*[\n]*\s*([\d\.]+)', text)
                 if fallback_match:
                     raw_item_name = fallback_match.group(1)
                     item_name = " ".join(raw_item_name.split()) 
                     hsn, qty, uom, rate = fallback_match.group(2).strip(), fallback_match.group(3).strip(), fallback_match.group(4).strip(), fallback_match.group(5).strip()

            # --- Tax & Amount Details ---
            taxable_match = re.search(r'Taxable Value[\s:]*([\d\.]+)', text, re.IGNORECASE)
            taxable_val = taxable_match.group(1) if taxable_match else "0.00"

            cgst_match = re.search(r'CGST\s*(?:2\.5%)?\s*([\d\.]+)', text)
            cgst_val = cgst_match.group(1) if cgst_match else "0.00"

            sgst_match = re.search(r'SGST\s*(?:2\.5%)?\s*([\d\.]+)', text)
            sgst_val = sgst_match.group(1) if sgst_match else "0.00"

            total_match = re.search(r'Invoice Total[\s:]*([\d\.]+)', text, re.IGNORECASE)
            total_val = total_match.group(1) if total_match else "0.00"

            if inv_no or party_name: # Modify kiye taaki agar inv_no miss ho toh bhi row bane
                tally_data.append({
                    "Voucher Date": inv_date,
                    "Voucher No": inv_no,
                    "Party A/c Name": party_name,
                    "Party GSTIN": party_gst,
                    "Item Name": item_name,
                    "HSN/SAC Code": hsn,
                    "Billed Qty": qty,
                    "Unit": uom,
                    "Rate": rate,
                    "Taxable Value": float(taxable_val) if taxable_val else 0.00,
                    "CGST Amount": float(cgst_val) if cgst_val else 0.00,
                    "SGST Amount": float(sgst_val) if sgst_val else 0.00,
                    "IGST Amount": 0.00, # By default 0 for Mihira
                    "Total Invoice Amount": float(total_val) if total_val else 0.00
                })
    return tally_data

# ==========================================
# 📝 TALLY XML GENERATION LOGIC
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
    for vch_no, group in df_xml.groupby('Voucher No'):
        if pd.isna(vch_no) or str(vch_no).strip() == "": 
            continue # Skip if voucher number is completely empty after editing

        row = group.iloc[0]
        p_name = str(row['Party A/c Name']).strip() if pd.notna(row['Party A/c Name']) else ""
        p_gstin = str(row['Party GSTIN']).strip() if pd.notna(row['Party GSTIN']) else ""
        p_state = get_state(p_gstin)
        
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
      <ISGSTOVERRIDDEN>Yes</ISGSTOVERRIDDEN>
"""
        for _, i_row in group.iterrows():
            item_taxable = i_row['Taxable Value']
            item_tax = i_row['CGST Amount'] + i_row['SGST Amount'] + i_row['IGST Amount']
            
            gst_val = 0
            if item_taxable > 0:
                gst_val = int(round((item_tax / item_taxable) * 100))

            hsn = str(i_row['HSN/SAC Code']).split('.')[0]
            item_name = f"{hsn}@{gst_val}%"

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
                    if extracted:
                        all_data.extend(extracted)
                except Exception as e:
                    st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_data:
                # Save extracted data to session state so it doesn't reset on UI interaction
                st.session_state['raw_df'] = pd.DataFrame(all_data)
                st.success(f"✅ Success! {len(uploaded_pdfs)} PDF files processed.")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

# Check if we have data in session state to display and edit
if 'raw_df' in st.session_state:
    df = st.session_state['raw_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields
    empty_vouchers = df[df['Voucher No'].isna() | (df['Voucher No'] == "")]
    empty_parties = df[df['Party A/c Name'].isna() | (df['Party A/c Name'] == "")]
    zero_totals = df[df['Total Invoice Amount'] == 0.00]
    
    if not empty_vouchers.empty or not empty_parties.empty or not zero_totals.empty:
        st.warning("⚠️ **DHYAN DEIN:** Kuch invoices mein Data theek se extract nahi hua hai. Kripya niche table mein double-click karke empty ya 0.00 waali fields ko theek karein.")
    else:
        st.info("💡 Aap niche diye gaye table mein kisi bhi cell par double-click karke data edit kar sakte hain.")
    
    # --- NEW FEATURE: Editable Dataframe ---
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    st.markdown("---")
    st.subheader("💾 Download Final Files")
    st.write("Upar kiye gaye saare changes yahan download hone waali files mein aayenge.")
    
    # Generate files using the EDITED dataframe
    excel_buffer = io.BytesIO()
    edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_bytes = excel_buffer.getvalue()
    
    xml_string = generate_xml_from_df(edited_df.copy())
    
    # Download Buttons
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="⬇️ Download Edited Excel", 
            data=excel_bytes, 
            file_name="Mihira_Fabric_Final.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="⬇️ Download Tally XML", 
            data=xml_string, 
            file_name="Mihira_Fabric_ItemInvoice.xml", 
            mime="application/xml"
        )

import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.title("?? Kadvi Baa Tex - Sales Register PDF to XML")
st.write("Apni Sales Register PDF yahan upload karein, Excel aur Tally XML generate karne ke liye.")

# ==========================================
# ?? SETTINGS
# ==========================================
COMPANY_NAME = "KADVI BAA TEX LLP"  
FIXED_ITEM_NAME = "540720@5%"       

# GSTIN State Code Mapping
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

# ==========================================
# ??? HELPER FUNCTIONS
# ==========================================
def clean_number(val):
    if not val: return "0"
    val = val.replace(',', '').strip()
    parts = val.split('.')
    if len(parts) > 2:
        val = "".join(parts[:-1]) + "." + parts[-1]
    return val

def get_state_from_gstin(gstin):
    if pd.isna(gstin) or len(str(gstin)) < 2:
        return "Gujarat"
    code = str(gstin)[:2]
    return state_codes.get(code, "Gujarat")

# ==========================================
# ?? PDF EXTRACTION LOGIC
# ==========================================
def extract_kadvibaa_sales_register(pdf_file_obj):
    data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        current_date, current_bill, current_party, current_gstin = "", "", "", ""

        for page in pdf.pages:
            text = page.extract_text(layout=True) 
            if not text: continue
            
            for line in text.split('\n'):
                line = line.strip()
                if not line: continue
                clean_line = re.sub(r'\s+', ' ', line)

                # Catch New Bill Header
                bill_match = re.search(r"^(\d{2}/\d{2}/\d{2,4})\s+(\d+)\s+(.+)$", clean_line)
                if bill_match and "Date Period" not in clean_line:
                    raw_date = bill_match.group(1)
                    d_parts = raw_date.split('/')
                    current_date = f"{d_parts[0]}/{d_parts[1]}/20{d_parts[2]}" if len(d_parts[2]) == 2 else raw_date
                    current_bill = bill_match.group(2)
                    raw_party = bill_match.group(3)
                    current_party = raw_party.strip()
                    current_gstin = ""

                    crushed_party = re.sub(r'[\s.:,-]+', '', raw_party).upper()
                    gst_match = re.search(r'(\d{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]{3})', crushed_party)
                        
                    if gst_match:
                        current_gstin = gst_match.group(1)
                        spacer = r'[\s.:,-]*'
                        gstin_pattern = spacer.join(list(current_gstin))
                        current_party = re.sub(gstin_pattern, '', raw_party, flags=re.IGNORECASE).strip()
                    continue

                # Catch Displaced GSTIN
                if current_bill and not current_gstin:
                    crushed_line = re.sub(r'[\s.:,-]+', '', clean_line).upper()
                    gst_match = re.search(r'(\d{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]{3})', crushed_line)
                    if gst_match and "ITEMNAME" not in crushed_line and "HSN" not in crushed_line:
                        current_gstin = gst_match.group(1)
                        spacer = r'[\s.:,-]*'
                        gstin_pattern = spacer.join(list(current_gstin))
                        current_party = re.sub(gstin_pattern, '', current_party, flags=re.IGNORECASE).strip()

                if "Bill Total" in clean_line or "Item Name" in clean_line or "HSN No" in clean_line:
                    continue

                # Extract Item Rows
                item_match = re.search(r"^(.+?)\s+(\d{4,8})\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)\s+([-+\d.,]+)(?:\s+([-+\d.,]+))?$", clean_line)

                if item_match:
                    item_name = item_match.group(1).strip()
                    if len(item_name) < 2: continue
                    
                    hsn, qty, rate, amt, gst_rate = item_match.group(2), item_match.group(4), item_match.group(5), item_match.group(6), item_match.group(9)
                    cgst, sgst, igst = clean_number(item_match.group(10)), clean_number(item_match.group(11)), clean_number(item_match.group(12))

                    cgst_val = cgst if float(cgst) > 0 else ""
                    sgst_val = sgst if float(sgst) > 0 else ""
                    igst_val = igst if float(igst) > 0 else ""

                    data.append({
                        "Voucher Date": current_date, "Voucher Type": "Sales", "Voucher Number": current_bill,
                        "Party Name": current_party, "Party GSTIN": current_gstin, "Item Name": item_name,
                        "HSN/SAC": hsn, "Billed Qty": clean_number(qty), "Rate": clean_number(rate),
                        "Amount": clean_number(amt), "GST %": clean_number(gst_rate), "CGST Amount": cgst_val,
                        "SGST Amount": sgst_val, "IGST Amount": igst_val
                    })
                    
    return data

# ==========================================
# ?? XML GENERATION LOGIC
# ==========================================
def generate_tally_xml(df):
    df_xml = df.copy()
    num_cols = ['CGST Amount', 'SGST Amount', 'IGST Amount', 'Amount', 'Rate', 'Billed Qty']
    for col in num_cols:
        df_xml[col] = pd.to_numeric(df_xml[col].replace('', 0), errors='coerce').fillna(0)
    
    df_xml['Voucher Date'] = pd.to_datetime(df_xml['Voucher Date'], dayfirst=True).dt.strftime('%Y%m%d')

    xml_data = f"""<ENVELOPE>
     <HEADER>
      <TALLYREQUEST>Import Data</TALLYREQUEST>
     </HEADER>
     <BODY>
      <IMPORTDATA>
       <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
         <SVCURRENTCOMPANY>{COMPANY_NAME}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
       </REQUESTDESC>
       <REQUESTDATA>
    """

    grouped = df_xml.groupby('Voucher Number')
    for vch_no, group in grouped:
        first_row = group.iloc[0]
        vch_date, party_name = first_row['Voucher Date'], first_row['Party Name']
        party_gstin = str(first_row['Party GSTIN']) if pd.notna(first_row['Party GSTIN']) else ""
        party_state = get_state_from_gstin(party_gstin)
        
        total_taxable, total_cgst, total_sgst, total_igst = group['Amount'].sum(), group['CGST Amount'].sum(), group['SGST Amount'].sum(), group['IGST Amount'].sum()
        raw_total = total_taxable + total_cgst + total_sgst + total_igst
        grand_total = round(raw_total)
        round_off_amount = grand_total - raw_total

        xml_data += f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">
         <VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Invoice Voucher View">
          <DATE>{vch_date}</DATE>
          <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
          <VOUCHERNUMBER>{vch_no}</VOUCHERNUMBER>
          <PARTYLEDGERNAME>{party_name}</PARTYLEDGERNAME>
          <PARTYNAME>{party_name}</PARTYNAME>
          <PARTYGSTIN>{party_gstin}</PARTYGSTIN>
          <STATENAME>{party_state}</STATENAME>
          <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
          <PLACEOFSUPPLY>{party_state}</PLACEOFSUPPLY>
          <CONSIGNEESTATENAME>{party_state}</CONSIGNEESTATENAME>
          <CONSIGNEECOUNTRYNAME>India</CONSIGNEECOUNTRYNAME>
          <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
          <ISINVOICE>Yes</ISINVOICE>
          <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
          <VCHGSTSTATUSISINCLUDED>Yes</VCHGSTSTATUSISINCLUDED>
    """

        # Fixed Inventory logic handling
        for index, row in group.iterrows():
            qty, rate, amt = row['Billed Qty'], row['Rate'], row['Amount']
            xml_data += f"""      <ALLINVENTORYENTRIES.LIST>
           <STOCKITEMNAME>{FIXED_ITEM_NAME}</STOCKITEMNAME>
           <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
           <RATE>{rate:.2f}/MTR</RATE>
           <AMOUNT>{amt:.2f}</AMOUNT>
           <BILLEDQTY>{qty:.2f}</BILLEDQTY>
           <ACTUALQTY>{qty:.2f}</ACTUALQTY>
           <ACCOUNTINGALLOCATIONS.LIST>
            <LEDGERNAME>SALES</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>{amt:.2f}</AMOUNT>
           </ACCOUNTINGALLOCATIONS.LIST>
          </ALLINVENTORYENTRIES.LIST>
    """

        xml_data += f"""      <LEDGERENTRIES.LIST>
           <LEDGERNAME>{party_name}</LEDGERNAME>
           <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
           <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
           <AMOUNT>-{grand_total:.2f}</AMOUNT>
          </LEDGERENTRIES.LIST>
    """

        if total_cgst > 0:
            xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>CGST</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_cgst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""
        if total_sgst > 0:
            xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>SGST</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_sgst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""
        if total_igst > 0:
            xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>IGST</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_igst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""

        if round(round_off_amount, 2) != 0.00:
            is_positive = "Yes" if round_off_amount < 0 else "No"
            xml_data += f"""      <LEDGERENTRIES.LIST>
           <ROUNDTYPE>Normal Rounding</ROUNDTYPE>
           <LEDGERNAME>ROUNDING OFF</LEDGERNAME>
           <ISDEEMEDPOSITIVE>{is_positive}</ISDEEMEDPOSITIVE>
           <AMOUNT>{round_off_amount:.2f}</AMOUNT>
          </LEDGERENTRIES.LIST>
    """
        xml_data += "     </VOUCHER>\n    </TALLYMESSAGE>\n"

    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""
    return xml_data


# ==========================================
# ?? UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload Sales Register PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Process & Generate Files", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_data = []
            
            for pdf_file in uploaded_pdfs:
                try:
                    extracted_data = extract_kadvibaa_sales_register(pdf_file)
                    if extracted_data:
                        all_data.extend(extracted_data)
                except Exception as e:
                    st.error(f"? Error in {pdf_file.name}: {e}")
            
            if all_data:
                # 1. Convert to DataFrame
                df = pd.DataFrame(all_data)
                
                # 2. Generate Excel in Memory
                excel_buffer = io.BytesIO()
                df.to_excel(excel_buffer, index=False, engine='openpyxl')
                excel_bytes = excel_buffer.getvalue()
                
                # 3. Generate XML String
                xml_string = generate_tally_xml(df.copy())
                
                st.success(f"? Successfully processed {len(uploaded_pdfs)} PDF files!")
                
                # Download Buttons
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="?? Download Excel", 
                        data=excel_bytes, 
                        file_name="Kadvibaa_Sales_Extracted.xlsx", 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                with col2:
                    st.download_button(
                        label="?? Download Tally XML", 
                        data=xml_string, 
                        file_name="Kadvibaa_Tally_Import.xml", 
                        mime="application/xml"
                    )
            else:
                st.warning("?? Koi valid table data extract nahi ho paya. Kripya PDF check karein.")
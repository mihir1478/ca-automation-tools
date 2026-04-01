import streamlit as st
import pdfplumber
import pandas as pd
import re
import uuid
import io

st.title("?? Kadvi Baa Tex - Job Work PDF to XML")
st.write("Apni Job Work Expense PDF yahan upload karein, Excel aur Tally Purchase XML generate karne ke liye.")

# ==========================================
# ?? CONFIGURATION
# ==========================================
COMPANY_NAME = "KADVI BAA TEX LLP"  
EXPENSE_LEDGER = "JOB WORK"         

# ???? GST State Codes Dictionary
GST_STATE_CODES = {
    '01': 'Jammu & Kashmir', '02': 'Himachal Pradesh', '03': 'Punjab', '04': 'Chandigarh',
    '05': 'Uttarakhand', '06': 'Haryana', '07': 'Delhi', '08': 'Rajasthan', '09': 'Uttar Pradesh',
    '10': 'Bihar', '11': 'Sikkim', '12': 'Arunachal Pradesh', '13': 'Nagaland', '14': 'Manipur',
    '15': 'Mizoram', '16': 'Tripura', '17': 'Meghalaya', '18': 'Assam', '19': 'West Bengal',
    '20': 'Jharkhand', '21': 'Odisha', '22': 'Chhattisgarh', '23': 'Madhya Pradesh', '24': 'Gujarat',
    '25': 'Daman and Diu', '26': 'Dadra & Nagar Haveli and Daman & Diu', '27': 'Maharashtra', 
    '28': 'Andhra Pradesh', '29': 'Karnataka', '30': 'Goa', '31': 'Lakshadweep', '32': 'Kerala', 
    '33': 'Tamil Nadu', '34': 'Puducherry', '35': 'Andaman & Nicobar Islands', '36': 'Telangana', 
    '37': 'Andhra Pradesh', '38': 'Ladakh'
}

# ==========================================
# ?? PDF EXTRACTION LOGIC
# ==========================================
def process_job_work_pdf(pdf_file_obj):
    text = ""
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    lines = [i.strip() for i in text.split("\n") if i.strip()]
    data = []
    
    date = ""
    bill = ""
    party = ""
    gstin = ""
    date_pattern = r"\d{2}/\d{2}/\d{2}"

    for i, line in enumerate(lines):
        if re.match(date_pattern, line):
            parts = line.split()
            date = parts[0]
            bill = parts[1]
            party = " ".join(parts[2:])
            if i + 1 < len(lines):
                gstin = lines[i+1]

        if "Bill Total" in line:
            nums = re.findall(r"[\d,.]+", line)
            if len(nums) >= 9:
                qty = nums[1].replace(",", "")
                taxable = nums[4].replace(",", "")
                cgst = nums[5].replace(",", "")
                sgst = nums[6].replace(",", "")
                total = nums[8].replace(",", "")

                data.append([date, bill, party, gstin, qty, taxable, cgst, sgst, total])
                
    return data

# ==========================================
# ?? TALLY XML GENERATION LOGIC
# ==========================================
def generate_jobwork_xml(df):
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
    success_count = 0

    for index, row in df.iterrows():
        inv_no = str(row['Bill No']).strip()
        
        if pd.isna(row['Bill No']) or inv_no == "nan" or inv_no == "":
            continue
            
        party_name = str(row['Party Name']).replace('&', '&amp;').strip()
        party_gstin = str(row['GSTIN']).strip()
        
        # State auto-detect from GSTIN
        state_code = party_gstin[:2] if len(party_gstin) >= 2 else "24"
        party_state = GST_STATE_CODES.get(state_code, "Gujarat")

        # Date Parse
        raw_date = row['Date']
        if isinstance(raw_date, str):
            raw_date = raw_date.replace('/', '-')
        date_obj = pd.to_datetime(raw_date, dayfirst=True, errors='coerce')
        if pd.isna(date_obj):
            continue
        tally_date = date_obj.strftime('%Y%m%d')
        
        # Amounts Extraction
        taxable_val = float(row['Taxable Amount']) if row['Taxable Amount'] else 0.0
        cgst = float(row['CGST']) if row['CGST'] else 0.0
        sgst = float(row['SGST']) if row['SGST'] else 0.0
        inv_val = float(row['Bill Amount']) if row['Bill Amount'] else 0.0
        
        # Check for Round Off
        calculated_total = taxable_val + cgst + sgst
        round_off = round(calculated_total - inv_val, 2)
        
        guid = str(uuid.uuid4())
        
        voucher_xml = f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">
      <DATE>{tally_date}</DATE>
      <GUID>{guid}</GUID>
      <STATENAME>{party_state}</STATENAME>
      <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
      <PARTYGSTIN>{party_gstin}</PARTYGSTIN>
      <PLACEOFSUPPLY>{party_state}</PLACEOFSUPPLY>
      <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
      <PARTYNAME>{party_name}</PARTYNAME>
      <PARTYLEDGERNAME>{party_name}</PARTYLEDGERNAME>
      <VOUCHERNUMBER>{inv_no}</VOUCHERNUMBER>
      <REFERENCE>{inv_no}</REFERENCE>
      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
      <ISINVOICE>Yes</ISINVOICE>
      <ISELIGIBLEFORITC>Yes</ISELIGIBLEFORITC>
      
      <ALLINVENTORYENTRIES.LIST>      </ALLINVENTORYENTRIES.LIST>
      
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{party_name}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
       <AMOUNT>{inv_val:.2f}</AMOUNT>
       <BILLALLOCATIONS.LIST>
        <NAME>{inv_no}</NAME>
        <BILLTYPE>New Ref</BILLTYPE>
        <AMOUNT>{inv_val:.2f}</AMOUNT>
       </BILLALLOCATIONS.LIST>
      </LEDGERENTRIES.LIST>
      
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{EXPENSE_LEDGER}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{taxable_val:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>
"""
        if cgst > 0:
            voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>CGST</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{cgst:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>"""
              
        if sgst > 0:
            voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>SGST</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{sgst:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>"""

        if abs(round_off) > 0:
            is_deemed_positive = "Yes" if round_off < 0 else "No"
            voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>Round Off</LEDGERNAME>
       <ISDEEMEDPOSITIVE>{is_deemed_positive}</ISDEEMEDPOSITIVE>
       <AMOUNT>{round_off:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>"""

        voucher_xml += """
     </VOUCHER>
    </TALLYMESSAGE>"""
        
        xml_data += voucher_xml
        success_count += 1

    xml_data += """
   </REQUESTDATA>
  </IMPORTDATA>
 </BODY>
</ENVELOPE>"""

    return xml_data, success_count

# ==========================================
# ?? UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload Job Work PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Process & Generate Files", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_data = []
            
            for pdf_file in uploaded_pdfs:
                try:
                    extracted_data = process_job_work_pdf(pdf_file)
                    if extracted_data:
                        all_data.extend(extracted_data)
                except Exception as e:
                    st.error(f"? Error in file {pdf_file.name}: {str(e)}")
            
            if all_data:
                # 1. Create DataFrame
                df = pd.DataFrame(all_data, columns=[
                    "Date", "Bill No", "Party Name", "GSTIN", "Qty", 
                    "Taxable Amount", "CGST", "SGST", "Bill Amount"
                ])
                
                # 2. Generate Excel in memory
                excel_buffer = io.BytesIO()
                df.to_excel(excel_buffer, index=False, engine='openpyxl')
                excel_bytes = excel_buffer.getvalue()
                
                # 3. Generate XML String
                xml_string, count = generate_jobwork_xml(df.copy())
                
                st.success(f"? Success! {count} Vouchers ka XML aur Excel dono generate ho gaye hain.")
                
                # Download Buttons
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="?? Download Excel", 
                        data=excel_bytes, 
                        file_name="job_bill_correct.xlsx", 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                with col2:
                    st.download_button(
                        label="?? Download Tally XML", 
                        data=xml_string, 
                        file_name="Tally_JobWork_Import.xml", 
                        mime="application/xml"
                    )
            else:
                st.warning("?? Koi valid data extract nahi ho paya. Kripya PDF check karein.")
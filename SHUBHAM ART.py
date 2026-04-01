import streamlit as st
import pandas as pd
import io
import re
import pdfplumber

st.set_page_config(layout="wide") # Page layout ko wide banaya
st.title("📄 Shubham Art - PDF Invoices to Excel & XML")
st.write("Apni Shubham Art ki PDF files yahan upload karein. Data verify/edit karein aur uske baad Excel aur Tally XML generate karein.")

# ==========================================
# ⚙️ SETTINGS & FUNCTIONS
# ==========================================
COMPANY_NAME = "SHUBHAM ART"
SELLER_GSTIN = "24DRJPS8612H1ZG"
DEFAULT_UQC = "KGS" 

pdf_state_codes = {
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

def get_state_from_gstin(gstin):
    if pd.isna(gstin) or len(str(gstin)) < 2: return "Gujarat"
    code = str(gstin)[:2]
    return pdf_state_codes.get(code, "Gujarat")

# ==========================================
# 📄 PDF EXTRACTION LOGIC
# ==========================================
def extract_shubham_art_invoices(pdf_file_obj):
    data = []
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() 
            if not text: continue
            
            inv_no_match = re.search(r"Invoice No[\s.:]*([A-Za-z0-9/-]+)", text, re.IGNORECASE)
            inv_no = inv_no_match.group(1).strip() if inv_no_match else f"UNKNOWN-{page_num+1}"
            
            date_match = re.search(r"Date[\s.:]*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
            if date_match: 
                inv_date = date_match.group(1).strip()
            else:
                all_dates = re.findall(r"\d{2}/\d{2}/\d{4}", text)
                inv_date = all_dates[0] if all_dates else ""

            party_match = re.search(r"M/s[\s.:]*([^\n]+)", text, re.IGNORECASE)
            party_name = ""
            if party_match:
                party_name = party_match.group(1).strip()
                party_name = re.sub(r'(?i)\s*(?:Original|Invoice\s*No|Date).*$', '', party_name).strip()
                party_name = re.sub(r'[,.\s]+$', '', party_name)

            words = page.extract_words(keep_blank_chars=False)
            words_text = "".join([w['text'] for w in words]) if words else ""
            combined_text = (text + " " + words_text).upper()
            crushed_text = re.sub(r'[\s\n.:,-]+', '', combined_text)
            
            party_gstin = ""
            for g in re.findall(r'GST(?:IN|NO)?(24[A-Z0-9]{13})', crushed_text):
                if g != SELLER_GSTIN:
                    party_gstin = g
                    break
            if not party_gstin:
                for g in re.findall(r'(24[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]{3})', crushed_text):
                    if g != SELLER_GSTIN:
                        party_gstin = g
                        break

            def get_last_amount(pattern):
                for line in text.split('\n'):
                    if re.search(pattern, line, re.IGNORECASE):
                        amounts = re.findall(r"-?\d+\.\d+", line.replace(',', ''))
                        if amounts: return amounts[-1]
                return ""

            cgst = get_last_amount(r"Central Tax")
            sgst = get_last_amount(r"State.*?Tax")
            igst = get_last_amount(r"Integrated.*?Tax")
            round_off = get_last_amount(r"Round Off")
            grand_total = get_last_amount(r"Grand Total")

            items = []
            for line in text.split('\n'):
                line = line.strip()
                item_match = re.search(r"^(\d+)\s+(.+?)\s+(\d{4,8})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)$", line)
                if item_match:
                    items.append({
                        "Voucher Date": inv_date, "Voucher Type": "Sales", "Voucher Number": inv_no,
                        "Party Name": party_name, "Party GSTIN": party_gstin, "Item Name": item_match.group(2).strip(),
                        "HSN/SAC": item_match.group(3).strip(), "Billed Qty": item_match.group(4).strip(),
                        "Unit": DEFAULT_UQC, "Rate": item_match.group(5).strip(), "GST %": item_match.group(6).strip(),
                        "Amount": item_match.group(7).strip(), "CGST Amount": "", "SGST Amount": "",
                        "IGST Amount": "", "Round Off": "", "Total Invoice Value": grand_total
                    })

            if items:
                items[0]["CGST Amount"] = cgst; items[0]["SGST Amount"] = sgst
                items[0]["IGST Amount"] = igst; items[0]["Round Off"] = round_off
            data.extend(items)
    return data

# ==========================================
# 💻 TALLY XML GENERATION LOGIC
# ==========================================
def generate_tally_xml_from_df(df):
    num_cols = ['Amount', 'CGST Amount', 'SGST Amount', 'IGST Amount', 'Rate', 'Billed Qty', 'GST %']
    for col in num_cols:
        if col in df.columns: 
            df[col] = pd.to_numeric(df[col].astype(str).replace('', '0').str.replace(',', ''), errors='coerce').fillna(0)
    
    if 'Voucher Date' in df.columns: 
        df['Voucher Date'] = pd.to_datetime(df['Voucher Date'], dayfirst=True, errors='coerce').dt.strftime('%Y%m%d')

    xml_data = f"""<ENVELOPE>\n <HEADER>\n  <TALLYREQUEST>Import Data</TALLYREQUEST>\n </HEADER>\n <BODY>\n  <IMPORTDATA>\n   <REQUESTDESC>\n    <REPORTNAME>Vouchers</REPORTNAME>\n    <STATICVARIABLES>\n     <SVCURRENTCOMPANY>{COMPANY_NAME}</SVCURRENTCOMPANY>\n    </STATICVARIABLES>\n   </REQUESTDESC>\n   <REQUESTDATA>\n"""
    
    grouped = df.groupby('Voucher Number')
    for vch_no, group in grouped:
        if pd.isna(vch_no) or str(vch_no).strip() == "": 
            continue # Skip row if voucher number is empty

        first_row = group.iloc[0]
        vch_date = first_row['Voucher Date'] if 'Voucher Date' in df.columns else "20260228"
        party_name = first_row['Party Name']
        party_gstin = str(first_row['Party GSTIN']).strip() if pd.notna(first_row['Party GSTIN']) else ""
        party_state = get_state_from_gstin(party_gstin)
        
        total_taxable = group['Amount'].sum()
        total_cgst = group['CGST Amount'].sum()
        total_sgst = group['SGST Amount'].sum()
        total_igst = group['IGST Amount'].sum()
        
        raw_total = total_taxable + total_cgst + total_sgst + total_igst
        grand_total = round(raw_total)
        round_off_amount = grand_total - raw_total

        xml_data += f"""    <TALLYMESSAGE xmlns:UDF="TallyUDF">\n     <VOUCHER VCHTYPE="Sales" ACTION="Create" OBJVIEW="Invoice Voucher View">\n      <DATE>{vch_date}</DATE>\n      <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>\n      <VOUCHERNUMBER>{vch_no}</VOUCHERNUMBER>\n      <PARTYLEDGERNAME>{party_name}</PARTYLEDGERNAME>\n      <PARTYNAME>{party_name}</PARTYNAME>\n      <PARTYGSTIN>{party_gstin}</PARTYGSTIN>\n      <STATENAME>{party_state}</STATENAME>\n      <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>\n      <PLACEOFSUPPLY>{party_state}</PLACEOFSUPPLY>\n      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>\n      <ISINVOICE>Yes</ISINVOICE>\n      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>\n      <VCHGSTSTATUSISINCLUDED>Yes</VCHGSTSTATUSISINCLUDED>\n      <ISBOENOTAPPLICABLE>Yes</ISBOENOTAPPLICABLE>\n      <ISGSTOVERRIDDEN>Yes</ISGSTOVERRIDDEN>\n"""
        
        for index, row in group.iterrows():
            raw_hsn = str(row['HSN/SAC']).replace('.0', '').strip()
            raw_gst = float(row['GST %']) if pd.notna(row['GST %']) else 0
            item_name = f"{raw_hsn}@{int(raw_gst) if raw_gst.is_integer() else raw_gst}%" 
            qty, rate, amt = row['Billed Qty'], row['Rate'], row['Amount']

            unit = ""
            if 'Unit' in df.columns and pd.notna(row['Unit']): 
                unit = str(row['Unit']).strip().upper()
            elif 'UQC' in df.columns and pd.notna(row['UQC']): 
                unit = str(row['UQC']).strip().upper()

            qty_str = f"{qty:.3f} {unit}".strip()
            rate_str = f"{rate:.2f}/{unit}" if unit else f"{rate:.2f}"

            xml_data += f"""      <ALLINVENTORYENTRIES.LIST>\n       <STOCKITEMNAME>{item_name}</STOCKITEMNAME>\n       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>\n       <RATE>{rate_str}</RATE>\n       <AMOUNT>{amt:.2f}</AMOUNT>\n       <BILLEDQTY>{qty_str}</BILLEDQTY>\n       <ACTUALQTY>{qty_str}</ACTUALQTY>\n       <ACCOUNTINGALLOCATIONS.LIST>\n        <LEDGERNAME>SALES</LEDGERNAME>\n        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>\n        <AMOUNT>{amt:.2f}</AMOUNT>\n       </ACCOUNTINGALLOCATIONS.LIST>\n      </ALLINVENTORYENTRIES.LIST>\n"""
            
        xml_data += f"""      <LEDGERENTRIES.LIST>\n       <LEDGERNAME>{party_name}</LEDGERNAME>\n       <GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY>\n       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>\n       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>\n       <AMOUNT>-{grand_total:.2f}</AMOUNT>\n      </LEDGERENTRIES.LIST>\n"""
        
        if total_cgst > 0: xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>CGST</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_cgst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""
        if total_sgst > 0: xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>SGST</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_sgst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""
        if total_igst > 0: xml_data += f"""      <LEDGERENTRIES.LIST><LEDGERNAME>IGST</LEDGERNAME><GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{total_igst:.2f}</AMOUNT></LEDGERENTRIES.LIST>\n"""
        
        if round(round_off_amount, 2) != 0.00:
            is_pos = "Yes" if round_off_amount < 0 else "No"
            xml_data += f"""      <LEDGERENTRIES.LIST>\n       <LEDGERNAME>ROUND OFF</LEDGERNAME>\n       <GSTOVRDNTYPEOFSUPPLY>Services</GSTOVRDNTYPEOFSUPPLY>\n       <ISDEEMEDPOSITIVE>{is_pos}</ISDEEMEDPOSITIVE>\n       <AMOUNT>{abs(round_off_amount):.2f}</AMOUNT>\n      </LEDGERENTRIES.LIST>\n"""
        
        xml_data += "     </VOUCHER>\n    </TALLYMESSAGE>\n"
    xml_data += """   </REQUESTDATA>\n  </IMPORTDATA>\n </BODY>\n</ENVELOPE>"""
    return xml_data

# ==========================================
# 🚀 UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload Invoice PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Extract Data from PDFs", type="primary"):
        with st.spinner("PDFs process ho rahi hain..."):
            all_data = []
            for pdf_file in uploaded_pdfs:
                try:
                    extracted = extract_shubham_art_invoices(pdf_file)
                    if extracted: 
                        all_data.extend(extracted)
                except Exception as e:
                    st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_data:
                # 1. Create DataFrame
                df = pd.DataFrame(all_data)
                
                # Enforce column order if needed
                cols = ["Voucher Date", "Voucher Type", "Voucher Number", "Party Name", "Party GSTIN", "Item Name", "HSN/SAC", "Billed Qty", "Unit", "Rate", "GST %", "Amount", "CGST Amount", "SGST Amount", "IGST Amount", "Round Off", "Total Invoice Value"]
                df = df.reindex(columns=cols)

                # Save into session state
                st.session_state['shubham_df'] = df
                st.success(f"✅ Successfully processed {len(uploaded_pdfs)} PDF files!")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

# Check if data exists in session state to show the interactive table
if 'shubham_df' in st.session_state:
    df = st.session_state['shubham_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields
    empty_vouchers = df[df['Voucher Number'].isna() | (df['Voucher Number'] == "")]
    empty_parties = df[df['Party Name'].isna() | (df['Party Name'] == "")]
    empty_totals = df[df['Total Invoice Value'].isna() | (df['Total Invoice Value'] == "") | (df['Total Invoice Value'] == "0.00") | (df['Total Invoice Value'] == 0.0)]
    
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
    xml_string = generate_tally_xml_from_df(edited_df.copy())
    
    # Download Buttons
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Edited Excel", 
            data=excel_bytes, 
            file_name="Shubham_Art_Extracted.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="📥 Download Tally XML", 
            data=xml_string, 
            file_name="Shubham_Art_Tally.xml", 
            mime="application/xml"
        )

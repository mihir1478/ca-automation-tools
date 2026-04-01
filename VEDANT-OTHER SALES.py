import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom

st.set_page_config(layout="wide") # Page layout ko wide banaya
st.title("📄 B2B Regular Sales - PDF to Tally XML")
st.write("Apni B2B Invoices ki PDF file yahan upload karein. Agar ek PDF me multiple invoices hain, toh wo automatically split ho jayengi. Data verify/edit karein aur download karein.")

# ==========================================
# ⚙️ CONFIGURATION & HELPERS
# ==========================================
state_codes_map = {
    "01": "Jammu And Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "27": "Maharashtra", "37": "Andhra Pradesh", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman And Nicobar Islands",
    "36": "Telangana", "38": "Ladakh"
}

def safe_float(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace(',', '')
    if val_str == '-' or val_str == '': return 0.0
    try:
        return float(val_str)
    except:
        return 0.0

# ==========================================
# 📄 PDF EXTRACTION LOGIC
# ==========================================
def extract_b2b_invoices(pdf_file_obj):
    text = ""
    with pdfplumber.open(pdf_file_obj) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += "\n" + t

    # Split invoices based on "TAX INVOICE" keyword
    invoices = re.split(r'TAX INVOICE', text)
    rows = []

    for inv in invoices:
        # Invoice Number
        inv_match = re.search(r'VV/\d{2}-\d{2}/\d+', inv)
        if not inv_match: continue
        invoice_no = inv_match.group()

        # Date
        date_match = re.search(r'\d{2}-\d{2}-\d{4}', inv)
        date = date_match.group() if date_match else ""

        # Billing Block
        party = ""
        billing_block = re.search(r'BILLING NAME & ADDRESS(.*?)GSTIN', inv, re.S)
        if billing_block:
            name_match = re.search(r'Name\.\s*(.*)', billing_block.group(1))
            if name_match:
                party = name_match.group(1).strip()
                # REMOVE DOUBLE NAME
                if "Name." in party:
                    party = party.split("Name.")[0].strip()

        # GSTIN
        gst_match = re.search(r'GSTIN\.\s*([A-Z0-9]{15})', inv)
        gstin = gst_match.group(1) if gst_match else ""

        # Totals
        product_match = re.search(r'Product Amount\s*:?\s*([\d,\.]+)', inv)
        product = float(product_match.group(1).replace(",", "")) if product_match else 0

        cgst_match = re.search(r'Add\s*:?\s*CGST\s*:?\s*([\d,\.]+)', inv)
        cgst = float(cgst_match.group(1).replace(",", "")) if cgst_match else 0

        sgst_match = re.search(r'Add\s*:?\s*SGST\s*:?\s*([\d,\.]+)', inv)
        sgst = float(sgst_match.group(1).replace(",", "")) if sgst_match else 0

        igst_match = re.search(r'Add\s*:?\s*IGST\s*:?\s*([\d,\.]+)', inv)
        igst = float(igst_match.group(1).replace(",", "")) if igst_match else 0

        net_match = re.search(r'Net Amount\s*:?\s*([\d,\.]+)', inv)
        net = float(net_match.group(1).replace(",", "")) if net_match else 0

        rows.append({
            "Invoice No": invoice_no,
            "Date": date,
            "Party Name": party,
            "GSTIN": gstin,
            "Taxable Amount": product,
            "CGST": cgst,
            "SGST": sgst,
            "IGST": igst,
            "Total Amount": net
        })
        
    return rows

# ==========================================
# 💻 TALLY XML GENERATION LOGIC
# ==========================================
def generate_xml_from_df(df):
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(req_desc, "REPORTNAME").text = "Vouchers"
    ET.SubElement(ET.SubElement(req_desc, "STATICVARIABLES"), "SVCURRENTCOMPANY").text = "VEDANT VASTRAM"
    
    req_data = ET.SubElement(import_data, "REQUESTDATA")

    grouped_invoices = df.groupby('Invoice No')

    for inv_no, group in grouped_invoices:
        if pd.isna(inv_no) or str(inv_no).strip() == "": 
            continue # Skip row if invoice number is empty
            
        inv_no = str(inv_no).strip()
        first_row = group.iloc[0]
        
        raw_date = str(first_row['Date']).strip()
        try:
            vch_date = pd.to_datetime(raw_date, dayfirst=True, errors='coerce').strftime('%Y%m%d')
        except:
            continue 

        party_name = str(first_row['Party Name']).strip()
        party_gstin = str(first_row['GSTIN']).strip().upper()
        
        party_state_code = party_gstin[:2] if len(party_gstin) >= 2 else "24"
        party_state = state_codes_map.get(party_state_code, "Gujarat")

        # VOUCHER HEADER
        msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        vch = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": "Sales", "ACTION": "Create", "OBJVIEW": "Invoice Voucher View"})
        
        ET.SubElement(vch, "DATE").text = vch_date
        ET.SubElement(vch, "GSTREGISTRATIONTYPE").text = "Regular"
        ET.SubElement(vch, "STATENAME").text = party_state
        ET.SubElement(vch, "COUNTRYOFRESIDENCE").text = "India"
        ET.SubElement(vch, "PARTYGSTIN").text = party_gstin
        ET.SubElement(vch, "PLACEOFSUPPLY").text = party_state
        
        ET.SubElement(vch, "VOUCHERTYPENAME").text = "Sales"
        ET.SubElement(vch, "PARTYNAME").text = party_name
        ET.SubElement(vch, "PARTYLEDGERNAME").text = party_name
        ET.SubElement(vch, "VOUCHERNUMBER").text = inv_no
        ET.SubElement(vch, "PARTYMAILINGNAME").text = party_name
        ET.SubElement(vch, "BASICBUYERNAME").text = party_name
        
        ET.SubElement(vch, "VCHENTRYMODE").text = "Item Invoice"
        ET.SubElement(vch, "ISINVOICE").text = "Yes"
        ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"

        total_inv_val = 0.0
        total_txval = 0.0
        total_igst = 0.0
        total_cgst = 0.0
        total_sgst = 0.0

        # ITEMS LOOP
        for _, row in group.iterrows():
            txval = round(safe_float(row['Taxable Amount']), 2)
            igst = round(safe_float(row['IGST']), 2)
            cgst = round(safe_float(row['CGST']), 2)
            sgst = round(safe_float(row['SGST']), 2)
            item_total = round(safe_float(row['Total Amount']), 2)

            total_inv_val += item_total
            total_txval += txval
            total_igst += igst
            total_cgst += cgst
            total_sgst += sgst

            stock_item_name = "Items @ 5%"

            inv = ET.SubElement(vch, "ALLINVENTORYENTRIES.LIST")
            ET.SubElement(inv, "STOCKITEMNAME").text = stock_item_name
            ET.SubElement(inv, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(inv, "RATE").text = f"{txval}/PCS" 
            ET.SubElement(inv, "AMOUNT").text = str(txval)
            ET.SubElement(inv, "ACTUALQTY").text = " 1 PCS"
            ET.SubElement(inv, "BILLEDQTY").text = " 1 PCS"
            
            acc_alloc = ET.SubElement(inv, "ACCOUNTINGALLOCATIONS.LIST")
            ET.SubElement(acc_alloc, "LEDGERNAME").text = "SALES"
            ET.SubElement(acc_alloc, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(acc_alloc, "AMOUNT").text = str(txval)

        # PARTY LEDGER (Debit)
        party_l = ET.SubElement(vch, "LEDGERENTRIES.LIST")
        ET.SubElement(party_l, "LEDGERNAME").text = party_name
        ET.SubElement(party_l, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(party_l, "AMOUNT").text = f"-{round(total_inv_val, 2)}"

        # TAX LEDGERS (Credit)
        if total_igst > 0:
            tl = ET.SubElement(vch, "LEDGERENTRIES.LIST")
            ET.SubElement(tl, "LEDGERNAME").text = "IGST"
            ET.SubElement(tl, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(tl, "AMOUNT").text = str(round(total_igst, 2))
        
        if total_cgst > 0:
            tl_c = ET.SubElement(vch, "LEDGERENTRIES.LIST")
            ET.SubElement(tl_c, "LEDGERNAME").text = "CGST"
            ET.SubElement(tl_c, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(tl_c, "AMOUNT").text = str(round(total_cgst, 2))
            
            tl_s = ET.SubElement(vch, "LEDGERENTRIES.LIST")
            ET.SubElement(tl_s, "LEDGERNAME").text = "SGST"
            ET.SubElement(tl_s, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(tl_s, "AMOUNT").text = str(round(total_sgst, 2))

        # AUTO ROUND-OFF
        diff = round(total_inv_val - (total_txval + total_igst + total_cgst + total_sgst), 2)
        
        if abs(diff) > 0.00:
            ro_l = ET.SubElement(vch, "LEDGERENTRIES.LIST")
            ET.SubElement(ro_l, "LEDGERNAME").text = "Round Off"  
            
            if diff > 0:
                ET.SubElement(ro_l, "ISDEEMEDPOSITIVE").text = "No"
                ET.SubElement(ro_l, "AMOUNT").text = str(abs(diff))
            else:
                ET.SubElement(ro_l, "ISDEEMEDPOSITIVE").text = "Yes"
                ET.SubElement(ro_l, "AMOUNT").text = f"-{abs(diff)}"

    xml_pretty = minidom.parseString(ET.tostring(envelope)).toprettyxml(indent="  ")
    return xml_pretty

# ==========================================
# 🚀 UI WORKFLOW
# ==========================================
uploaded_pdfs = st.file_uploader("Upload B2B Invoice PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_pdfs:
    if st.button("Extract Data from PDFs", type="primary"):
        with st.spinner("Processing your PDFs... Kripya wait karein."):
            all_rows = []
            
            for pdf_file in uploaded_pdfs:
                try:
                    rows = extract_b2b_invoices(pdf_file)
                    if rows:
                        all_rows.extend(rows)
                except Exception as e:
                    st.error(f"❌ Error in file {pdf_file.name}: {e}")
            
            if all_rows:
                # 1. Create DataFrame
                df = pd.DataFrame(all_rows)
                
                # Enforce logical column order
                cols = ["Invoice No", "Date", "Party Name", "GSTIN", "Taxable Amount", "CGST", "SGST", "IGST", "Total Amount"]
                df = df.reindex(columns=cols)
                
                # Save to session state
                st.session_state['b2b_regular_df'] = df
                st.success(f"✅ Success! {len(all_rows)} invoices extracted successfully.")
            else:
                st.error("❌ Koi valid data extract nahi ho paya. Kripya PDF check karein.")

# Check if data exists in session state to show the interactive table
if 'b2b_regular_df' in st.session_state:
    df = st.session_state['b2b_regular_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields
    empty_vouchers = df[df['Invoice No'].isna() | (df['Invoice No'] == "")]
    empty_parties = df[df['Party Name'].isna() | (df['Party Name'] == "")]
    empty_totals = df[df['Total Amount'].isna() | (df['Total Amount'] == "") | (df['Total Amount'] == 0.0)]
    
    if not empty_vouchers.empty or not empty_parties.empty or not empty_totals.empty:
        st.warning("⚠️ **DHYAN DEIN:** Kuch invoices mein Invoice No, Party Name ya Total Amount theek se extract nahi hua hai. Kripya niche table mein double-click karke theek karein.")
    else:
        st.info("💡 Aap niche diye gaye table mein kisi bhi cell par double-click karke data edit kar sakte hain.")
    
    # Editable Dataframe
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    st.markdown("---")
    st.subheader("💾 Download Final Files")
    st.write("Upar kiye gaye changes automatically niche download hone waali files mein apply ho jayenge.")
    
    # 2. Generate Excel in Memory
    excel_buffer = io.BytesIO()
    edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
    excel_bytes = excel_buffer.getvalue()
    
    # 3. Generate XML String
    xml_string = generate_xml_from_df(edited_df.copy())
    
    # Download Buttons
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Download Edited Excel", 
            data=excel_bytes, 
            file_name="B2B_Invoices_Edited.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col2:
        st.download_button(
            label="📥 Download Tally XML", 
            data=xml_string, 
            file_name="B2B_Regular_Sales_Import.xml", 
            mime="application/xml"
        )

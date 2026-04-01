import streamlit as st
import pandas as pd
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom

st.set_page_config(layout="wide") # Page layout ko wide banaya
st.title("🛒 Mirraw B2B - Excel/CSV to Tally XML")
st.write("Apni Mirraw B2B Sales ki Excel ya CSV file yahan upload karein. Data verify/edit karein aur XML generate karein.")

# ==========================================
# ⚙️ CONFIGURATION & HELPERS
# ==========================================
# State Codes for detecting State from GSTIN
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
# 💻 TALLY XML GENERATION LOGIC
# ==========================================
def generate_mirraw_xml(df):
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    
    # Get Company Name from the first row
    company_name = str(df['Supplier Name'].iloc[0]).strip().upper() if not df.empty and pd.notna(df['Supplier Name'].iloc[0]) else "VEDANT VASTRAM"
    
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(req_desc, "REPORTNAME").text = "Vouchers"
    ET.SubElement(ET.SubElement(req_desc, "STATICVARIABLES"), "SVCURRENTCOMPANY").text = company_name
    req_data = ET.SubElement(import_data, "REQUESTDATA")

    # --- GROUP BY INVOICE NUMBER ---
    grouped_invoices = df.groupby('Invoice No')

    for inv_no, group in grouped_invoices:
        inv_no = str(inv_no).strip()
        if inv_no == 'nan' or not inv_no: continue

        # Header information from the FIRST row
        first_row = group.iloc[0]
        
        raw_date = str(first_row['Date']).strip()
        if raw_date == 'nan' or not raw_date: continue
        try:
            vch_date = pd.to_datetime(raw_date, dayfirst=True, errors='coerce').strftime('%Y%m%d')
        except:
            continue 

        party_gstin = str(first_row['Mirraw GSTIN']).strip().upper()
        cmp_gstin = str(first_row['Vendor GSTIN']).strip().upper()
        party_state_code = party_gstin[:2] if len(party_gstin) >= 2 else "27"
        party_state = state_codes_map.get(party_state_code, "Maharashtra")
        cmp_state = str(first_row['Vendor State']).strip().title() if pd.notna(first_row['Vendor State']) else "Gujarat"

        msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        vch = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": "Sales Online", "ACTION": "Create", "OBJVIEW": "Invoice Voucher View"})
        
        ET.SubElement(vch, "DATE").text = vch_date
        ET.SubElement(vch, "GSTREGISTRATIONTYPE").text = "Regular"
        ET.SubElement(vch, "STATENAME").text = party_state
        ET.SubElement(vch, "COUNTRYOFRESIDENCE").text = "India"
        ET.SubElement(vch, "PARTYGSTIN").text = party_gstin
        ET.SubElement(vch, "PLACEOFSUPPLY").text = party_state
        ET.SubElement(vch, "VOUCHERTYPENAME").text = "Sales Online"
        ET.SubElement(vch, "PARTYMAILINGNAME").text = "MIRRAW ONLINE SERVICES PRIVATE LIMITED"
        ET.SubElement(vch, "PARTYNAME").text = "MIRRAW ONLINE SERVICES PRIVATE LIMITED"
        ET.SubElement(vch, "CMPGSTIN").text = cmp_gstin
        ET.SubElement(vch, "PARTYLEDGERNAME").text = "MIRRAW ONLINE SERVICES PRIVATE LIMITED"
        ET.SubElement(vch, "VOUCHERNUMBER").text = inv_no
        ET.SubElement(vch, "CMPGSTSTATE").text = cmp_state
        ET.SubElement(vch, "VCHENTRYMODE").text = "Item Invoice"
        ET.SubElement(vch, "ISINVOICE").text = "Yes"
        ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"
        ET.SubElement(vch, "BASICBUYERNAME").text = "MIRRAW ONLINE SERVICES PRIVATE LIMITED"

        # Counters for totals
        total_inv_val = 0.0
        total_txval = 0.0
        total_igst = 0.0
        total_cgst = 0.0
        total_sgst = 0.0

        # --- LOOP THROUGH EACH ITEM ---
        for _, row in group.iterrows():
            txval = round(safe_float(row['Taxable Value']), 2)
            igst = round(safe_float(row['IGST']), 2)
            cgst = round(safe_float(row['CGST']), 2)
            sgst = round(safe_float(row['SGST']), 2)
            item_total = round(safe_float(row['Total']), 2)

            total_txval += txval
            total_inv_val += item_total
            total_igst += igst
            total_cgst += cgst
            total_sgst += sgst
            
            hsn_code = str(row['HSN Code']).strip().replace('.0', '')
            tax_rate = str(row['Tax Rate']).strip().replace('.0', '')
            qty = str(row['Quantity']).strip().replace('.0', '')
            stock_item_name = f"HSN_{hsn_code} @ {tax_rate}%"

            inv = ET.SubElement(vch, "ALLINVENTORYENTRIES.LIST")
            ET.SubElement(inv, "STOCKITEMNAME").text = stock_item_name
            ET.SubElement(inv, "GSTHSNNAME").text = hsn_code
            ET.SubElement(inv, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(inv, "AMOUNT").text = str(txval)
            ET.SubElement(inv, "ACTUALQTY").text = f" {qty} PCS"
            ET.SubElement(inv, "BILLEDQTY").text = f" {qty} PCS"
            
            acc_alloc = ET.SubElement(inv, "ACCOUNTINGALLOCATIONS.LIST")
            ET.SubElement(acc_alloc, "LEDGERNAME").text = "Online Sales"
            ET.SubElement(acc_alloc, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(acc_alloc, "AMOUNT").text = str(txval)

        # --- LEDGER ENTRIES ---
        party_l = ET.SubElement(vch, "LEDGERENTRIES.LIST")
        ET.SubElement(party_l, "LEDGERNAME").text = "MIRRAW ONLINE SERVICES PRIVATE LIMITED"
        ET.SubElement(party_l, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(party_l, "AMOUNT").text = f"-{round(total_inv_val, 2)}"

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

        # --- AUTO ROUND-OFF LOGIC ---
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

    # Generate Output
    xml_pretty = minidom.parseString(ET.tostring(envelope)).toprettyxml(indent="  ")
    return xml_pretty


# ==========================================
# 🚀 UI WORKFLOW & PROCESSING
# ==========================================
uploaded_file = st.file_uploader("Upload Mirraw B2B Report (Excel/CSV)", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    if st.button("Load Data", type="primary"):
        with st.spinner("Processing Data... Kripya wait karein."):
            try:
                # 1. File Reading Logic
                if uploaded_file.name.lower().endswith('.csv'):
                    raw_df = pd.read_csv(uploaded_file)
                else:
                    raw_df = pd.read_excel(uploaded_file)
                    
                raw_df.columns = raw_df.columns.str.strip()
                
                if raw_df.empty:
                    st.error("❌ Upload ki gayi file khali hai!")
                else:
                    # 2. Smart Column Detection & Mapping
                    col_inv = next((c for c in raw_df.columns if 'INVOICE NO' in str(c).upper()), 'Sales Invoice No')
                    col_date = next((c for c in raw_df.columns if 'DATE' in str(c).upper()), 'Sales Invoice/Order Date')
                    col_party_gstin = next((c for c in raw_df.columns if 'MIRRAW GSTIN' in str(c).upper()), 'Mirraw GSTIN No')
                    col_cmp_gstin = next((c for c in raw_df.columns if 'VENDOR GST' in str(c).upper()), 'Vendor Gst Number')
                    col_cmp_state = next((c for c in raw_df.columns if 'VENDOR STATE' in str(c).upper()), 'Vendor State')
                    col_supplier = next((c for c in raw_df.columns if 'SUPPLIER NAME' in str(c).upper()), 'Supplier Name')
                    col_taxval = next((c for c in raw_df.columns if 'TAXABLE' in str(c).upper()), 'Taxable value')
                    col_qty = next((c for c in raw_df.columns if 'QUANTITY' in str(c).upper()), 'Quantity')
                    col_hsn = next((c for c in raw_df.columns if 'HSN' in str(c).upper()), 'HSN Code')
                    col_rate = next((c for c in raw_df.columns if 'RATE' in str(c).upper() and 'TAX' in str(c).upper()), 'Rate of Tax')
                    col_total = next((c for c in raw_df.columns if str(c).strip().upper() == 'TOTAL'), 'Total')
                    col_igst = next((c for c in raw_df.columns if 'IGST' in str(c).upper()), 'IGST')
                    col_cgst = next((c for c in raw_df.columns if 'CGST' in str(c).upper()), 'CGST')
                    col_sgst = next((c for c in raw_df.columns if 'SGST' in str(c).upper()), 'SGST')

                    # Build Standardized DataFrame
                    df = pd.DataFrame({
                        'Invoice No': raw_df[col_inv] if col_inv in raw_df.columns else "",
                        'Date': raw_df[col_date] if col_date in raw_df.columns else "",
                        'Mirraw GSTIN': raw_df[col_party_gstin] if col_party_gstin in raw_df.columns else "",
                        'Vendor GSTIN': raw_df[col_cmp_gstin] if col_cmp_gstin in raw_df.columns else "",
                        'Vendor State': raw_df[col_cmp_state] if col_cmp_state in raw_df.columns else "Gujarat",
                        'Supplier Name': raw_df[col_supplier] if col_supplier in raw_df.columns else "VEDANT VASTRAM",
                        'HSN Code': raw_df[col_hsn] if col_hsn in raw_df.columns else "",
                        'Quantity': raw_df[col_qty] if col_qty in raw_df.columns else 0,
                        'Tax Rate': raw_df[col_rate] if col_rate in raw_df.columns else 0,
                        'Taxable Value': raw_df[col_taxval] if col_taxval in raw_df.columns else 0.0,
                        'IGST': raw_df[col_igst] if col_igst in raw_df.columns else 0.0,
                        'CGST': raw_df[col_cgst] if col_cgst in raw_df.columns else 0.0,
                        'SGST': raw_df[col_sgst] if col_sgst in raw_df.columns else 0.0,
                        'Total': raw_df[col_total] if col_total in raw_df.columns else 0.0
                    })

                    # Save into session state
                    st.session_state['mirraw_df'] = df
                    st.success("✅ File loaded successfully! Niche data check karein.")
            except Exception as e: 
                st.error(f"❌ Error aayi hai: {str(e)}")

# Check if data exists in session state to show the interactive table
if 'mirraw_df' in st.session_state:
    df = st.session_state['mirraw_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields
    empty_invoices = df[df['Invoice No'].isna() | (df['Invoice No'] == "")]
    empty_dates = df[df['Date'].isna() | (df['Date'] == "")]
    
    if not empty_invoices.empty or not empty_dates.empty:
        st.warning("⚠️ **DHYAN DEIN:** Kuch rows mein 'Invoice No' ya 'Date' missing hai. Kripya niche table mein double-click karke theek karein.")
    else:
        st.info("💡 Data yahan verify karein. Kisi bhi cell par double-click karke edit kiya ja sakta hai.")

    # Editable Dataframe
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    st.markdown("---")
    st.subheader("💾 Download Final Files")
    st.write("Upar kiye gaye changes automatically niche in files mein apply ho jayenge.")
    
    col1, col2 = st.columns(2)
    
    try:
        # Generate files on the fly from the edited dataframe
        xml_string = generate_mirraw_xml(edited_df)
        
        # Excel generation
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_bytes = excel_buffer.getvalue()

        with col1:
            st.download_button(
                label="📥 Download Edited Excel",
                data=excel_bytes,
                file_name="Mirraw_B2B_Sales_Edited.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            st.download_button(
                label="📥 Download Tally XML",
                data=xml_string,
                file_name="Mirraw_B2B_Grouped_Tally_Import.xml",
                mime="application/xml"
            )
            
    except Exception as e:
        st.error(f"❌ XML Generate karte waqt error: {str(e)}. Kripya check karein ki data sahi format mein ho.")

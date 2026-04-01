import streamlit as st
import pandas as pd
import io
import xml.etree.ElementTree as ET
from xml.dom import minidom

st.set_page_config(layout="wide") # Page ko wide banaya
st.title("🛒 Ajio GST Report to Tally XML")
st.write("Apni Ajio ki Excel ya CSV B2B Report yahan upload karein. Data edit/verify karein aur Tally XML generate karein.")

# ==========================================
# ⚙️ HELPERS & CONFIGURATION
# ==========================================
def safe_float(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace(',', '')
    if val_str == '-' or val_str == '': return 0.0
    try:
        return float(val_str)
    except:
        return 0.0

# ==========================================
# 💻 XML GENERATION LOGIC
# ==========================================
def generate_xml_from_df(df):
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(req_desc, "REPORTNAME").text = "Vouchers"
    ET.SubElement(ET.SubElement(req_desc, "STATICVARIABLES"), "SVCURRENTCOMPANY").text = "DHRUTI CREATION"
    
    req_data = ET.SubElement(import_data, "REQUESTDATA")

    # Group by Invoice No for multi-item invoices
    grouped_invoices = df.groupby('Seller Invoice No')

    for inv_no, group in grouped_invoices:
        inv_no = str(inv_no).strip()
        if inv_no == 'nan' or not inv_no: continue

        first_row = group.iloc[0]
        
        # --- DATE PARSING LOGIC ---
        raw_date = str(first_row.get('Seller Invoice Date', '')).strip()
        if raw_date == 'nan' or not raw_date: continue
        
        clean_date = raw_date.replace("IST ", "").replace("GMT ", "")
        try:
            vch_date = pd.to_datetime(clean_date).strftime('%Y%m%d')
        except:
            continue 

        # --- STATIC PARTY DETAILS (Reliance Retail) ---
        party_name = "Reliance Retail Limited"
        party_gstin = "24AABCR1718E1ZV"
        party_state = "Gujarat"
        cmp_gstin = "24ACIPL7705K1ZF"
        
        msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        vch = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": "Sales Online", "ACTION": "Create", "OBJVIEW": "Invoice Voucher View"})
        
        ET.SubElement(vch, "DATE").text = vch_date
        ET.SubElement(vch, "GSTREGISTRATIONTYPE").text = "Regular"
        ET.SubElement(vch, "STATENAME").text = party_state
        ET.SubElement(vch, "COUNTRYOFRESIDENCE").text = "India"
        ET.SubElement(vch, "PARTYGSTIN").text = party_gstin
        ET.SubElement(vch, "PLACEOFSUPPLY").text = party_state
        
        ET.SubElement(vch, "VOUCHERTYPENAME").text = "Sales Online"
        ET.SubElement(vch, "PARTYNAME").text = party_name
        ET.SubElement(vch, "CMPGSTIN").text = cmp_gstin
        ET.SubElement(vch, "PARTYLEDGERNAME").text = party_name
        ET.SubElement(vch, "VOUCHERNUMBER").text = inv_no
        ET.SubElement(vch, "PARTYMAILINGNAME").text = party_name
        ET.SubElement(vch, "CONSIGNEEMAILINGNAME").text = party_name
        ET.SubElement(vch, "BASICBUYERNAME").text = party_name
        ET.SubElement(vch, "CMPGSTSTATE").text = party_state
        
        ET.SubElement(vch, "VCHENTRYMODE").text = "Item Invoice"
        ET.SubElement(vch, "ISINVOICE").text = "Yes"
        ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"

        # Counters for totals
        total_inv_val = 0.0
        total_txval = 0.0
        total_igst = 0.0
        total_cgst = 0.0
        total_sgst = 0.0

        # --- ITEMS LOOP ---
        for _, row in group.iterrows():
            txval = round(safe_float(row.get('Base Price', 0)), 2) 
            igst = round(safe_float(row.get('IGST AMOUNT', 0)), 2)
            cgst = round(safe_float(row.get('CGST AMOUNT', 0)), 2)
            sgst = round(safe_float(row.get('SGST AMOUNT', 0)), 2)
            
            item_total = round(safe_float(row.get('Invoice Value', 0)), 2) 
            qty = safe_float(row.get('Shipped QTY', 1))
            
            if qty == 0: qty = 1.0 
            item_rate = round(txval / qty, 2)

            total_inv_val += item_total
            total_txval += txval
            total_igst += igst
            total_cgst += cgst
            total_sgst += sgst

            igst_pct = safe_float(row.get('IGST PERCENTAGE', 0))
            cgst_pct = safe_float(row.get('CGST PERCENTAGE', 0))
            sgst_pct = safe_float(row.get('SGST PERCENTAGE', 0))
            tax_rate = igst_pct if igst_pct > 0 else (cgst_pct + sgst_pct)
            if tax_rate == 0: tax_rate = 5.0 
            
            stock_item_name = f"HSN_5407 @ {int(tax_rate)}%"

            # --- INVENTORY ENTRY ---
            inv = ET.SubElement(vch, "ALLINVENTORYENTRIES.LIST")
            ET.SubElement(inv, "STOCKITEMNAME").text = stock_item_name
            ET.SubElement(inv, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(inv, "RATE").text = f"{item_rate}/PCS" 
            ET.SubElement(inv, "AMOUNT").text = str(txval)
            ET.SubElement(inv, "ACTUALQTY").text = f" {int(qty)} PCS"
            ET.SubElement(inv, "BILLEDQTY").text = f" {int(qty)} PCS"
            
            # Sales Ledger Allocation
            acc_alloc = ET.SubElement(inv, "ACCOUNTINGALLOCATIONS.LIST")
            ET.SubElement(acc_alloc, "LEDGERNAME").text = "Online Sales"
            ET.SubElement(acc_alloc, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(acc_alloc, "AMOUNT").text = str(txval)

        # --- PARTY LEDGER (Debit) ---
        party_l = ET.SubElement(vch, "LEDGERENTRIES.LIST")
        ET.SubElement(party_l, "LEDGERNAME").text = party_name
        ET.SubElement(party_l, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(party_l, "AMOUNT").text = f"-{round(total_inv_val, 2)}"

        # --- TAX LEDGERS (Credit) ---
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

    # Output Generation
    xml_pretty = minidom.parseString(ET.tostring(envelope)).toprettyxml(indent="  ")
    return xml_pretty


# ==========================================
# 🚀 STREAMLIT UI WORKFLOW
# ==========================================
uploaded_file = st.file_uploader("Upload Ajio Report (Excel/CSV)", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    if st.button("Load File Data", type="primary"):
        with st.spinner("Processing Ajio Data... Kripya wait karein."):
            try:
                if uploaded_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                df.columns = df.columns.str.strip()
                
                if df.empty:
                    st.error("⚠️ Upload ki gayi file khali hai!")
                else:
                    # Save to session state for interactive editing
                    st.session_state['ajio_df'] = df
                    st.success("✅ File loaded successfully!")
            except Exception as e: 
                st.error(f"❌ Error aayi hai: {str(e)}")

# Check if data is loaded in session state
if 'ajio_df' in st.session_state:
    df = st.session_state['ajio_df']
    
    st.markdown("---")
    st.subheader("📊 Validate & Edit Extracted Data")
    
    # Check for missing crucial fields based on what the XML parser needs
    if 'Seller Invoice No' in df.columns and 'Seller Invoice Date' in df.columns:
        empty_invoices = df[df['Seller Invoice No'].isna() | (df['Seller Invoice No'] == "")]
        empty_dates = df[df['Seller Invoice Date'].isna() | (df['Seller Invoice Date'] == "")]
        
        if not empty_invoices.empty or not empty_dates.empty:
            st.warning("⚠️ **DHYAN DEIN:** Kuch rows mein 'Seller Invoice No' ya 'Seller Invoice Date' missing hai. Kripya table mein double-click karke theek karein.")
        else:
            st.info("💡 Data yahan verify karein. Kisi cell ko edit karne ke liye uspe double-click karein.")
    else:
        st.error("❌ File mein 'Seller Invoice No' ya 'Seller Invoice Date' columns missing hain. Kripya sahi report upload karein.")

    # Show editable dataframe
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    
    st.markdown("---")
    st.subheader("💾 Download Final Files")
    st.write("Upar kiye gaye changes automatically in files mein apply ho jayenge.")
    
    col1, col2 = st.columns(2)
    
    try:
        # Generate files on the fly from the edited dataframe
        xml_string = generate_xml_from_df(edited_df)
        
        # Adding Excel download option just like the other scripts
        excel_buffer = io.BytesIO()
        edited_df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_bytes = excel_buffer.getvalue()

        with col1:
            st.download_button(
                label="📥 Download Edited Excel",
                data=excel_bytes,
                file_name="Ajio_B2B_Sales_Edited.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            st.download_button(
                label="📥 Download Tally XML",
                data=xml_string,
                file_name="Ajio_B2B_Sales_Import.xml",
                mime="application/xml"
            )
            
    except Exception as e:
        st.error(f"❌ XML Generate karte waqt error: {str(e)}. Kripya check karein ki zaroori columns exist karte hain.")

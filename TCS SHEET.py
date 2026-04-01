import streamlit as st
import pandas as pd
import json
import io
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

st.title("📊 TCS Credit - GSTR1 JSON & Tally XML")
st.write("Apni TCS Credit Original Excel file yahan upload karein. B2CS aur ECO Summary ke saath JSON aur 'Unregistered' party ke roop me Tally XML generate hoga.")

# ==========================================
# ⚙️ MAPPINGS & CONFIGURATION
# ==========================================
state_codes = {
    "JAMMU AND KASHMIR": "01", "HIMACHAL PRADESH": "02", "PUNJAB": "03", "CHANDIGARH": "04",
    "UTTARAKHAND": "05", "HARYANA": "06", "DELHI": "07", "RAJASTHAN": "08", "UTTAR PRADESH": "09",
    "BIHAR": "10", "SIKKIM": "11", "ARUNACHAL PRADESH": "12", "ASSAM": "18", "WEST BENGAL": "19",
    "JHARKHAND": "20", "ODISHA": "21", "CHHATTISGARH": "22", "MADHYA PRADESH": "23", "GUJARAT": "24",
    "MAHARASHTRA": "27", "ANDHRA PRADESH": "37", "KARNATAKA": "29", "GOA": "30", "LAKSHADWEEP": "31",
    "KERALA": "32", "TAMIL NADU": "33", "PUDUCHERRY": "34", "ANDAMAN AND NICOBAR ISLANDS": "35",
    "TELANGANA": "36", "LADAKH": "38"
}
code_to_state = {v: k.title() for k, v in state_codes.items()}
month_map = {"JANUARY": "01", "FEBRUARY": "02", "MARCH": "03", "APRIL": "04", "MAY": "05", "JUNE": "06",
             "JULY": "07", "AUGUST": "08", "SEPTEMBER": "09", "OCTOBER": "10", "NOVEMBER": "11", "DECEMBER": "12"}

def safe_scan(df, keyword):
    for r in range(min(len(df), 15)):
        for c in range(len(df.columns)):
            if keyword in str(df.iloc[r, c]).upper():
                for next_c in range(c + 1, len(df.columns)):
                    val = str(df.iloc[r, next_c]).strip()
                    if val != 'nan' and val != '': return val
    return ""

def get_party_ledger_name(collector_name):
    name = str(collector_name).upper()
    if "MEESHO" in name: return "Selling Through Meesho"
    elif "AMAZON" in name: return "Selling Through Amazon"
    elif "FLIPKART" in name: return "Selling Through Flipkart"
    else: return "Selling Through Other E-Com. Platform"

# ==========================================
# 🚀 UI WORKFLOW & LOGIC
# ==========================================
uploaded_files = st.file_uploader("Upload TCS Credit Excel file", type=["xlsx", "xls"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Process & Generate Files", type="primary"):
        with st.spinner("Processing your Excel files..."):
            for uploaded_file in uploaded_files:
                try:
                    # Header Scan
                    df_head = pd.read_excel(uploaded_file, sheet_name='TCS Credit Original', nrows=12, header=None)
                    gstin_raw = safe_scan(df_head, "GSTIN:")
                    gstin_search = re.search(r'\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{3}', gstin_raw if gstin_raw else str(df_head))
                    gstin = gstin_search.group(0) if gstin_search else "UNKNOWN_GSTIN"
                    
                    p_text = safe_scan(df_head, "PERIOD:").upper()
                    years = re.findall(r'20\d{2}', " ".join(df_head.astype(str).values.flatten()))
                    
                    # Quarter / Month Logic
                    if any(q in p_text for q in ["QUARTER-4", "Q4"]): m_code, year = "03", (max(years) if years else "2026")
                    elif any(q in p_text for q in ["QUARTER-3", "Q3"]): m_code, year = "12", (min(years) if years else "2025")
                    elif any(q in p_text for q in ["QUARTER-2", "Q2"]): m_code, year = "09", (min(years) if years else "2025")
                    elif any(q in p_text for q in ["QUARTER-1", "Q1"]): m_code, year = "06", (min(years) if years else "2025")
                    elif any(m in p_text for m in month_map):
                        det_m = next(m for m in month_map if m in p_text)
                        m_code = month_map[det_m]
                        year = max(years) if m_code in ["01","02","03"] else (min(years) if years else "2025")
                    else:
                        m_code, year = "03", "2026"
                        
                    fp = f"{m_code}{year}"

                    # Data Loading
                    df_data = pd.read_excel(uploaded_file, sheet_name='TCS Credit Original', skiprows=5)
                    df_data.columns = df_data.columns.str.strip()
                    if df_data.empty: 
                        st.warning(f"File {uploaded_file.name} is empty or invalid.")
                        continue
                    
                    if 'Name of Collector' not in df_data.columns:
                        df_data['Name of Collector'] = 'Other'

                    # --- 1. JSON B2CS ---
                    b2cs_list = []
                    grouped_pos = df_data.groupby('Pos')['Net Value'].sum().reset_index()

                    for _, row in grouped_pos.iterrows():
                        txval = round(float(row['Net Value']), 2)
                        if txval == 0: continue
                        
                        p_code = state_codes.get(str(row['Pos']).strip().upper(), "24")
                        if p_code == "24": iamt, camt, samt = 0.0, round(txval * 0.025, 2), round(txval * 0.025, 2)
                        else: iamt, camt, samt = round(txval * 0.05, 2), 0.0, 0.0
                            
                        b2cs_list.append({
                            "sply_ty": "INTRA" if p_code == "24" else "INTER", "rt": 5.0, "typ": "OE", "pos": p_code,
                            "txval": txval, "iamt": iamt, "camt": camt, "samt": samt, "csamt": 0.0
                        })

                    # --- 2. ECO SUMMARY ---
                    eco_tax_dict = {}
                    df_data['GSTIN of Collector'] = df_data['GSTIN of Collector'].fillna('UNKNOWN')
                    grouped_eco = df_data.groupby(['GSTIN of Collector', 'Pos'])['Net Value'].sum().reset_index()

                    for _, row in grouped_eco.iterrows():
                        eco_gstin = str(row['GSTIN of Collector']).strip()
                        if eco_gstin in ['UNKNOWN', '', 'nan']: continue
                        txval = round(float(row['Net Value']), 2)
                        if txval == 0: continue 
                        
                        p_code = state_codes.get(str(row['Pos']).strip().upper(), "24")
                        if p_code == "24": i, c, s = 0.0, round(txval * 0.025, 2), round(txval * 0.025, 2)
                        else: i, c, s = round(txval * 0.05, 2), 0.0, 0.0
                            
                        if eco_gstin not in eco_tax_dict: eco_tax_dict[eco_gstin] = {"suppval": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0}
                        eco_tax_dict[eco_gstin]["suppval"] += txval; eco_tax_dict[eco_gstin]["igst"] += i
                        eco_tax_dict[eco_gstin]["cgst"] += c; eco_tax_dict[eco_gstin]["sgst"] += s

                    eco_summary = [{"etin": k, "suppval": round(v["suppval"], 2), "igst": round(v["igst"], 2), "cgst": round(v["cgst"], 2), "sgst": round(v["sgst"], 2), "cess": 0.0, "flag": "N"} for k, v in eco_tax_dict.items()]

                    # --- 3. TALLY XML ---
                    envelope = ET.Element("ENVELOPE")
                    header = ET.SubElement(envelope, "HEADER")
                    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
                    body = ET.SubElement(envelope, "BODY")
                    import_data = ET.SubElement(body, "IMPORTDATA")
                    req_data = ET.SubElement(import_data, "REQUESTDATA")

                    grouped_xml = df_data.groupby(['Name of Collector', 'Pos'])['Net Value'].sum().reset_index()

                    for idx, row in grouped_xml.iterrows():
                        txval = round(float(row['Net Value']), 2)
                        if txval == 0: continue
                        
                        p_code = state_codes.get(str(row['Pos']).strip().upper(), "24")
                        s_name = code_to_state.get(p_code, "Gujarat")
                        party_name = get_party_ledger_name(row['Name of Collector'])
                        
                        if p_code == "24": iamt, camt, samt = 0.0, round(txval * 0.025, 2), round(txval * 0.025, 2)
                        else: iamt, camt, samt = round(txval * 0.05, 2), 0.0, 0.0
                            
                        total_inv_val = round(txval + iamt + camt + samt, 2)
                        party_amt = round(-total_inv_val, 2)

                        msg = ET.SubElement(req_data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
                        vch = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": "Sales Online", "ACTION": "Create", "OBJVIEW": "Invoice Voucher View"})
                        
                        vch_day = "30" if m_code in ["04", "06", "09", "11"] else ("28" if m_code == "02" else "31")
                        ET.SubElement(vch, "DATE").text = f"{year}{m_code}{vch_day}"
                        
                        # --- FIX applied here ---
                        ET.SubElement(vch, "GSTREGISTRATIONTYPE").text = "Unregistered"
                        # ------------------------

                        ET.SubElement(vch, "STATENAME").text = s_name
                        ET.SubElement(vch, "COUNTRYOFRESIDENCE").text = "India"
                        ET.SubElement(vch, "PLACEOFSUPPLY").text = s_name
                        
                        ET.SubElement(vch, "VOUCHERTYPENAME").text = "Sales Online"
                        ET.SubElement(vch, "VCHSTATUSVOUCHERTYPE").text = "Sales Online"
                        
                        ET.SubElement(vch, "PARTYLEDGERNAME").text = party_name 
                        ET.SubElement(vch, "VOUCHERNUMBER").text = f"{m_code}/OT/{str(idx+1).zfill(3)}"
                        ET.SubElement(vch, "VCHENTRYMODE").text = "Item Invoice"
                        ET.SubElement(vch, "ISINVOICE").text = "Yes"
                        ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"
                        ET.SubElement(vch, "CONSIGNEESTATENAME").text = s_name
                        ET.SubElement(vch, "CONSIGNEECOUNTRYNAME").text = "India"
                        ET.SubElement(vch, "BASICBUYERNAME").text = party_name 
                        
                        inv = ET.SubElement(vch, "ALLINVENTORYENTRIES.LIST")
                        ET.SubElement(inv, "STOCKITEMNAME").text = "Items @ 5%"
                        ET.SubElement(inv, "ISDEEMEDPOSITIVE").text = "No"
                        ET.SubElement(inv, "AMOUNT").text = str(txval)
                        
                        acc_alloc = ET.SubElement(inv, "ACCOUNTINGALLOCATIONS.LIST")
                        ET.SubElement(acc_alloc, "LEDGERNAME").text = "Online Sales"
                        ET.SubElement(acc_alloc, "ISDEEMEDPOSITIVE").text = "No"
                        ET.SubElement(acc_alloc, "AMOUNT").text = str(txval)

                        party_l = ET.SubElement(vch, "LEDGERENTRIES.LIST")
                        ET.SubElement(party_l, "LEDGERNAME").text = party_name 
                        ET.SubElement(party_l, "ISDEEMEDPOSITIVE").text = "Yes"
                        ET.SubElement(party_l, "AMOUNT").text = str(party_amt)

                        for t_name, t_amt in [("Output IGST", iamt), ("Output CGST", camt), ("Output SGST", samt)]:
                            if t_amt != 0: 
                                tl = ET.SubElement(vch, "LEDGERENTRIES.LIST")
                                ET.SubElement(tl, "LEDGERNAME").text = t_name
                                ET.SubElement(tl, "ISDEEMEDPOSITIVE").text = "No"
                                ET.SubElement(tl, "AMOUNT").text = str(t_amt)

                    # --- 4. GSTR-1 JSON GENERATION ---
                    hsn = {"hsn_b2c": [], "hsn_b2b": [{"rt": 5.0, "txval": 1.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "num": 1, "hsn_sc": "5407", "desc": "FABRICS", "uqc": "OTH", "qty": 1.0}]}
                    
                    m_name = next((k for k, v in month_map.items() if v == m_code), "MARCH")
                    doc_issue = {"doc_det": [{"doc_num": 1, "doc_typ": "Invoice for outward supply", "docs": [{"num": 1, "from": f"{m_name}{year}", "to": f"{m_name}{year}", "totnum": 1, "cancel": 0, "net_issue": 1}]}]}
                    
                    final_json = {
                        "gstin": gstin, "fp": fp, "gt": 0.0, "cur_gt": 0.0,
                        "b2b": [], "b2cl": [], "b2cs": b2cs_list, "cdnr": [], "cdnur": [], "exp": [], "at": [], "atadj": [], "nil": {"inv": []},
                        "hsn": hsn, "doc_issue": doc_issue, "supeco": {"clttx": eco_summary}
                    }

                    # Generate strings for download
                    json_string = json.dumps(final_json, indent=4)
                    xml_pretty = minidom.parseString(ET.tostring(envelope)).toprettyxml(indent="  ")

                    st.success(f"✅ SUCCESS for {uploaded_file.name}! Party Details ab 'Unregistered' show karengi.")
                    
                    # Layout in 2 columns for download buttons
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="📥 Download Tally XML",
                            data=xml_pretty,
                            file_name=f"Tally_Import_{fp}.xml",
                            mime="application/xml"
                        )
                    with col2:
                        st.download_button(
                            label="📥 Download GSTR-1 JSON",
                            data=json_string,
                            file_name=f"GSTR1_{gstin}_{fp}.json",
                            mime="application/json"
                        )
                        
                except Exception as e:
                    st.error(f"❌ Error in {uploaded_file.name}: {str(e)}")

import streamlit as st
import pandas as pd
import uuid
import io

st.title("📦 GSTR to Tally Purchase XML")
st.write("Apni GSTR Excel file (B2B Sheet) yahan upload karein, Tally Item Invoice format mein XML generate karne ke liye.")

# --- ⚙️ CONFIGURATION ---
COMPANY_NAME = "BHAGVATI FEB"  # Tally Company ka naam
SHEET_NAME = "B2B"

# 🇮🇳 GST State Codes Dictionary
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
# ------------------------

uploaded_file = st.file_uploader("Upload GSTR Excel File", type=["xlsx", "xls"])

if uploaded_file is not None:
    if st.button("Generate Purchase XML", type="primary"):
        with st.spinner("Processing GSTR Data..."):
            try:
                # File reading logic
                df = pd.read_excel(uploaded_file, sheet_name=SHEET_NAME, skiprows=6, header=None)
                vouchers_dict = {}

                for index, row in df.iterrows():
                    inv_no = str(row[2]).strip()
                    party_gstin = str(row[0]).strip()
                    
                    if pd.isna(row[2]) or inv_no == "nan" or inv_no == "":
                        continue
                        
                    unique_key = f"{inv_no}_{party_gstin}"
                    
                    if unique_key not in vouchers_dict:
                        state_code = party_gstin[:2]
                        party_state = GST_STATE_CODES.get(state_code, "Not Applicable")

                        raw_pos = str(row[6]).strip()
                        if raw_pos == "nan" or raw_pos == "":
                            pos = party_state
                        else:
                            pos = raw_pos.split('-')[1].strip() if '-' in raw_pos else raw_pos

                        vouchers_dict[unique_key] = {
                            'inv_no': inv_no,
                            'party_gstin': party_gstin,
                            'party_name': str(row[1]).replace('&', '&amp;').strip(),
                            'date': row[4],
                            'state': party_state,
                            'pos': pos,
                            'inv_val': float(row[5]) if not pd.isna(row[5]) else 0.0,
                            'items': []
                        }
                    
                    rate = float(row[8]) if not pd.isna(row[8]) else 0.0
                    vouchers_dict[unique_key]['items'].append({
                        'rate': rate,
                        'taxable_val': float(row[9]) if not pd.isna(row[9]) else 0.0,
                        'igst': float(row[10]) if not pd.isna(row[10]) else 0.0,
                        'cgst': float(row[11]) if not pd.isna(row[11]) else 0.0,
                        'sgst': float(row[12]) if not pd.isna(row[12]) else 0.0
                    })

                # --- XML GENERATION ---
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

                for unique_key, v_data in vouchers_dict.items():
                    raw_date = v_data['date']
                    if isinstance(raw_date, str):
                        raw_date = raw_date.replace('/', '-')
                    
                    date_obj = pd.to_datetime(raw_date, dayfirst=True, errors='coerce')
                    if pd.isna(date_obj):
                        continue
                        
                    tally_date = date_obj.strftime('%Y%m%d')
                    
                    total_taxable = 0
                    total_igst = 0
                    total_cgst = 0
                    total_sgst = 0
                    item_xml_list = ""
                    
                    for item in v_data['items']:
                        total_taxable += item['taxable_val']
                        total_igst += item['igst']
                        total_cgst += item['cgst']
                        total_sgst += item['sgst']
                        
                        item_name = f"purchase@{int(item['rate'])}%"
                        
                        # Fix for ALLINVENTORYENTRIES (putting ACCOUNTINGALLOCATIONS inside it properly)
                        item_xml_list += f"""
      <ALLINVENTORYENTRIES.LIST>
       <STOCKITEMNAME>{item_name}</STOCKITEMNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{item['taxable_val']:.2f}</AMOUNT>
       <ACCOUNTINGALLOCATIONS.LIST>
        <LEDGERNAME>Purchase</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{item['taxable_val']:.2f}</AMOUNT>
       </ACCOUNTINGALLOCATIONS.LIST>
      </ALLINVENTORYENTRIES.LIST>"""
                    
                    round_off = round((total_taxable + total_igst + total_cgst + total_sgst) - v_data['inv_val'], 2)
                    guid = str(uuid.uuid4())
                    
                    voucher_xml = f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
     <VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">
      <DATE>{tally_date}</DATE>
      <GUID>{guid}</GUID>
      <STATENAME>{v_data['state']}</STATENAME>
      <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
      <PARTYGSTIN>{v_data['party_gstin']}</PARTYGSTIN>
      <PLACEOFSUPPLY>{v_data['pos']}</PLACEOFSUPPLY>
      <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
      <PARTYNAME>{v_data['party_name']}</PARTYNAME>
      <PARTYLEDGERNAME>{v_data['party_name']}</PARTYLEDGERNAME>
      <VOUCHERNUMBER>{v_data['inv_no']}</VOUCHERNUMBER>
      <REFERENCE>{v_data['inv_no']}</REFERENCE>
      <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
      <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
      <ISINVOICE>Yes</ISINVOICE>
      <ISELIGIBLEFORITC>Yes</ISELIGIBLEFORITC>
      
      {item_xml_list}
      
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>{v_data['party_name']}</LEDGERNAME>
       <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
       <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
       <AMOUNT>{v_data['inv_val']:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>
"""
                    if total_cgst > 0:
                        voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>CGST</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{total_cgst:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>"""
                      
                    if total_sgst > 0:
                        voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>SGST</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{total_sgst:.2f}</AMOUNT>
      </LEDGERENTRIES.LIST>"""
                      
                    if total_igst > 0:
                        voucher_xml += f"""
      <LEDGERENTRIES.LIST>
       <LEDGERNAME>IGST</LEDGERNAME>
       <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
       <AMOUNT>-{total_igst:.2f}</AMOUNT>
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

                if success_count > 0:
                    st.success(f"🎉 Success! Total {success_count} Purchase Vouchers generated.")
                    
                    st.download_button(
                        label="📥 Download Tally XML",
                        data=xml_data,
                        file_name="Tally_Purchases_Import.xml",
                        mime="application/xml"
                    )
                else:
                    st.warning("⚠️ Koi valid data nahi mila process karne ke liye.")

            except Exception as e:
                st.error(f"❌ Error aayi hai: {str(e)}")
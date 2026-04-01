import streamlit as st
import requests
import xmltodict
import pandas as pd
import re

# Streamlit page configuration
st.set_page_config(page_title="Tally Automation Interface", layout="wide")

st.title("📊 Tally Data Fetcher (Fully Updated)")
st.write("Apne Python automation scripts ko yahan se direct run karein. (Educational Mode Supported)")

# Tally Server ka Local URL
TALLY_URL = "http://localhost:9000"

# Tally ko bhejne ke liye XML Request (Exporting List of Accounts)
xml_payload = """<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <EXPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>List of Accounts</REPORTNAME>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                </STATICVARIABLES>
            </REQUESTDESC>
        </EXPORTDATA>
    </BODY>
</ENVELOPE>"""

if st.button("Fetch Ledgers from Tally"):
    with st.spinner("Tally se data fetch ho raha hai..."):
        try:
            # Tally API ko request bhejna
            response = requests.post(TALLY_URL, data=xml_payload)
            
            if response.status_code == 200:
                st.success("Data successfully fetched from Tally!")
                
                # Raw XML text lena
                raw_xml = response.text
                
                # --- ERROR FIX 1: Invalid XML Control Characters ko remove karna ---
                clean_xml = re.sub(r'&#x[0-1]?[0-9A-Fa-f];', '', raw_xml)
                clean_xml = re.sub(r'&#[0-3]?[0-9];', '', clean_xml)
                
                try:
                    # Clean ki hui XML ko Python dictionary me convert karna
                    data_dict = xmltodict.parse(clean_xml)
                    
                    # --- ERROR FIX 2: Tally ke naye data structure (IMPORTDATA) ko handle karna ---
                    # Tally apne masters data ko IMPORTDATA -> REQUESTDATA -> TALLYMESSAGE me bhejta hai
                    messages = data_dict['ENVELOPE']['BODY']['IMPORTDATA']['REQUESTDATA']['TALLYMESSAGE']
                    
                    # Ensure karein ki messages ek list ho (agar sirf ek message ho toh error na aaye)
                    if not isinstance(messages, list):
                        messages = [messages]
                        
                    ledger_data = []
                    
                    # Har message block ko check karein
                    for msg in messages:
                        # Agar us block me 'LEDGER' ka data hai, toh hi usko extract karein
                        if 'LEDGER' in msg:
                            ledger = msg['LEDGER']
                            
                            # Tally ek sath multiple ledgers bhej sakta hai (list) ya single (dict)
                            if isinstance(ledger, list):
                                for l in ledger:
                                    ledger_data.append({
                                        "Ledger Name": l.get('@NAME', 'Unknown'), 
                                        "Group": l.get('PARENT', 'Unknown')
                                    })
                            else:
                                ledger_data.append({
                                    "Ledger Name": ledger.get('@NAME', 'Unknown'), 
                                    "Group": ledger.get('PARENT', 'Unknown')
                                })
                    
                    # Agar ledgers extract ho gaye toh table banakar display karein
                    if len(ledger_data) > 0:
                        df = pd.DataFrame(ledger_data)
                        
                        # Dataframe ko thoda clean dikhane ke liye index hide karna
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        st.info(f"✅ Total Ledgers Found: {len(df)}")
                    else:
                        st.warning("Data fetch hua, par is company mein koi Ledger nahi mila.")
                        
                except KeyError as e:
                    st.warning("Tally ka data format match nahi hua. Neeche raw data check karein.")
                    with st.expander("Show Raw XML Data (For Debugging)"):
                        st.code(clean_xml[:2000]) # Shuruwati 2000 characters print karega
                        
                except Exception as e:
                    st.error(f"Data parse karne mein error aayi: {e}")
                    
            else:
                st.error(f"Server Error: Status Code {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            st.error("Tally Server se connect nahi ho paaya. Kripya check karein ki Tally open hai aur Port 9000 par 'Tally as ERP Server' enable hai.")

import streamlit as st
import pandas as pd
import os

# Page Configuration
st.set_page_config(page_title="HSN & SAC Search Tool", page_icon="🔍", layout="wide")

@st.cache_data
def load_data():
    # Current folder path nikalna jahan app.py save hai
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Excel file exactly usi folder me hai, toh direct naam attach karna hai
    excel_path = os.path.join(current_dir, 'HSN_SAC.xlsx')
    
    # Check if file exists to avoid errors
    if not os.path.exists(excel_path):
        st.error(f"❌ File nahi mili is location par: {excel_path}\nKripya check karein ki 'HSN_SAC.xlsx' isi folder me hai.")
        return pd.DataFrame()

    try:
        # Excel file se dono sheets read karna (openpyxl engine zaroori hai)
        hsn_df = pd.read_excel(excel_path, sheet_name='HSN_MSTR', engine='openpyxl')
        sac_df = pd.read_excel(excel_path, sheet_name='SAC_MSTR', engine='openpyxl')
        
        # Columns rename karna taaki dono easily merge ho jayein
        hsn_df = hsn_df.rename(columns={'HSN_CD': 'Code', 'HSN_Description': 'Description'})
        hsn_df['Type'] = 'HSN (Goods)'
        
        sac_df = sac_df.rename(columns={'SAC_CD': 'Code', 'SAC_Description': 'Description'})
        sac_df['Type'] = 'SAC (Services)'
        
        # Handle empty/NaN values aur unhe string me convert karna search ke liye
        hsn_df['Code'] = hsn_df['Code'].fillna('').astype(str)
        sac_df['Code'] = sac_df['Code'].fillna('').astype(str)
        hsn_df['Description'] = hsn_df['Description'].fillna('').astype(str)
        sac_df['Description'] = sac_df['Description'].fillna('').astype(str)
        
        # Dono DataFrames ko combine karna
        combined_df = pd.concat([hsn_df, sac_df], ignore_index=True)
        return combined_df
        
    except Exception as e:
        st.error(f"❌ Error reading Excel file: {e}\n(Make sure openpyxl is installed: pip install openpyxl)")
        return pd.DataFrame()

# Data load function call karein
df = load_data()

# UI Layout
st.title("GST HSN & SAC Search Tool 🔍")
st.markdown("Aasani se HSN (Goods) aur SAC (Services) codes ko unke number ya description se search karein.")

# User Inputs
col1, col2 = st.columns([2, 1])

with col1:
    search_query = st.text_input("Enter Code ya Description yahan type karein:", "")

with col2:
    filter_type = st.radio("Category Filter:", ["All", "Only HSN", "Only SAC"], horizontal=True)

st.divider()

# Data Filtering Logic
if not df.empty:
    filtered_df = df.copy()

    # Filter by Type (HSN/SAC)
    if filter_type == "Only HSN":
        filtered_df = filtered_df[filtered_df['Type'] == 'HSN (Goods)']
    elif filter_type == "Only SAC":
        filtered_df = filtered_df[filtered_df['Type'] == 'SAC (Services)']

    # Filter by Search Query
    if search_query:
        search_query = search_query.lower()
        mask = filtered_df['Code'].str.lower().str.contains(search_query) | \
               filtered_df['Description'].str.lower().str.contains(search_query)
        filtered_df = filtered_df[mask]

    # Results Display
    st.write(f"**Total Results Found:** `{len(filtered_df)}`")

    if len(filtered_df) > 0:
        st.dataframe(
            filtered_df[['Type', 'Code', 'Description']], 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.warning("Koi result nahi mila. Kripya apna search term check karein.")
else:
    st.info("⚠️ Data load nahi ho paya. Kripya upar diye gaye error message ko check karein.")

import streamlit as st
import os

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="FREYORA Master Dashboard", page_icon="🚀", layout="wide")

# ==========================================
# 🎨 2. HYBRID THEME (CLEAN CSS)
# ==========================================
st.markdown("""
<style>
    /* 1. SIRF SIDEBAR KO DARK KAREIN */
    [data-testid="stSidebar"] {
        background-color: #0E1117 !important;
    }
    
    [data-testid="stSidebar"] p, 
    [data-testid="stSidebar"] span, 
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebarNav"] a,
    [data-testid="stSidebar"] svg {
        color: #FAFAFA !important;
        fill: #FAFAFA !important;
    }

    [data-testid="stSidebarNav"] li a {
        border-radius: 8px;
        margin: 4px 10px;
        transition: all 0.3s ease;
    }
    [data-testid="stSidebarNav"] li a:hover {
        background-color: #262730 !important;
        transform: translateX(5px);
    }

    /* 2. PREMIUM BUTTONS */
    .stButton > button {
        background: linear-gradient(45deg, #6C63FF, #4B45CC) !important;
        color: white !important;
        border: none !important;
        padding: 10px 24px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 15px rgba(108, 99, 255, 0.2) !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(108, 99, 255, 0.4) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🚀 3. DYNAMIC AUTO-DISCOVERY ROUTER
# ==========================================
pages_dict = {}

if os.path.exists("home.py"):
    pages_dict["🏠 Main Menu"] = [st.Page("home.py", title="Home Dashboard", icon="🏠", default=True)]

scripts_folder = "scripts"

if os.path.exists(scripts_folder):
    categories = sorted([f for f in os.listdir(scripts_folder) if os.path.isdir(os.path.join(scripts_folder, f))])
    
    for category in categories:
        cat_path = os.path.join(scripts_folder, category)
        python_files = sorted([f for f in os.listdir(cat_path) if f.endswith('.py')])
        
        page_list = []
        for file in python_files:
            file_path = os.path.join(cat_path, file)
            title = file.replace('.py', '')
            page_list.append(st.Page(file_path, title=title, icon="⚙️"))
        
        if page_list:
            clean_category_name = category.split('_', 1)[-1] if '_' in category else category
            pages_dict[f"📂 {clean_category_name}"] = page_list

# ==========================================
# 4. RUN NAVIGATION
# ==========================================
if pages_dict:
    pg = st.navigation(pages_dict)
    pg.run()
else:
    st.error("⚠️ Koi scripts nahi mili. Kripya 'scripts' folder check karein.")

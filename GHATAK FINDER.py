import streamlit as st
import pandas as pd
import io

# 1. Page Configuration (Agar aap is page ko kisi dusri multi-page app ke andar use kar rahe hain, 
# toh yeh line hata sakte hain agar already main file mein set_page_config lagi hui hai)
st.set_page_config(page_title="Ghatak Finder", layout="wide", page_icon="📍")

st.title("📍 GHATAK FINDER")
st.markdown("Yeh tool aapko Division, Range, Ghatak, Area Code ya Locality ke hisaab se jurisdiction find karne mein madad karega.")

# 2. Extracted Clean Data (Ahmedabad Sample + Surat FULL DATA)
@st.cache_data
def load_data():
    csv_data = """Division,Range,Ghatak,Area Code,Area Name,Locality Description
Ahmedabad,1,1,0704,KALUPUR,"All regions covered in & between: Kalupur, Chokha bazaar Revdi bazaar, Hirabhai Market"
Ahmedabad,1,1,0710,PANCHKUVA,"All regions covered in & between Jhakaria Masjid to kalupur station -- to Panchkuva darwaja to Khadia char rasta"
Ahmedabad,1,2,0705,GHEEKANTA,"All regions covered in & between Gheekanta Rd.-murtimant complex -- old prakash cinema --Pitaliya bamba -- Delhi darwaja-- to kalupur Swaminarayan temple"
Ahmedabad,1,2,0706,DARIAPUR,"All regions covered in & between swaminarayan temple Dariapur, kazipur, Dabgarwaad to delhi darwaja interior of prem darwaja areas"
Ahmedabad,1,3,0707,KHANPUR,"All regions covered in & between Nehrubridge Indian Airlines to --Khanpur, Mirzapur, Qutubshah mosque inside regions of delhi darwaja - shahpur mill compound Relief cinema via salapose road"
Ahmedabad,1,3,0708,TEEN DARWAJA,"All regions covered in & between: From Nehrubridge -Sidi saiyad jali to-- Relief road --vijali ghar to pattharkuva-- Gheekanta cross roads -- to Pankornaka -- karanj police station tel exchange to & sidi saiyad jali"
Ahmedabad,1,3,0712,LAL DARWAJA,"All regions covered from ellisbridge end --victoria garden laldarwaja bus terminus-- bhadra to pankornaka, dhalgarwaad - danapith-- Manek chowk- municiapal corporation Akhandannd ayurvedic hopital Khamasa to Astodia cross roads"
Ahmedabad,1,3,0713,MANEK CHOWK,"All regions covered in & between: From Pankornaka to Raipur chakla to Raipur Darwaja -- chandla od -- sankadi sheri --regions north to Manekchowk to Astodia Chakala cross roads, gol limda Gandhi Road and back"
Ahmedabad,2,4,0709,KHADIA,"All regions covered in & between: From Gheekanta cross roads to jhakaria masjid, to khadia cross roads till Pankornaka"
Ahmedabad,2,4,0711,RAIPUR,"All regions covered in & between: From Kalupur Station to Sarangpur to Raipur Darwaja, Raipur chakla to B D Arts College till Pankornaka"
Surat,15,57,2201,Rander,"FROM SARDAR BRIDGE VIA ANAND MAHAL ROAD UP TO PALANPUR PATIA, SUBHASH GARDEN CIRCLE TO SAROLI OCTROI NAKA, JAHANGIRPURA TO CITY AREA UP TO RIVER TAPI (INCLUDING RANDER VILLAGE)"
Surat,15,57,2202,Adajan,"LEFT AREA FROM SARDAR BRIDGE VIA ANAND MAHAL ROAD, UP TO PALANPUR PATIA. AND FROM PAL OCTROI NAKA TO PALANPUR VILLAGE."
Surat,15,57,2224,Hajira,"ICCHAPORE, KAVAS, MORA, PAL-BHATHA, HAJIRA"
Surat,15,57,2230,Jahangirabad,"SUBHASH GARDEN CIRCLE TO SAROLI JAKAT NAKA"
Surat,15,57,2231,Olpad,"Olpad taluko"
Surat,15,58,2203,Ghod-dod-road,"MAJURAGATE TO PODAR CIRCLE RIGHT SIDE AREA, FROM GHODDOD ROAD TO PARLE POINT RUNDH OCTROI NAKA. RIGHT SIDE AREA UP TO RIVER TAPI, RIGHT SIDE AREA FROM SARDAR BRIDGE UP TO MAJURA GATE."
Surat,15,58,2207,Nanpura,"FROM CHOWK BAZAR TO FLYOVER BRIDGE, MAJURA GATE CHAR RASTA, SORTHIYAWADI, LEFT SIDE AREA OF SHANKHESHWAR COMPLEX, RUDARPURA MAIN ROAD TO MAKKAI PUL UP TO CHOWK BAZAR."
Surat,15,58,2215,Sagrampura,"SAGRAMPURA, NAVSARIBAZAR, RUSTAMPURA ATHWAGATE TO RING ROAD"
Surat,15,59,2204,Rampura,"AREA FROM I. P. MISSION SCHOOL TO VED DARWAJA, FROM HODI BANGLA TO SAIYADPURA PUMPING STATION UP TO ASHAKTASHRAM HOSPITAL MAIN ROAD, GARDEN TUNKI, RAMPURA, RUGNATHPURA AND RUGNATHPURA ROAD TO LAL DARWAJA CIRCLE."
Surat,15,59,2205,Laldarwaja,"AREA OF LALDARWAJA CIRCLE TO DELHI GATE, RAILWAY STATION TO DELHI GATE VIA RAJMARG AREA AND FROM RAILWAY STATION TO SUMUL DAIRY UP TO FLY OVER BRIDGE."
Surat,15,59,2206,Shahpor,"AREA OF NEHRU BRIDGE TO LEFT SIDE UP TO BHAGAL CHAR RASTA, BHAGAL CHAR RASTA VIA KASKIWAD TO SAIYADPURA PUMPING STATION TO VARIALI BAZAR UP TO I. P. MISSION SCHOOL TO CHOWK BAZAR."
Surat,15,59,2208,Haripura,"RIGHT SIDE AREA FROM BHAGAL CHAR RASTA VIA HARIPURA TO SAIYADPURA PUMPING STATION, AREA FROM RUWALA TEKRA VIA BHAVANIVAD TO RAMPURA ROAD."
Surat,15,59,2209,Mahidharpura,"ALL AREA OF MAHIDHARPURA, FROM JADAKHADI CHAR RASTA TO GUNDI SHERI NAKA, KUMBHAR SHERI, MOTISHERI, VANIA SHERI, AREA OF MAHIDHAR PURA TO AMISHA HOTEL INCLUDING MAIN ROAD OPP. TOWER."
Surat,15,60,2210,Zapabazar,"FROM LAMBE HUNUMAN RAILWAY BRIDGE TO SAHARA DARWAJA TO SURAT COTTON MILL TO MAIN ROAD OF ZAAPA BAZAR YARN MARKET, RIGHT SIDE AREA FROM HAJURI CHAMBER TO TOWER. RIGHT SIDE AREA OF MAIN ROAD FROM TOWER ROAD TO LINEAR BUS STAND."
Surat,15,60,2211,Begumpura,"AREA FROM SAHARA DARWAJA TO SALABATPURA MOMNAWAD, BEGAMPURA, LEFT SIDE OF KAMELA DARWAJA TO ZAMPA BAZAR."
Surat,15,60,2212,Navapura,"AREA FROM KAMELA DARWAJA TO MAAN DARWAJA TOD KM HOSPITAL AND ALL AREA NAVAPURA."
Surat,15,60,2213,Ambaji Road,"AREA OF KHAPATIA CHAKLA VIA AMBAJI ROAD TO WADIFALIYA GATE, BALAJI ROAD, CHAUTA BAZAR, KHAPATIA CHAKLA TO HANUMAN CHAR RASTA."
Surat,16,61,2214,Gopipura,"FROM HANUMAN CHAR RASTA TO KAJI MEDAN., GOPIPURA, INSIDE OF THE MOMNAWAD THREE ROADS, FROM GOPIPURA POLICE CHOWKI TO PANI NI BHIT ADN SONI FALIA AND CHAWLK BAZAR, FROM CHAWLK BAZAR TO BHAGA TALAV MAIN ROAD. RIGHT SIDE OF ROAD STARTS FROM CHAWLK BAZAR TO BHAGA TALAV."
Surat,16,61,2216,Salbatpura,"LEFT SIDE OF RING ROAD STARTING UDHNA DARWAJA TO MAAN DARWAJA, FROM L. B. APTT. MAIN ROAD TO SALABATPURA MOMNAWAD. WHOLE AREA OF SALABATPURA AND AREA FROM UDHNA DARWAJA TOD K M HOSPITAL."
Surat,16,62,2218,Udhana & Udhana Gam,"UDHNA GIDC, LIMBAYAT, DINDOLI, NAVAGAM, BHEDWAD, EAST SIDE OF UDHNA AND EAST SIDE OF SURAT NAVSARI ROAD."
Surat,16,62,2219,Harinagar-1/2/3,"UDHNA VILLAGE, HARINAGAR 1, 2, 3, RANCHOD NAGAR UP TO FIRST STREET OF BHEDWAD, WEST SIDE OF SURAT - NAVSARI ROAD."
Surat,16,63,2220,Pandesara,"PANDESARA, PANDESARA GIDC, VADOD VILLAGE, SURAT-NAVSARI ROAD UP TO UN JAKAT NAKA."
Surat,16,63,2221,Sachin,"SACHIN, SACHIN GIDC, VILLAGE SACHIN, BHESTAN, UNN, YANZ, KHARWASA UP TO THE LIMIT OF TALUKA CHORYASI."
Surat,16,64,2222,Khatodara,"KHATODARA, BAMROLI, UDHNA-MAGDALLA ROAD UP TO BHATAR CHAR RASTA."
Surat,16,64,2223,Bhatar,"BHATAR, CHALTHAN, UMRA, PIPLOD AREA OF CHORYSI TALUKA UP TO DUMAS."
Surat,17,65,2225,Amroli,"AMROLI GAM, CHHAPRABHATHA, MOTA VARACHHA, KOSAD, UTRAN, VARIYAV"
Surat,17,65,2226,Ved,"VED ROAD, DABHOLI, TUNKI, SINGANPOR GAM, SINGANPOR CHAR RASTA"
Surat,17,65,2227,Katargam,"KATARGAM DARWAJA, SINGANPOR ROAD, GOTALAWADI, SUMULDAIRY ROAD, VASTADEVDI ROAD, FULPADA ROAD"
Surat,17,66,2228,Varachha,"A. K. ROAD, VARACHA ROAD FROM HIRABAG CIRCLE TO RIVER TAPTI, L. H. ROAD"
Surat,17,66,2229,Kapodara,"FROM HIRABAG CIRCLE TO SARTHANA JAKAT NAKA, KAPODERA NANA VARACHHA"
Surat,17,67,2237,Mandvi,"MANDVI TALUKA, KARANJ GIDC"
Surat,17,67,2232,Mangrol,"MANGROL TALUKA, MOTA BORASARA, PIPODARA, PALOD, KIM, KOSAMBA"
Surat,17,67,2238,Kamrej,"KAMREJ TALUKA, SARATHANA JAKATNAKA ONWARDS, NAVAGAM"
Surat,17,67,2233,Umarpada,"Umarpada taluko"
Surat,17,68,2217,Umarwada,"UMARPADA, ANJANA, PUNA KUMBHARIA ROAD, MAGOB, OPP-KINNARY CINEMA AREA (RING ROAD), PUNA GAM, DUMBHAL"
Surat,17,68,2239,Palsana,"PALSANA TALUKA, KADODARA, TATITHAIYA, VARELI"
Surat,17,68,2240,Bardoli city,"Bardoli city"
Surat,17,68,2241,Bardoli Taluko,"Bardoli Taluko"
Surat,17,69,2242,Vyara Town,"Vyara Town"
Surat,17,69,2243,Vyara Taluko,"Vyara Taluko"
Surat,17,69,2244,Valod,"Valod"
Surat,17,69,2236,Songadh,"Songadh town & taluko"
Surat,17,69,2234,Nizar,"Nizar city & taluko"
Surat,17,69,2235,Uchhal,"Uchhal city & taluko"
Surat,17,69,2245,Mahuva,"Mahuva"
"""
    df = pd.read_csv(io.StringIO(csv_data))
    return df

df = load_data()

# 3. Search UI
st.markdown("---")
st.subheader("🔍 Search Database")

# A little UI tweak to make the search bar look better
search_query = st.text_input("Area Code, Naam, Ghatak, ya locality ka naam type karein (e.g., '2228', 'Varachha', '0704'):", "")

# 4. Table Configuration (Isse Locality column bada aur clear dikhega)
column_configuration = {
    "Locality Description": st.column_config.TextColumn(
        "Locality Description",
        width="large", # Gives maximum width to the text description
    ),
    "Area Code": st.column_config.NumberColumn(
        "Area Code",
        format="%d" # Removes the comma (e.g. 2,201 will become 2201)
    )
}

# 5. Search & Filter Logic
if search_query:
    mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(search_query.lower()).any(), axis=1)
    filtered_df = df[mask]
    
    # Display Results
    if not filtered_df.empty:
        st.success(f"✅ {len(filtered_df)} Result(s) Found!")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True, column_config=column_configuration)
    else:
        st.warning("⚠️ Koi data nahi mila. Spelling check karein ya doosra keyword try karein.")
else:
    st.info("👆 Upar box mein details enter karein. Niche pura database preview diya gaya hai:")
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=column_configuration)

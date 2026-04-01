import streamlit as st
import io
import zipfile
from PIL import Image
from pypdf import PdfReader, PdfWriter

st.title("🗜️ GST Document Compressor")
st.write("GST Portal ke liye apne documents (Photos < 100KB, PDFs < 1MB) yahan upload karein. Yeh tool unhe automatically compress karke ek ZIP file mein de dega.")

# ==========================================
# 🛠️ COMPRESSION FUNCTIONS
# ==========================================
def compress_image(uploaded_file, max_size_kb=100):
    """Images ko 100KB ke andar compress karne ka logic"""
    img = Image.open(uploaded_file)
    
    # Agar image PNG (RGBA) hai toh usko JPEG (RGB) me convert karna padega
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    quality = 95
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=quality)
    
    # Jab tak size 100KB se zyada hai, quality kam karte raho
    while output.tell() > max_size_kb * 1024 and quality > 10:
        quality -= 5
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality)
        
    return output.getvalue(), "jpg"

def compress_pdf(uploaded_file):
    """PDFs ka size chhota karne ka basic logic"""
    reader = PdfReader(uploaded_file)
    writer = PdfWriter()
    
    for page in reader.pages:
        writer.add_page(page)
        
    # PDF ke andar ke content ko compress karna
    for page in writer.pages:
        page.compress_content_streams() 
        
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), "pdf"

# ==========================================
# 🚀 UI WORKFLOW
# ==========================================
uploaded_files = st.file_uploader("Upload Photos (JPG/PNG) & Documents (PDF)", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

if uploaded_files:
    if st.button("Compress All Documents", type="primary"):
        with st.spinner("Documents compress ho rahe hain... Kripya wait karein."):
            
            # Ek memory me ZIP file banane ke liye
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file in uploaded_files:
                    try:
                        file_ext = file.name.split('.')[-1].lower()
                        original_size = file.size / 1024 # KB mein
                        
                        # IMAGE COMPRESSION
                        if file_ext in ['jpg', 'jpeg', 'png']:
                            compressed_data, new_ext = compress_image(file)
                            new_name = file.name.rsplit('.', 1)[0] + "_compressed." + new_ext
                            zip_file.writestr(new_name, compressed_data)
                            
                            new_size = len(compressed_data) / 1024
                            st.success(f"🖼️ {file.name}: {original_size:.1f} KB ➡️ {new_size:.1f} KB")
                            
                        # PDF COMPRESSION
                        elif file_ext == 'pdf':
                            compressed_data, new_ext = compress_pdf(file)
                            new_name = file.name.rsplit('.', 1)[0] + "_compressed.pdf"
                            zip_file.writestr(new_name, compressed_data)
                            
                            new_size = len(compressed_data) / 1024
                            st.success(f"📄 {file.name}: {original_size:.1f} KB ➡️ {new_size:.1f} KB")
                            
                    except Exception as e:
                        st.error(f"❌ Error compressing {file.name}: {str(e)}")

            # ZIP file ko download ke liye ready karna
            zip_buffer.seek(0)
            
            st.write("---")
            st.download_button(
                label="📥 Download All Compressed Docs (ZIP)",
                data=zip_buffer,
                file_name="GST_Compressed_Docs.zip",
                mime="application/zip",
                type="primary"
            )
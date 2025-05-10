import streamlit as st
import json
from pathlib import Path
from document import PDF_Document
from summarizer import Summarizer
import os.path as osp
import fitz  # PyMuPDF for PDF preview
import time
import shutil

# Set up the Streamlit app
st.set_page_config(
    page_title="PDF Document Analyzer",
    page_icon="📕",
    layout="wide"
)

# Initialize session state
if 'processed_doc' not in st.session_state:
    st.session_state.processed_doc = None
if 'summary' not in st.session_state:
    st.session_state.summary = None
if 'preview_image' not in st.session_state:
    st.session_state.preview_image = None
if 'doc_stats' not in st.session_state:
    st.session_state.doc_stats = None

# App title and description
st.title("📕 LLM Book Summarizer")
st.markdown("Upload a PDF document to view its metadata and summary.")

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

summarizer = Summarizer(config)
summary_prompt_path = osp.join(config["PROMPT_DIR"], "summary_chain_of_thought.txt")

# File uploader
uploaded_file = st.file_uploader("Upload PDF", type="pdf")

if uploaded_file is not None and st.session_state.processed_doc is None:
    # Show upload progress
    # progress_bar = st.progress(0)
    status_text = st.empty()
    
    # # Simulate upload progress
    # for i in range(100):
    #     progress_bar.progress(i + 1)
    #     status_text.text(f"Uploading... {i + 1}%")
    #     time.sleep(0.01)
    
    # Save file temporarily
    temp_path = Path("temp") / uploaded_file.name
    temp_path.parent.mkdir(exist_ok=True)
    
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    status_text.text("Upload complete!")
    # progress_bar.empty()
    
    try:
        # Create PDF_Document instance
        doc = PDF_Document(file_path=str(temp_path), config=config)
        
        # Store in session state
        st.session_state.processed_doc = doc
        
        # Process PDF preview
        pdf_document = fitz.open(temp_path)
        first_page = pdf_document[0]
        pix = first_page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        
        # Store preview and stats in session state
        st.session_state.preview_image = img_data
        st.session_state.doc_stats = {
            'total_pages': len(pdf_document),
            'file_size': f"{uploaded_file.size / 1024:.2f} KB"
        }
        
        pdf_document.close()
        
    except Exception as e:
        st.error(f"Error processing document: {str(e)}")

    finally:
        # Clean up temporary files
        if temp_path.exists():
            temp_path.unlink()
        if Path("temp").exists():
            shutil.rmtree("temp")

# Display the processed document information
if st.session_state.processed_doc is not None:
    # Create two columns for layout (1:2 ratio for better summary display)
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Document preview
        st.subheader("Document Preview")
        st.image(st.session_state.preview_image, caption="First Page Preview")

        # Document metadata
        st.subheader("Document Information")
        st.write(f"**Name:** {st.session_state.processed_doc.name}")
        st.write(f"**Author:** {st.session_state.processed_doc.author}")
        st.write(f"**File Size:** {st.session_state.doc_stats['file_size']}")
        st.write(f"**Total Pages:** {st.session_state.doc_stats['total_pages']}")
        
        # Summarize button
        if st.button("Generate Summary"):
            with st.spinner("Generating summary..."):
                summary = summarizer._get_doc_summary(
                    document=st.session_state.processed_doc,
                    summary_prompt_path=summary_prompt_path,
                    save=False
                )
                st.session_state.summary = summary
    
    with col2:
        # Summary section
        if st.session_state.summary:
            st.subheader("Document Summary")
            # Create a container with fixed height and scrolling
            with st.container():
                # Convert the first line to a proper header if it starts with #
                summary_lines = st.session_state.summary.split('\n')
                if summary_lines and summary_lines[0].startswith('#'):
                    summary_lines[0] = f"<h1>{summary_lines[0].lstrip('#').strip()}</h1>"
                
                cleaned_summary = '\n'.join(summary_lines)
                
                st.markdown(
                    f"""
                    <div style="height: 600px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">
                        {cleaned_summary}
                    """,
                    unsafe_allow_html=True
                )
            
            st.write("---")
            # Download button
            st.download_button(
                label="Download Summary",
                data=st.session_state.summary,
                file_name=f"{st.session_state.processed_doc.name}_summary.md",
                mime="text/markdown"
            )
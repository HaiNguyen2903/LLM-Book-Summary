import streamlit as st
import json
from pathlib import Path
from document import PDF_Document
from summarizer import Summarizer
import os.path as osp
import fitz  # PyMuPDF for PDF preview
import shutil
from streamlit import session_state as ss

def init_session_state():
    # Initialize session state
    if 'uploaded_file' not in ss:
        ss.uploaded_file = None
    if 'summary' not in ss:
        ss.summary = None
    if 'preview_image' not in ss:
        ss.preview_image = None
    if 'doc_stats' not in ss:
        ss.doc_stats = None
    if 'summary_style' not in ss:
        ss.summary_style = list(SUMMARY_STYLES.keys())[0]
    if 'temp_path' not in ss:
        ss.temp_path = None

def update_summary_options():
    with st.sidebar:
        st.header("Summary Style")
        style_options = list(SUMMARY_STYLES.keys())
        selected_style = st.selectbox(
            "Choose summary style:",
            style_options,
            index=style_options.index(ss.summary_style) if ss.summary_style in style_options else 0,
            help="\n\n".join([f"**{k}**: {v['description']}" for k, v in SUMMARY_STYLES.items()])
        )
        ss.summary_style = selected_style
        st.markdown(f"**Description:** {SUMMARY_STYLES[selected_style]['description']}")

def update_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        # Save file temporarily
        temp_path = Path("temp") / uploaded_file.name
        temp_path.parent.mkdir(exist_ok=True)

        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Create PDF_Document instance
        doc = PDF_Document(file_path=str(temp_path), config=config)
        
        # Store in session state
        ss.uploaded_file = doc
        ss.temp_path = temp_path
    else:
        # reset session state
        ss.uploaded_file = None
        ss.temp_path = None
        ss.preview_image = None
        ss.doc_stats = None
        ss.summary = None

def update_book_info():
    with st.sidebar:
        if ss.uploaded_file is not None:
            # display preview
            st.header("Document Preview")

            pdf_doc = fitz.open(ss.temp_path)

            first_page = pdf_doc[0]
            pix = first_page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            ss.preview_image = img_data

            st.sidebar.image(ss.preview_image, caption="First Page Preview")

            # display book info
            ss.doc_stats = {
                'total_pages': len(pdf_doc),
                'file_size': f"{uploaded_file.size / 1024:.2f} KB"
            }

            st.write(f"**Name:** {ss.uploaded_file.name}")
            st.write(f"**Author:** {ss.uploaded_file.author}")
            st.write(f"**File Size:** {ss.doc_stats['file_size']}")
            st.write(f"**Total Pages:** {ss.doc_stats['total_pages']}")


def update_summary():
    if ss.uploaded_file is not None:
        if st.button("Generate Summary"):
            # generate summary
            with st.spinner("Generating summary..."):
                summarizer = Summarizer(config)
                summary = summarizer._get_doc_summary(
                    document=ss.uploaded_file,
                    summary_prompt_path=osp.join(
                        config["PROMPT_DIR"],
                        SUMMARY_STYLES[ss.summary_style]["prompt_file"]
                    ),
                    save=False
                )
                ss.summary = summarizer.format_doc_summary(summary)

            # display summary
            st.header("Document Summary")
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

            st.write("   ") 

            st.download_button(
                label="Download Summary",
                data=st.session_state.summary,
                file_name=f"{st.session_state.uploaded_file.name}_summary.md",
                mime="text/markdown"
            )

if __name__ == '__main__':

    # --- Summary Style Definitions ---
    SUMMARY_STYLES = {
        "Analytic Summary": {
            "prompt_file": "summary_cot_analytic_style.txt",
            "description": "Concise, analytical, and natural-sounding summary in the book's intellectual voice."
        },
        "Bullet-Point Summary": {
            "prompt_file": "summary_cot_bullet_points_style.txt",
            "description": "Clear, scannable bullet-point summary for quick reference."
        },
        "Narrative Summary": {
            "prompt_file": "summary_cot_narrative_style.txt",
            "description": "Narrative summary with a focus on the story and characters."
        }
    }

    with open('config.json', 'r') as f:
        config = json.load(f)

    # Set up the Streamlit app
    st.set_page_config(
        page_title="Book Summarizer",
        page_icon="📕",
        layout="wide"
    )

    # App title and description
    st.title("📕 LLM Book Summarizer")
    st.markdown("Upload a PDF document to view its metadata and summary.")

    # # File uploader
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")

    # initialize session state
    init_session_state()
    # update summary options
    update_summary_options()
    # update uploaded file
    update_uploaded_file(uploaded_file)
    # update book info
    update_book_info()
    # update summary    
    update_summary()

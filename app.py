import streamlit as st
import json
from pathlib import Path
from document import PDF_Document
from summarizer import Summarizer
import os.path as osp
import fitz  # PyMuPDF for PDF preview
import shutil
from streamlit import session_state as ss
import sqlite3
from datetime import datetime

def init_db():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect('books.db')

    ss.db_file = 'books.db'

    c = conn.cursor()
    
    # Create books table
    c.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT,
            book_name TEXT,
            total_pages INTEGER,
            created_at TIMESTAMP,
            UNIQUE(book_name, author)
        )
    ''')
    
    # Create chunks table (1-n relationship with books)
    c.execute('''
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            chunk_text TEXT,
            chunk_order INTEGER,
            FOREIGN KEY (book_id) REFERENCES books (id)
        )
    ''')
    
    # Create summaries table
    c.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            summary_style TEXT,
            created_at TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books (id)
        )
    ''')
    
    # Create chunk_summaries table (1-n relationship with summaries)
    c.execute('''
        CREATE TABLE IF NOT EXISTS chunk_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_id INTEGER,
            chunk_order INTEGER,
            chunk_summary TEXT,
            FOREIGN KEY (summary_id) REFERENCES summaries (id),
            FOREIGN KEY (chunk_order) REFERENCES chunks (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def store_book_info(doc, summary_style, summary_data):
    """Store book information and summaries in the database"""
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    
    try:
        # Insert book information
        c.execute('''
            INSERT INTO books (author, book_name, total_pages, created_at)
            VALUES (?, ?, ?, ?)
        ''', (
            doc.author,
            doc.name,
            len(doc.pages),
            datetime.now()
        ))
        
        book_id = c.lastrowid
        
        # Insert chunks
        chunk_ids = []
        for i, chunk_text in enumerate(doc.chunks):
            c.execute('''
                INSERT INTO chunks (book_id, chunk_text, chunk_index)
                VALUES (?, ?, ?)
            ''', (book_id, chunk_text, i))
            chunk_ids.append(c.lastrowid)
        
        # Insert summary
        c.execute('''
            INSERT INTO summaries (book_id, summary_style, created_at)
            VALUES (?, ?, ?)
        ''', (book_id, summary_style, datetime.now()))
        
        summary_id = c.lastrowid
        
        # Insert chunk summaries
        for chunk_id, chunk_summary in zip(chunk_ids, summary_data['chunks']):
            c.execute('''
                INSERT INTO chunk_summaries (summary_id, chunk_id, chunk_summary)
                VALUES (?, ?, ?)
            ''', (summary_id, chunk_id, chunk_summary))
        
        conn.commit()
        return True
        
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()

def init_session_state():
    if 'uploaded_file' not in ss:
        ss.uploaded_file = None
    if 'summary' not in ss:
        ss.summary = None
    if 'summary_json' not in ss:
        ss.summary_json = None
    if 'preview_image' not in ss:
        ss.preview_image = None
    if 'doc_stats' not in ss:
        ss.doc_stats = None
    if 'summary_style' not in ss:
        ss.summary_style = list(SUMMARY_STYLES.keys())[0]
    if 'temp_path' not in ss:
        ss.temp_path = None
    if 'db_file' not in ss:
        ss.db_file = 'books.db'
        init_db()
    if 'book_info_updated' not in ss:
        ss.book_info_updated = False
    if 'book_id' not in ss:
        ss.book_id = None

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
        ss.summary_json = None
        ss.book_info_updated = False
        ss.summary_updated = False
        ss.book_id = None

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

def update_book_info_to_db():
    # if book info updated is false and uploaded file is not none
    if ss.book_info_updated is False and ss.uploaded_file is not None:
        """Store book information and summaries in the database"""
        conn = sqlite3.connect('books.db')
        c = conn.cursor()
        
        # update book info updated
        ss.book_info_updated = True

        book_id = None

        try:
            # Insert book information
            c.execute('''
                INSERT INTO books (author, book_name, total_pages, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                ss.uploaded_file.author,
                ss.uploaded_file.name,
                ss.doc_stats['total_pages'],
                datetime.now()
            ))

            # update book_id
            ss.book_id = c.lastrowid

            conn.commit()
        
        # if book already exists
        except sqlite3.IntegrityError:
            ss.book_id = c.execute('''
                SELECT id FROM books WHERE book_name = ? AND author = ?
            ''', (ss.uploaded_file.name, ss.uploaded_file.author)).fetchone()[0]
            conn.rollback()
        finally:
            chunks = ss.uploaded_file.contents
            for chunk_id in chunks:
                # update book chunks
                c.execute('''
                    INSERT INTO chunks (book_id, chunk_order, chunk_text)
                    VALUES (?, ?, ?)
                ''', (
                    ss.book_id,
                    int(chunk_id),
                    chunks[chunk_id]['text']
                ))
                conn.commit()
            conn.close()
            return


def update_summary():
    if ss.uploaded_file is not None:
        if st.button("Generate Summary"):
            # generate summary
            with st.spinner("Generating summary..."):
                summarizer = Summarizer(config)
                summary_data = summarizer._get_doc_summary(
                    document=ss.uploaded_file,
                    summary_prompt_path=osp.join(
                        config["PROMPT_DIR"],
                        SUMMARY_STYLES[ss.summary_style]["prompt_file"]
                    ),
                    save=False
                )
                ss.summary_json = summary_data
                ss.summary = summarizer.format_doc_summary(summary_data)

                update_summary_to_db()
                
                # # Store book information in database
                # if store_book_info(ss.uploaded_file, ss.summary_style, summary_data):
                #     st.success("Book information stored successfully!")
                # else:
                #     st.warning("Book already exists in database!")

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

def update_summary_to_db():
    # if ss.summary_updated is False and ss.summary_json is not None:
    # Insert summary
    conn = sqlite3.connect(ss.db_file)
    c = conn.cursor()
    
    # insert summary event
    c.execute('''
        INSERT INTO summaries (book_id, summary_style, created_at)
        VALUES (?, ?, ?)
    ''', (ss.book_id, ss.summary_style, datetime.now()))

    summary_id = c.lastrowid

    # insert chunk summaries
    for chunk_id in ss.summary_json:
        c.execute('''
            INSERT INTO chunk_summaries (summary_id, chunk_order, chunk_summary)
            VALUES (?, ?, ?)
        ''', (summary_id, chunk_id, ss.summary_json[chunk_id]['summary']))
    
    conn.commit()
    conn.close()

    ss.summary_updated = True
    return


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
    # update book info to database
    update_book_info_to_db()
    st.write(ss.book_id)
    # update summary 
    update_summary()   
    # update summary to database
    # update_summary_to_db()

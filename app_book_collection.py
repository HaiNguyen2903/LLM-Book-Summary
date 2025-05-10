import streamlit as st
import json
import os
import os.path as osp
from pathlib import Path
from document import PDF_Document
import glob

# Initialize session state for books data if not exists
if 'books' not in st.session_state:
    data_dir = 'outputs'

    categories = os.listdir(data_dir)
    books_dict = {}
    
    for category in categories:
        books_dict[category] = []
        book_dirs = os.listdir(osp.join(data_dir, category))
        for book_dir in book_dirs:
            book_path = osp.join(data_dir, category, book_dir)
            book_metadata = json.load(open(osp.join(book_path, 'metadata.json')))
            book_summary = open(osp.join(book_path, 'summary.md')).read()
            books_dict[category].append({
                'title': book_metadata['title'],
                'author': book_metadata['author'],
                'category': book_metadata['category'],
                'summary': book_summary
            })

    # save books_dict to session state
    st.session_state.books = books_dict

if __name__ == "__main__":
    # Set up the Streamlit app
    st.set_page_config(
        page_title="Book Library",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    with open('config.json', 'r') as f:
        config = json.load(f)

    # App title and description
    st.title("📚 Book Library")
    st.markdown("Welcome to our digital book library! Browse through different categories.")

    # Sidebar for category selection and navigation
    st.sidebar.title("Navigation")
    selected_category = st.sidebar.selectbox(
        "Select a category",
        list(st.session_state.books.keys())
    )
    
    # Add navigation button to add book page
    if st.sidebar.button("Add New Book"):
        st.switch_page("pages/app.py")

    # Main content area
    st.subheader(f"Books in {selected_category}")
    for book in st.session_state.books[selected_category]:
        with st.expander(f"{book['title']} by {book['author']}"):
            st.write(book['summary'])
            
            # Add download button for summary
            summary_text = f"Title: {book['title']}\nAuthor: {book['author']}\n\nSummary:\n{book['summary']}"
            st.download_button(
                label="Download Summary",
                data=summary_text,
                file_name=f"{book['title']}_summary.txt",
                mime="text/plain"
            )
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import fitz
import os.path as osp
import json
from utils import Cleaner
import glob
from utils import mkdir_if_not_exists

class PDF_Document:
    def __init__(self, file_path: str, config: dict, 
                 save_structure=False, save_metadata=False) -> None:
        self.file_path = file_path
        self.name = self._get_doc_name()
        self.author = self._get_author()
        self.category = self._get_category()
        self.config = config
        # save directory
        self.save_dir = osp.join(self.config['OUTPUT_DIR'], self.category, self.name)
        mkdir_if_not_exists(self.save_dir)
        
        self.save_structure = save_structure
        self.contents = self._extract_toc_hierarchical()
        
        if save_metadata:
            meta_data = {
                'title': self.name,
                'author': self.author,
                'category': self.category,
            }

            with open(osp.join(self.save_dir, 'metadata.json'), "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

        return
    
    def _extract_full_text(self) -> list:
        """
        Extract text from PDF between start_page and end_page (inclusive).
        Page numbers are 0-based.
        """
        doc = fitz.open(self.file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        cleaner = Cleaner()

        # clean text
        text = cleaner.clean_pdf_text(text)

        content = {
            "level": 1,
            "title": self.name,
            "start_page": None,
            "end_page": None,  # to be filled later
            "children": [],
            "text": text
        }

        if self.save_structure:
            mkdir_if_not_exists('book_structures')
            with open(osp.join('book_structures', f'{self.name}.json'), "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

        return [content]
    
    def _get_doc_name(self) -> str:
        assert self.file_path[-3:] == 'pdf', f'File {self.file_path} is not a PDF'
        
        doc_name = osp.basename(self.file_path)[:-4]

        # replace_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', 
        #                  ',', '.', '!', '(', ')', ";"]

        # for char in replace_chars:
        #     doc_name = doc_name.replace(char, '_')

        return doc_name

    def _get_author(self) -> str:
        """
        Extract author information from PDF metadata.
        Returns empty string if author information is not found.
        """
        try:
            doc = fitz.open(self.file_path)
            metadata = doc.metadata
            doc.close()
            
            if metadata and metadata.get('author'):
                return metadata['author']
            return ""
        except Exception as e:
            print(f"Error extracting author: {str(e)}")
            return ""
        
    def _get_category(self) -> str:
        return osp.basename(osp.dirname(self.file_path))
    
    def _is_ignore_sections(self, title: str) -> bool:
        ignore_sections = ['preface', 'acknowledgments', 'author', 'title', 'contents',
                           'copyright', 'epigraph', 'appendix', 'notes', 'index', 'welcome',
                           'dedication']
        
        for keyword in ignore_sections:
            if keyword in title.lower():
                return True
            
        return False
    
    def _extract_toc_hierarchical(self) -> list:
        doc = fitz.open(self.file_path)
        toc = doc.get_toc(simple=False)  # returns [level, title, page number, ...]
        total_pages = len(doc)

        cleaner = Cleaner()

        if len(toc) == 0:
            return self._extract_full_text()

        # Step 1: Build a flat list with placeholders for children and end_page
        toc_entries = []

        # check max level
        max_level = 0
        
        for idx, entry in enumerate(toc):
            level, title, page = entry[:3]

            # check if the section is a ignore section
            if self._is_ignore_sections(title):
                continue

            toc_entries.append({
                "level": level,
                "title": title,
                "start_page": page,
                "end_page": None,  # to be filled later
                "children": []
            })

        # Step 2: Compute end_page for each section
        for i, current in enumerate(toc_entries):
            current_level = current["level"]

            # update max level
            max_level = max(max_level, current_level)   

            current_start = current["start_page"]

            # Find the next section at the same or higher level
            for j in range(i + 1, len(toc_entries)):
                if toc_entries[j]["level"] <= current_level:
                    current["end_page"] = toc_entries[j]["start_page"] - 1
                    break
            else:
                current["end_page"] = total_pages  # last section

        # Step 3: Extract text per section
        for entry in toc_entries:
            start = entry["start_page"] - 1  # PyMuPDF is 0-based
            end = entry["end_page"]
            section_text = ""
            for p in range(start, end):
                section_text += doc.load_page(p).get_text()
            
            entry["text"] = cleaner.clean_pdf_text(section_text)

        # Step 4: Build hierarchical structure using a stack
        root = []
        stack = []

        for entry in toc_entries:
            while stack and stack[-1]["level"] >= entry["level"]:
                stack.pop()

            if stack:
                stack[-1]["children"].append(entry)
            else:
                root.append(entry)

            stack.append(entry)

        # Step 5: Remove text from entries that have children
        def remove_parent_text(entries):
            for entry in entries:
                if entry["children"]:
                    if "text" in entry:
                        del entry["text"]
                    remove_parent_text(entry["children"])

        remove_parent_text(root)

        if self.save_structure:
            with open(osp.join(self.save_dir, 'structure.json'), "w", encoding="utf-8") as f:
                json.dump(root, f, indent=2, ensure_ascii=False)

        return root

class EPUB_Document:
    def __init__(self, file_path):
        self.file_path = file_path
        return

    def extract_toc_hierarchical(self):
        book = epub.read_epub(self.file_path)
        toc = book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        toc_entries = []

        print(toc)

        for item in toc:
            soup = BeautifulSoup(item.get_body_content_str(), 'html.parser')
            title = soup.find('title').text if soup.find('title') else "Untitled"
            toc_entries.append({
                "title": title,
                "content": soup.get_text(separator=' ', strip=True)
            })

        with open("toc_with_text_2.json", "w", encoding="utf-8") as f:
            json.dump(toc_entries, f, indent=2, ensure_ascii=False)

        return toc_entries
    
    def extract_toc_from_epub(self):
        book = epub.read_epub(self.file_path)
        toc = book.get_toc()  # This returns a nested list or tuple structure

        def parse_toc(toc_items):
            result = []
            for item in toc_items:
                if isinstance(item, epub.Link):
                    result.append({
                        "title": item.title,
                        "start": item.href,
                        "end": None,
                        "subsections": []
                    })
                elif isinstance(item, tuple):
                    link, subitems = item
                    result.append({
                        "title": link.title,
                        "start": link.href,
                        "end": None,
                        "subsections": parse_toc(subitems)
                    })
            return result

        return parse_toc(toc)
    

def main():
    # path = 'datasets/The Art of Strategy.pdf'
    # path = 'datasets/tales-from-coffee.pdf'
    # path = 'datasets/Rich Dad Poor Dad.pdf'
    path = 'datasets/books/Self-Development/Atomic Habits.pdf'

    with open('config.json', 'r') as f:
        config = json.load(f)

    document = PDF_Document(path, config, save_structure=True, save_metadata=True)

if __name__ == "__main__":
    main()
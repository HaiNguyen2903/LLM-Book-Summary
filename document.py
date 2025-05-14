import ebooklib
from ebooklib import epub
import fitz
import os.path as osp
import json
from utils import Cleaner
import glob
from utils import mkdir_if_not_exists
from IPython import embed

class PDF_Document:
    def __init__(self, file_path: str, config: dict, 
                 save_structure=False, save_metadata=False) -> None:
        self.file_path = file_path
        self.name = self._get_doc_name()
        self.author = self._get_author()
        self.category = self._get_category()
        self.config = config
        self.max_chunk_length = config['MAX_CHUNK_LENGTH']
        # save directory
        self.save_dir = osp.join(self.config['OUTPUT_DIR'], self.category, self.name)
        mkdir_if_not_exists(self.save_dir)
        
        self.save_structure = save_structure
        # self.contents = self._extract_toc_hierarchical()
        self.contents = self._extract_content_by_chunk()
        
        if save_metadata:
            meta_data = {
                'title': self.name,
                'author': self.author,
                'category': self.category,
            }

            with open(osp.join(self.save_dir, 'metadata.json'), "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)

        return
    
    def _extract_full_text(self) -> dict:
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
            "0": {
                "level": 1,
                "title": self.name,
                "text": text
            }
        }

        if self.save_structure:
            mkdir_if_not_exists('book_structures')
            with open(osp.join('book_structures', f'{self.name}.json'), "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2, ensure_ascii=False)

        return content
    
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
    
    def _extract_content_by_chunk(self) -> dict:
        doc = fitz.open(self.file_path)
        toc = doc.get_toc(simple=False)  # returns [level, title, page number, ...]
        total_page = len(doc)
        cleaner = Cleaner()

        chunks = {}
        chunk_id = 0

        if len(toc) == 0:
            return self._extract_full_text()

        for i in range(len(toc)):
            entry = toc[i]
            current_level, current_title, current_start_page = entry[:3]
            current_end_page = None

            if self._is_ignore_sections(current_title):
                continue

            try:
                # if there are sub sections
                if toc[i + 1][0] > current_level:
                    text = ""
                # if there are no sub sections, then we need to extract the text for this section
                else:
                    current_end_page = toc[i + 1][2] - 1
                    text = ""
                    for p in range(current_start_page-1, current_end_page):
                        text += doc.load_page(p).get_text()
                    
                    text = cleaner.clean_pdf_text(text)

                chunks[chunk_id] = {
                    "level": current_level,
                    "title": current_title,
                    "text": text
                }
                chunk_id += 1
            except:
                # last section
                current_end_page = total_page
                text = ""
                for p in range(current_start_page-1, current_end_page):
                    text += doc.load_page(p).get_text()
                
                text = cleaner.clean_pdf_text(text)

                chunks[chunk_id] = {
                    "level": current_level,
                    "title": current_title,
                    "text": text
                }
                chunk_id += 1

        if self.save_structure:
            with open(osp.join(self.save_dir, 'structure.json'), "w", encoding="utf-8") as f:
                json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        return chunks
                

    def _extract_toc_hierarchical(self) -> list:
        import math

        doc = fitz.open(self.file_path)
        toc = doc.get_toc(simple=False)  # returns [level, title, page number, ...]
        total_pages = len(doc)

        cleaner = Cleaner()

        if len(toc) == 0:
            return self._extract_full_text()

        # Predefined threshold for text length (number of characters)
        TEXT_LENGTH_THRESHOLD = 2000

        # Step 1: Build a flat list with placeholders for end_page
        toc_entries = []
        for idx, entry in enumerate(toc):
            level, title, page = entry[:3]

            print(level, title)

            # check if the section is a ignore section
            if self._is_ignore_sections(title):
                continue

            toc_entries.append({
                "idx": idx,
                "level": level,
                "title": title,
                "start_page": page,
                "end_page": None,  # to be filled later
            })

        # Step 2: Compute end_page for each section
        for i, current in enumerate(toc_entries):
            current_level = current["level"]
            current_start = current["start_page"]

            # Find the next section at the same or higher level
            for j in range(i + 1, len(toc_entries)):
                if toc_entries[j]["level"] <= current_level:
                    current["end_page"] = toc_entries[j]["start_page"] - 1
                    break
            else:
                current["end_page"] = total_pages  # last section

        # Step 3: Build parent-child relationships (store children indices)
        for i, entry in enumerate(toc_entries):
            entry["children"] = []

        stack = []
        for i, entry in enumerate(toc_entries):
            while stack and toc_entries[stack[-1]]["level"] >= entry["level"]:
                stack.pop()
            if stack:
                toc_entries[stack[-1]]["children"].append(i)
            stack.append(i)

        # Step 4: Recursive flattening with correct order
        output = []
        chunk_id = 0

        def process_section(idx):
            nonlocal chunk_id
            entry = toc_entries[idx]
            has_children = len(entry["children"]) > 0

            item = {
                "chunk_id": chunk_id,
                "level": entry["level"],
                "title": entry["title"],
                "start_page": entry["start_page"],
                "end_page": entry["end_page"],
            }

            if has_children:
                item["text"] = ""
                output.append(item)
                chunk_id += 1
                # Process children in order
                for child_idx in entry["children"]:
                    process_section(child_idx)
            else:
                # Extract text for this section
                start = entry["start_page"] - 1  # PyMuPDF is 0-based
                end = entry["end_page"]
                section_text = ""
                for p in range(start, end):
                    section_text += doc.load_page(p).get_text()
                section_text = cleaner.clean_pdf_text(section_text)

                # If text is longer than threshold, split into smaller items
                if len(section_text) > TEXT_LENGTH_THRESHOLD:
                    # Split by paragraphs (double newlines or single newlines)
                    paragraphs = [p for p in section_text.split('\n\n') if p.strip()]
                    # If splitting by double newline yields too few, split by single newline
                    if len(paragraphs) <= 1:
                        paragraphs = [p for p in section_text.split('\n') if p.strip()]

                    # Now group paragraphs into chunks under threshold
                    current_chunk = ""
                    for para in paragraphs:
                        if len(current_chunk) + len(para) + 2 <= TEXT_LENGTH_THRESHOLD:
                            if current_chunk:
                                current_chunk += "\n\n" + para
                            else:
                                current_chunk = para
                        else:
                            # Save current chunk
                            output.append({
                                "chunk_id": chunk_id,
                                "level": entry["level"],
                                "title": entry["title"],
                                "start_page": entry["start_page"],
                                "end_page": entry["end_page"],
                                "text": current_chunk.strip()
                            })
                            chunk_id += 1
                            current_chunk = para
                    # Add the last chunk
                    if current_chunk.strip():
                        output.append({
                            "chunk_id": chunk_id,
                            "level": entry["level"],
                            "title": entry["title"],
                            "start_page": entry["start_page"],
                            "end_page": entry["end_page"],
                            "text": current_chunk.strip()
                        })
                        chunk_id += 1
                else:
                    item["text"] = section_text
                    output.append(item)
                    chunk_id += 1

        # Find all top-level sections (no parent)
        parent_indices = set()
        for entry in toc_entries:
            parent_indices.update(entry["children"])
        top_level_indices = [i for i in range(len(toc_entries)) if i not in parent_indices]

        for idx in top_level_indices:
            process_section(idx)

        if self.save_structure:
            with open(osp.join(self.save_dir, 'structure.json'), "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

        return output

def main():
    path = 'datasets/books/Self-Development/Atomic Habits.pdf'

    with open('config.json', 'r') as f:
        config = json.load(f)

    document = PDF_Document(path, config, save_structure=True, save_metadata=False)

if __name__ == "__main__":
    main()
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
import os
import re
from collections import Counter

class Cleaner:
    def __init__(self):
        pass
    
    # Remove common page number patterns
    def remove_page_numbers(self, text):
        text = re.sub(r'\n?Page\s*\d+(\s*of\s*\d+)?\n?', '', text, flags=re.IGNORECASE)
        # text = re.sub(r'\n?\d+\n?', '', text)  # standalone numbers (use with caution)
        return text
    
    def remove_tables(self, text):
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            if len(re.findall(r'\d', line)) > 5 and re.search(r'\s{2,}', line):
                continue  # likely a table row
            if re.search(r'\|', line):  # vertical bars are typical of table borders
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)
    
    def remove_image_captions(self, text):
        return re.sub(r'(Figure|Image)\s*\d+.*', '', text, flags=re.IGNORECASE)
    
    def remove_repeated_lines(self, text):
        lines = text.split('\n')
        freq = Counter(lines)
        common_lines = {line for line, count in freq.items() if count > 3}  # appears in many pages
        cleaned_lines = [line for line in lines if line.strip() not in common_lines]
        return '\n'.join(cleaned_lines)

    def remove_links(self, text):
        # Remove URLs and email addresses
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)
        return text
    
    def remove_special_chars(self, text):
        # Remove unusual Unicode characters while keeping basic punctuation
        text = re.sub(r'[^\x00-\x7F]+', '', text)  # Remove non-ASCII chars
        text = re.sub(r'[^\w\s.,!?;:()\-\'\"]+', ' ', text)  # Keep basic punctuation
        return text
    
    def normalize_whitespace(self, text):
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove spaces at start/end of lines
        text = '\n'.join(line.strip() for line in text.split('\n'))
        # Remove multiple consecutive empty lines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text

    def normalize_quotes(self, text):
        # First replace escaped quotes with temporary placeholder
        text = text.replace('\\"', '###QUOTE###')
        # Normalize different types of quotes to single quotes
        text = text.replace('"', "'").replace('"', "'").replace('"', "'")
        # Replace back the escaped quotes with single quotes
        text = text.replace('###QUOTE###', "'")
        # Handle any remaining escaped quotes
        text = text.replace('\\"', "'")
        return text
    
    def remove_long_dashed_lines(self, text):
        """
        Remove lines composed solely of dash‐like separators and strip inline
        sequences of two or more dashes (hyphens, en‐dashes, em‐dashes).
        """
        # Pattern to match entire lines of only dash‐like characters
        sep_pattern = re.compile(r'^\s*[-\u2012\u2013\u2014]{2,}\s*$')
        # Pattern to match inline sequences of dash‐like characters
        inline_pattern = re.compile(r'[-\u2012\u2013\u2014]{2,}')
        cleaned_lines = []
        for line in text.splitlines():
            # Skip full‐line separators
            if sep_pattern.match(line):
                continue
            # Remove any inline long‐dash sequences
            cleaned_line = inline_pattern.sub('', line)
            cleaned_lines.append(cleaned_line)
        return '\n'.join(cleaned_lines)
        
    def clean_pdf_text(self, text):
        text = self.remove_page_numbers(text)
        text = self.remove_tables(text)
        text = self.remove_image_captions(text)
        text = self.remove_repeated_lines(text)
        text = self.remove_links(text)
        text = self.remove_special_chars(text)
        text = self.normalize_whitespace(text)
        text = self.normalize_quotes(text)
        text = self.remove_long_dashed_lines(text)
        return text
    

def mkdir_if_not_exists(path):
    """
    Create a directory if it does not exist.
    """
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Directory {path} created.")
    return path

def save_txt_and_md_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

def epub_to_text(epub_path):
    book = epub.read_epub(epub_path)
    text_content = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Parse the HTML content using BeautifulSoup
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            # Extract just the text, removing HTML tags
            chapter_text = soup.get_text(separator=' ', strip=True)
            text_content.append(chapter_text)
    return '\n'.join(text_content)

def main():
    return

if __name__ == "__main__":
    main()
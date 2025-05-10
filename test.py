import json
def add_toc_to_md(md_path: str) -> None:
    """
    Add a table of contents to the beginning of a markdown file based on its headers.
    The TOC will be clickable and link to the corresponding sections.
    
    Args:
        md_path (str): Path to the markdown file
    """
    with open(md_path, 'r') as f:
        content = f.read()
    
    # Extract headers and their levels
    headers = []
    for line in content.split('\n'):
        if line.startswith('#'):
            level = len(line.split()[0])
            title = ' '.join(line.split()[1:])
            headers.append((level, title))
    
    # Generate TOC with clickable links
    toc = "# Table of Contents\n\n"
    for level, title in headers:
        indent = '  ' * (level - 1)
        # Create anchor by converting to lowercase, replacing spaces with hyphens
        # and removing special characters
        anchor = title.lower().replace(' ', '-')
        anchor = ''.join(c for c in anchor if c.isalnum() or c == '-')
        toc += f"{indent}- [{title}](#{anchor})\n"
    
    # Add TOC to beginning of file
    with open(md_path, 'w') as f:
        f.write(toc + '\n\n' + content)

def get_sections_dict(md_path: str) -> dict:
    """
    Generate a dictionary from the content in the markdown file where each item includes
    the nearest header as title and the content of that section.
    
    Args:
        md_path (str): Path to the markdown file
        
    Returns:
        dict: Dictionary with section titles as keys and their content as values
    """
    with open(md_path, 'r') as f:
        content = f.read()
    
    sections = {}
    current_title = None
    current_content = []
    
    for line in content.split('\n'):
        if line.startswith('#'):
            # If we have a previous section, save it
            if current_title:
                sections[current_title] = '\n'.join(current_content).strip()
            
            # Start new section
            current_title = ' '.join(line.split()[1:])
            current_content = []
        else:
            # Skip empty lines at the start of a section
            if not current_title and not line.strip():
                continue
            current_content.append(line)
    
    # Add the last section
    if current_title:
        sections[current_title] = '\n'.join(current_content).strip()

    with open('sections.json', 'w') as f:
        json.dump(sections, f)
    
    return sections

# Example usage
summary_path = 'summaries/Atomic_Habits/full_summary_new.md'

# add_toc_to_md(summary_path)
sections = get_sections_dict(summary_path)
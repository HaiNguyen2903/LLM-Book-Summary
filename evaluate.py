from custom_summarization_metric import CustomSummarizationMetric
from deepeval.test_case import LLMTestCase
from deepeval import evaluate
from deepeval.metrics import SummarizationMetric
import json
from IPython import embed
import os.path as osp
from utils import mkdir_if_not_exists

def get_summary_dict(md_path: str) -> dict:
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
    
    return sections

def get_full_content_dict(json_data):
    """
    Generate a dictionary from the book structure json file.
    """
    sections = {}
    
    def process_item(item):
        title = item.get('title', '')
        text = item.get('text', '')
        sections[title] = text
        
        # Process children recursively
        for child in item.get('children', []):
            process_item(child)
    
    # Process each item in the list
    for item in json_data:
        process_item(item)
    return sections

def eval_summaries(summary_path, book_structure_path, save_result=True):
    summary_dict = get_summary_dict(summary_path)

    # ignore table of contents and empty sections
    summary_dict = {k: v for k, v in summary_dict.items() if k != 'Table of Contents' and v != ''}

    with open(book_structure_path, 'r') as f:
        book_structure = json.load(f)

    full_content = get_full_content_dict(book_structure)

    test_cases = []

    # adding test cases for each section
    for section in summary_dict.keys():
        test_cases.append(LLMTestCase(
            input = full_content[section],
            actual_output = summary_dict[section]
        ))

    custom_summarization_metric = CustomSummarizationMetric(n_complex_questions = 5, 
                                                            verbose_mode=False)

    eval_result = evaluate(test_cases, [custom_summarization_metric])

    result_dict = {}

    for i, section in enumerate(summary_dict.keys()):
        summarization_metric_logs = json.loads(eval_result.test_results[i].metrics_data[0].verbose_logs)
        result_dict[section] = summarization_metric_logs

    # save_result
    if save_result:
        save_dir = osp.dirname(summary_path)
        mkdir_if_not_exists(save_dir)
        with open(osp.join(save_dir, 'eval_results.json'), 'w') as f:
            json.dump(result_dict, f)

    return result_dict
    

if __name__ == '__main__':
    book_dir = 'outputs/Self-Development/Atomic Habits'

    book_structure_path = osp.join(book_dir, 'structure.json')
    summary_path = osp.join(book_dir, 'summary.md')

    print(osp.dirname(summary_path))
    # eval_summaries(summary_path, book_structure_path)
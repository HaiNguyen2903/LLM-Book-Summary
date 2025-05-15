from custom_summarization_metric import CustomSummarizationMetric
from deepeval.test_case import LLMTestCase
from deepeval import evaluate
import json
import os.path as osp
from utils import mkdir_if_not_exists
import argparse

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

def eval_summaries(summary_path, summary_style, save_result=True):
    with open(summary_path, 'r') as f:
        summary_dict = json.load(f)

    summary_dict = {k: v for k, v in summary_dict.items() if v['text'] != ''}

    test_cases = []

    for _, item in summary_dict.items():
        if item['text'] == '':
            continue

        original_text = item['text']
        summary = item['summary']

        test_case = LLMTestCase(input=original_text, actual_output=summary)
        test_cases.append(test_case)

    custom_summarization_metric = CustomSummarizationMetric(n_complex_questions = 3, 
                                                            verbose_mode=False)

    eval_result = evaluate(test_cases, [custom_summarization_metric])

    result_dict = {}

    for i, chunk_id in enumerate(summary_dict.keys()):
        summarization_metric_logs = json.loads(eval_result.test_results[i].metrics_data[0].verbose_logs)
        result_dict[chunk_id] = summarization_metric_logs

    # save_result
    if save_result:
        save_dir = osp.dirname(summary_path)
        mkdir_if_not_exists(save_dir)
        with open(osp.join(save_dir, f'eval_results_{summary_style}.json'), 'w') as f:
            json.dump(result_dict, f)

    return result_dict

if __name__ == '__main__':
    # summary_path = 'outputs/Self-Development/Atomic Habits/summary.json'

    parser = argparse.ArgumentParser(description="Book summarizer")
    parser.add_argument('--style', type=str, default='analytic', help='summary style')
    parser.add_argument('--summary_path', type=str, required=True, help='document path')
    
    args = parser.parse_args()
    eval_summaries(args.summary_path, args.style)
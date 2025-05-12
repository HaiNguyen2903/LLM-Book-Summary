import os
import openai
import json
from utils import mkdir_if_not_exists
import os.path as osp
# from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import SummarizationMetric
from document import PDF_Document
from utils import save_txt_and_md_file

class Summarizer:
    def __init__(self, config):
        self.client = openai
        self.config = config

    def _get_response(self, instruction, user_input):
        response = self.client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": user_input}
            ]
        )
        return response.choices[0].message.content.strip()
    
    def _load_prompt(self, file_path):
        with open(file_path, "r") as f:
            return f.read()
        
    def _get_section_summary(self, doc_item: dict, summary_prompt: str) -> str:
        title = doc_item['title']
        level = doc_item['level']
        children = doc_item['children']

        header = '#'*level + ' ' + title

        final_summary = header + '\n'

        # if no children, get summary
        if len(children) == 0:
            summary = self._get_response(
                    instruction=summary_prompt,
                    user_input=doc_item['text']
                )
            final_summary += f"{summary}\n\n"
            return final_summary
        
        for child in children:
            final_summary += self._get_section_summary(doc_item=child, summary_prompt=summary_prompt)

        return final_summary

    def _add_toc(self, content: str) -> str:        
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

        return toc + '\n\n' + content
    
    def _get_doc_summary(self, document: PDF_Document, summary_prompt_path: str, save=True) -> str:
        doc_name = document.name
        doc_contents = document.contents[:2]
        
        summary_prompt = self._load_prompt(summary_prompt_path)

        full_summary = ""

        # get summary for each section
        for item in doc_contents:
            full_summary += self._get_section_summary(doc_item=item, summary_prompt=summary_prompt)

        # add toc to the full summary
        full_summary = self._add_toc(full_summary)

        save_dir = document.save_dir

        mkdir_if_not_exists(save_dir)

        if save:
            save_txt_and_md_file(osp.join(save_dir, 'summary.md'), full_summary)

        return full_summary
                    
    
    def _get_self_reflective_summary(self, input_text, summary_prompt_path,
                                    self_reflect_prompt_path,
                                    max_attempts=5, threshold=0.7):

        evaluator = SummarizationMetric(threshold=threshold, model="gpt-4o-mini")

        summary_prompt = self._load_prompt(summary_prompt_path)
        self_reflect_prompt = self._load_prompt(self_reflect_prompt_path)
        
        summary = self._get_response(instruction=summary_prompt, user_input=input_text)

        questions = None
        best_score = -1
        best_summary = ''
        
        for i in range(max_attempts):
            test_case = LLMTestCase(input=input_text, actual_output=summary)
            evaluator.measure(test_case)

            score = evaluator.score
            reason = evaluator.reason

            if score >= threshold:
                return summary, score

            # save best summary
            if score > best_score:
                best_score = score
                best_summary = summary
            
            # if there are no questions yet
            if not questions:
                questions = evaluator.assessment_questions
                # adding questions to evaluator to avoid re-generating questions
                evaluator = SummarizationMetric(threshold=threshold,
                                                model="gpt-4o-mini",
                                                assessment_questions=questions)
                print('QUESTIONS:', questions)
            
            
            reflect_input = f"""
            Original Text:
            {input_text}

            Previous Summary:
            {best_summary}

            Score and Feedback:
            {reason}
            """

            print(f'ATTEMP {i+1}')
            print(f'SCORE: {score} \n REASON: {reason} \n SUMMARY: {summary}')
            print()

            # rewrite summary
            summary = self._get_response(instruction=self_reflect_prompt, user_input=reflect_input)

        return best_summary, best_score
        

def main():
    openai.api_key = os.getenv("OPENAI_API_KEY")

    with open('config.json', 'r') as f:
        config = json.load(f)

    summarizer = Summarizer(config=config)

    doc_path = 'datasets/books/Self-Development/Atomic Habits.pdf'
    doc = PDF_Document(doc_path)
    
    summary_prompt_path = osp.join(config["PROMPT_DIR"], "summary_chain_of_thought.txt")
    self_reflect_prompt_path = osp.join(config['PROMPT_DIR'], 'self_reflect_cot.txt')

    # with open('summaries/deep_work/Introduction.txt', 'r') as f:
    #     input = f.read()

    # summary = agent._get_self_reflective_summary(input_text=input, summary_prompt_path=summary_prompt_path,
    #                                              self_reflect_prompt_path=self_reflect_prompt_path,
    #                                              max_attempts=2)
    
    # print('FINAL SUMMARY:', summary)

    summarizer._get_doc_summary(document=doc,
                            summary_prompt_path=summary_prompt_path,
                            save=True)

    return

if __name__ == '__main__':
    main()
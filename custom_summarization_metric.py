import json
from typing import List, Optional, Union
import asyncio

from deepeval.test_case import (
    LLMTestCase,
    LLMTestCaseParams,
    ConversationalTestCase,
)
from deepeval.metrics import BaseMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.utils import get_or_create_event_loop, prettify_list
from deepeval.metrics.utils import (
    construct_verbose_logs,
    trimAndLoadJson,
    check_llm_test_case_params,
    initialize_model,
)
from deepeval.metrics.summarization.template import SummarizationTemplate
from deepeval.metrics.faithfulness.template import FaithfulnessTemplate
from deepeval.metrics.indicator import metric_progress_indicator
from deepeval.metrics.summarization.schema import *
from deepeval.metrics.faithfulness.schema import *

from pydantic import BaseModel, Field

required_params: List[LLMTestCaseParams] = [
    LLMTestCaseParams.INPUT,
    LLMTestCaseParams.ACTUAL_OUTPUT,
]

class ComplexQuestion(BaseModel):
    question: str
    answer: str
    importance: int = Field(description="1-5, with 1 being not important and 5 being most important")

class ComplexQuestions(BaseModel):
    questions: List[ComplexQuestion]

class ComplexQuestionVerdictOutput(BaseModel):
    score: int
    reason: str

class ComplexQuestionVerdict(ComplexQuestionVerdictOutput):
    original_answer: str
    summary_answer: str
    question: str

class ComplexQuestionsVerdictsOutputs(BaseModel):
    verdicts: List[ComplexQuestionVerdictOutput]




class CustomSummarizationMetric(BaseMetric):
    def __init__(
        self,
        threshold: float = 0.5,
        n: int = 5,
        n_complex_questions: int = 5,
        model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        assessment_questions: Optional[List[str]] = None,
        include_reason: bool = True,
        async_mode=True,
        strict_mode: bool = False,
        verbose_mode: bool = False,
        truths_extraction_limit: Optional[int] = None,
    ):
        self.threshold = 1 if strict_mode else threshold
        self.model, self.using_native_model = initialize_model(model)
        self.evaluation_model = self.model.get_model_name()

        if assessment_questions is not None and len(assessment_questions) == 0:
            self.assessment_questions = None
        else:
            self.assessment_questions = assessment_questions

        self.complex_assessment_questions = None
        self.include_reason = include_reason
        self.n = n
        self.n_complex_questions = n_complex_questions
        self.async_mode = async_mode
        self.strict_mode = strict_mode
        self.verbose_mode = verbose_mode

        self.truths_extraction_limit = truths_extraction_limit
        if self.truths_extraction_limit is not None:
            self.truths_extraction_limit = max(self.truths_extraction_limit, 0)

    def measure(
        self,
        test_case: Union[LLMTestCase, ConversationalTestCase],
        _show_indicator: bool = True,
    ) -> float:
        if isinstance(test_case, ConversationalTestCase):
            test_case = test_case.turns[0]
        check_llm_test_case_params(test_case, required_params, self)

        self.evaluation_cost = 0 if self.using_native_model else None
        with metric_progress_indicator(self, _show_indicator=_show_indicator):
            if self.async_mode:
                loop = get_or_create_event_loop()
                loop.run_until_complete(
                    self.a_measure(test_case, _show_indicator=False)
                )
            else:
                self.truths: str = self._generate_truths(test_case.input)
                self.claims: List[str] = self._generate_claims(
                    test_case.actual_output
                )
                self.coverage_verdicts: List[SummarizationCoverageVerdict] = (
                    self._generate_coverage_verdicts(test_case)
                )
                self.alignment_verdicts: List[SummarizationAlignmentVerdict] = (
                    self._generate_alignment_verdicts()
                )
                self.complex_coverage_verdicts: List[ComplexQuestionVerdict] = (
                    self._generate_complex_coverage_verdicts(test_case)
                )

                alignment_score = self._calculate_score(ScoreType.ALIGNMENT)
                coverage_score = self._calculate_score(ScoreType.COVERAGE)
                complex_coverage_scores = [e.score / 5 for e in self.complex_coverage_verdicts]
                complex_coverage_score = sum(complex_coverage_scores) / len(complex_coverage_scores)

                self.score_breakdown = {
                    ScoreType.ALIGNMENT.value: alignment_score,
                    ScoreType.COVERAGE.value: coverage_score,
                }
                
                self.score = (alignment_score + coverage_score + complex_coverage_score) / 3
                self.reason = self._generate_reason()
                self.success = self.score >= self.threshold

                logs = {
                    'claims': self.claims,
                    'assessment_questions': self.assessment_questions,
                    'complex_assessment_questions': [e.dict() for e in self.complex_assessment_questions],
                    'coverage_verdicts': [v.dict() for v in self.coverage_verdicts],
                    'alignment_verdicts': [v.dict() for v in self.alignment_verdicts],
                    'complex_coverage_verdicts': [v.dict() for v in self.complex_coverage_verdicts],
                    'coverage_score': coverage_score,
                    'alignment_score': alignment_score,
                    'complex_coverage_score': complex_coverage_score,
                    'score': self.score,
                    'reason': self.reason,
                    'success': self.success,
                }
                self.verbose_logs = json.dumps(logs)

                return self.score

    async def a_measure(
        self,
        test_case: Union[LLMTestCase, ConversationalTestCase],
        _show_indicator: bool = True,
    ) -> float:
        if isinstance(test_case, ConversationalTestCase):
            test_case = test_case.turns[0]
        check_llm_test_case_params(test_case, required_params, self)

        self.evaluation_cost = 0 if self.using_native_model else None
        with metric_progress_indicator(
            self,
            async_mode=True,
            _show_indicator=_show_indicator,
        ):
            self.truths, self.claims = await asyncio.gather(
                self._a_generate_truths(test_case.input),
                self._a_generate_claims(test_case.actual_output),
            )

            (
                self.complex_coverage_verdicts, # List[ComplexQuestionVerdict]
                self.coverage_verdicts, # List[SummarizationCoverageVerdict]
                self.alignment_verdicts, # List[SummarizationAlignmentVerdict]
            ) = await asyncio.gather(
                self._a_generate_complex_coverage_verdicts(test_case),
                self._a_generate_coverage_verdicts(test_case),
                self._a_generate_alignment_verdicts(),
            )
            
            alignment_score = self._calculate_score(ScoreType.ALIGNMENT)
            coverage_score = self._calculate_score(ScoreType.COVERAGE)
            complex_coverage_scores = [e.score / 5 for e in self.complex_coverage_verdicts]
            complex_coverage_score = sum(complex_coverage_scores) / len(complex_coverage_scores)

            self.score_breakdown = {
                ScoreType.ALIGNMENT.value: alignment_score,
                ScoreType.COVERAGE.value: coverage_score,
            }

            # F1 score between the alignment score and complex coverage score
            precision = alignment_score
            recall = complex_coverage_score
            self.score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            self.reason = await self._a_generate_reason()
            self.success = self.score >= self.threshold

            logs = {
                'claims': self.claims,
                'assessment_questions': self.assessment_questions,
                'complex_assessment_questions': [e.dict() for e in self.complex_assessment_questions],
                'coverage_verdicts': [v.dict() for v in self.coverage_verdicts],
                'alignment_verdicts': [v.dict() for v in self.alignment_verdicts],
                'complex_coverage_verdicts': [v.dict() for v in self.complex_coverage_verdicts],
                'coverage_score': coverage_score,
                'alignment_score': alignment_score,
                'complex_coverage_score': complex_coverage_score,
                'score': self.score,
                'reason': self.reason,
                'success': self.success,
            }
            self.verbose_logs = json.dumps(logs)
            return self.score

    async def _a_generate_reason(self) -> str:
        if self.include_reason is False:
            return None

        contradictions = []
        redundancies = []
        for verdict in self.alignment_verdicts:
            if verdict.verdict.strip().lower() == "no":
                contradictions.append(verdict.reason)
            elif verdict.verdict.strip().lower() == "idk":
                redundancies.append(verdict.reason)

        questions = []
        if self.coverage_verdicts:
            for verdict in self.coverage_verdicts:
                if (
                    verdict.original_verdict.strip().lower() == "yes"
                    and verdict.summary_verdict.strip().lower() == "no"
                ):
                    questions.append(verdict.question)

        prompt: dict = SummarizationTemplate.generate_reason(
            contradictions=contradictions,
            redundancies=redundancies,
            questions=questions,
            score=format(self.score, ".2f"),
        )

        if len(questions) > 0:
            prompt += f"""Questions the original text can answer but not the summary:
{questions}

"""
        prompt += """JSON:
"""

        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["reason"]
        else:
            try:
                res: Reason = await self.model.a_generate(prompt, schema=Reason)
                return res.reason
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["reason"]

    def _generate_reason(self) -> str:
        if self.include_reason is False:
            return None

        contradictions = []
        redundancies = []
        for verdict in self.alignment_verdicts:
            if verdict.verdict.strip().lower() == "no":
                contradictions.append(verdict.reason)
            elif verdict.verdict.strip().lower() == "idk":
                redundancies.append(verdict.reason)

        questions = []
        if self.coverage_verdicts:
            for verdict in self.coverage_verdicts:
                if (
                    verdict.original_verdict.strip().lower() == "yes"
                    and verdict.summary_verdict.strip().lower() == "no"
                ):
                    questions.append(verdict.question)

        prompt: dict = SummarizationTemplate.generate_reason(
            contradictions=contradictions,
            redundancies=redundancies,
            questions=questions,
            score=format(self.score, ".2f"),
        )

        if len(questions) > 0:
            prompt += f"""Questions the original text can answer but not the summary:
{questions}

"""
        prompt += """JSON:
"""

        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["reason"]
        else:
            try:
                res: Reason = self.model.generate(prompt, schema=Reason)
                return res.reason
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["reason"]

    def _calculate_score(self, score_type: ScoreType) -> float:
        if score_type == ScoreType.ALIGNMENT:
            total = len(self.alignment_verdicts)
            if total == 0:
                return 0
            faithfulness_count = 0
            for verdict in self.alignment_verdicts:
                # Different from the faithfulness score, this
                # penalizes 'idk' (full of fluff) summaries
                if verdict.verdict.strip().lower() == "yes":
                    faithfulness_count += 1

            score = faithfulness_count / total

        else:
            if self.assessment_questions is None:
                return 1
            total = 0
            coverage_count = 0
            for verdict in self.coverage_verdicts:
                if verdict.original_verdict.strip().lower() == "yes":
                    total += 1
                    if verdict.summary_verdict.strip().lower() == "yes":
                        coverage_count += 1

            if total == 0:
                return 0

            score = coverage_count / total

        return 0 if self.strict_mode and score < self.threshold else score

    async def _a_generate_answers(self, text: str) -> List[str]:
        prompt = SummarizationTemplate.generate_answers(
            questions=self.assessment_questions, text=text
        )
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["answers"]
        else:
            try:
                res: Answers = await self.model.a_generate(
                    prompt, schema=Answers
                )
                return res.answers
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["answers"]

    def _generate_answers(self, text: str) -> List[str]:
        prompt = SummarizationTemplate.generate_answers(
            questions=self.assessment_questions, text=text
        )
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["answers"]
        else:
            try:
                res: Answers = self.model.generate(prompt, schema=Answers)
                return res.answers
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["answers"]
            
    async def _a_generate_complex_answers(self, text: str) -> List[str]:
        prompt = generate_complex_answers(self.complex_assessment_questions, text)
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["answers"]
        else:
            try:
                res: Answers = await self.model.a_generate(prompt, schema=Answers)
                return res.answers
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["answers"]
            
    def _generate_complex_answers(self, text: str) -> List[str]:
        prompt = generate_complex_answers(self.complex_assessment_questions, text)
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["answers"]
        else:
            try:
                res: Answers = self.model.generate(prompt, schema=Answers)
                return res.answers
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["answers"]

    async def _a_generate_assessment_questions(self, text: str):
        prompt = SummarizationTemplate.generate_questions(text=text, n=self.n)
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["questions"]
        else:
            try:
                res: Questions = await self.model.a_generate(
                    prompt, schema=Questions
                )
                return res.questions
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["questions"]

    def _generate_assessment_questions(self, text: str):
        prompt = SummarizationTemplate.generate_questions(text=text, n=self.n)
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["questions"]
        else:
            try:
                res: Questions = self.model.generate(prompt, schema=Questions)
                return res.questions
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["questions"]
            
    async def _a_generate_complex_assessment_questions(self, text: str) -> List[ComplexQuestion]:
        prompt = generate_complex_questions(text, self.n_complex_questions)
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            data = [ComplexQuestion(**e) for e in data["questions"]]
            return data
        else:
            try:
                print(f'Generating complex assessment questions - not using native model')
                res = await self.model.a_generate(prompt, schema=ComplexQuestions)
                return res.questions
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                out = data["questions"]
                out = [ComplexQuestion(**e) for e in out]
                return out
            
    def _generate_complex_assessment_questions(self, text: str) -> List[ComplexQuestion]:
        prompt = generate_complex_questions(text, self.n_complex_questions)
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            data = [ComplexQuestion(**e) for e in data["questions"]]
            return data
        else:
            try:
                print(f'Generating complex assessment questions - not using native model')
                res = self.model.generate(prompt, schema=ComplexQuestions)
                return res.questions
            except TypeError as e:
                print(f'Type error: {e}')
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                out = data["questions"]
                out = [ComplexQuestion(**e) for e in out]
                return out




    async def _a_generate_coverage_verdicts(
        self, test_case: LLMTestCase
    ) -> List[SummarizationCoverageVerdict]:
        if self.assessment_questions is None:
            self.assessment_questions = (
                await self._a_generate_assessment_questions(test_case.input)
            )

        tasks = [
            self._a_generate_answers(test_case.input),
            self._a_generate_answers(test_case.actual_output),
        ]
        results = await asyncio.gather(*tasks)
        original_answers = results[0]
        summary_answers = results[1]

        if len(original_answers) != len(summary_answers):
            raise ValueError("Number of verdicts generated does not equal.")

        coverage_veridcts: List[SummarizationCoverageVerdict] = []
        for i in range(len(original_answers)):
            coverage_veridcts.append(
                SummarizationCoverageVerdict(
                    summary_verdict=summary_answers[i],
                    original_verdict=original_answers[i],
                    question=self.assessment_questions[i],
                )
            )
        return coverage_veridcts

    def _generate_coverage_verdicts(
        self, test_case: LLMTestCase
    ) -> List[SummarizationCoverageVerdict]:
        if self.assessment_questions is None:
            self.assessment_questions = self._generate_assessment_questions(
                test_case.input
            )

        original_answers = self._generate_answers(test_case.input)
        summary_answers = self._generate_answers(test_case.actual_output)

        if len(original_answers) != len(summary_answers):
            raise ValueError("Number of verdicts generated does not equal.")

        coverage_veridcts: List[SummarizationCoverageVerdict] = []
        for i in range(len(original_answers)):
            coverage_veridcts.append(
                SummarizationCoverageVerdict(
                    summary_verdict=summary_answers[i],
                    original_verdict=original_answers[i],
                    question=self.assessment_questions[i],
                )
            )

        return coverage_veridcts
    
    def _generate_complex_coverage_verdicts(self, test_case: LLMTestCase) -> List[ComplexQuestionVerdict]:
        print(f'Generating complex assessment questions')
        if self.complex_assessment_questions is None:
            self.complex_assessment_questions: List[ComplexQuestion] = self._generate_complex_assessment_questions(test_case.input)
        
        print(f'Generated complex assessment questions = {self.complex_assessment_questions}')

        original_answers = [e.answer for e in self.complex_assessment_questions]
        summary_answers: List[str] = self._generate_complex_answers(test_case.actual_output)

        print(f'Generated complex answers = {summary_answers}')

        if len(original_answers) != len(summary_answers):
            raise ValueError("Number of verdicts generated does not equal.")
        
        answers = [{'original_answer': o, 'summary_answer': s} for o, s in zip(original_answers, summary_answers)]
        
        prompt = generate_complex_verdicts(answers)
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            out = [ComplexQuestionVerdict(original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                              question = self.complex_assessment_questions[i].question,
                                              **e) for i, e in enumerate(data["verdicts"])]
            return out
        else:
            try:
                res: ComplexQuestionsVerdictsOutputs = self.model.generate(prompt, schema=ComplexQuestionsVerdictsOutputs)
                out = [ComplexQuestionVerdict(original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                              question = self.complex_assessment_questions[i].question,
                                              **e) for i, e in enumerate(res.verdicts)]
                return out
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                out = data["verdicts"]

                out = [ComplexQuestionVerdict(**e, original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                              question = self.complex_assessment_questions[i].question,
                                              ) for i, e in enumerate(out)]
                return out
    
    async def _a_generate_complex_coverage_verdicts(self, test_case: LLMTestCase) -> List[ComplexQuestionVerdict]:
        print(f'Generating complex assessment questions')
        if self.complex_assessment_questions is None:
            self.complex_assessment_questions: List[ComplexQuestion] = await self._a_generate_complex_assessment_questions(test_case.input)
        
        print(f'Generated complex assessment questions = {self.complex_assessment_questions}')

        original_answers = [e.answer for e in self.complex_assessment_questions]
        summary_answers: List[str] = await self._a_generate_complex_answers(test_case.actual_output)

        print(f'Generated complex answers = {summary_answers}')

        if len(original_answers) != len(summary_answers):
            raise ValueError("Number of verdicts generated does not equal.")
        
        answers = [{'original_answer': o, 'summary_answer': s} for o, s in zip(original_answers, summary_answers)]
        
        prompt = generate_complex_verdicts(answers)
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            out = [ComplexQuestionVerdict(original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                              question = self.complex_assessment_questions[i].question,
                                              **e) for i, e in enumerate(data["verdicts"])]
            return out
        else:
            try:
                res: ComplexQuestionsVerdictsOutputs = await self.model.a_generate(prompt, schema=ComplexQuestionsVerdictsOutputs)
                out = [ComplexQuestionVerdict(original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                            question = self.complex_assessment_questions[i].question,
                                            **e) for i, e in enumerate(res.verdicts)]
                return out
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                out = data["verdicts"]

                out = [ComplexQuestionVerdict(**e, original_answer=answers[i]['original_answer'], summary_answer=answers[i]['summary_answer'],
                                            question = self.complex_assessment_questions[i].question,
                                            ) for i, e in enumerate(out)]
                return out


    async def _a_generate_alignment_verdicts(
        self,
    ) -> List[SummarizationAlignmentVerdict]:
        if len(self.claims) == 0:
            return []

        verdicts: List[SummarizationAlignmentVerdict] = []
        prompt = SummarizationTemplate.generate_alignment_verdicts(
            summary_claims=self.claims, orignal_text=self.truths
        )
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            verdicts = [
                SummarizationAlignmentVerdict(**item)
                for item in data["verdicts"]
            ]
            return verdicts
        else:
            try:
                res: Verdicts = await self.model.a_generate(
                    prompt, schema=Verdicts
                )
                verdicts = [item for item in res.verdicts]
                return verdicts
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                verdicts = [
                    SummarizationAlignmentVerdict(**item)
                    for item in data["verdicts"]
                ]
                return verdicts

    def _generate_alignment_verdicts(
        self,
    ) -> List[SummarizationAlignmentVerdict]:
        if len(self.claims) == 0:
            return []

        verdicts: List[SummarizationAlignmentVerdict] = []
        prompt = SummarizationTemplate.generate_alignment_verdicts(
            summary_claims=self.claims, orignal_text=self.truths
        )
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            verdicts = [
                SummarizationAlignmentVerdict(**item)
                for item in data["verdicts"]
            ]
            return verdicts
        else:
            try:
                res: Verdicts = self.model.generate(prompt, schema=Verdicts)
                verdicts = [item for item in res.verdicts]
                return verdicts
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                verdicts = [
                    SummarizationAlignmentVerdict(**item)
                    for item in data["verdicts"]
                ]
                return verdicts

    async def _a_generate_truths(self, text: str) -> str:
        return text
    def _generate_truths(self, text: str) -> str:
        return text
    
    async def _a_generate_claims(self, text: str) -> List[str]:
        # Borrow faithfulness template
        prompt = FaithfulnessTemplate.generate_claims(actual_output=text)
        if self.using_native_model:
            res, cost = await self.model.a_generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["claims"]
        else:
            try:
                res: Claims = await self.model.a_generate(prompt, schema=Claims)
                return res.claims
            except TypeError:
                res = await self.model.a_generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["claims"]


    def _generate_claims(self, text: str) -> List[str]:
        # Borrow faithfulness template
        prompt = FaithfulnessTemplate.generate_claims(actual_output=text)
        if self.using_native_model:
            res, cost = self.model.generate(prompt)
            self.evaluation_cost += cost
            data = trimAndLoadJson(res, self)
            return data["claims"]
        else:
            try:
                res: Claims = self.model.generate(prompt, schema=Claims)
                return res.claims
            except TypeError:
                res = self.model.generate(prompt)
                data = trimAndLoadJson(res, self)
                return data["claims"]

    def is_successful(self) -> bool:
        if self.error is not None:
            self.success = False
        else:
            try:
                self.success = self.score >= self.threshold
            except:
                self.success = False
        return self.success

    @property
    def __name__(self):
        return "Custom Summarization Metric"
    


##### PROMPT




def generate_complex_answers(questions, text):
        return f"""Based on the list of questions, generate a JSON with key 'answers', which answers the questions in order using information from the text.
        If the text does not contain enough information to answer the question, return 'idk'.
        The answer should be a concise 1-sentence long answer, which does not need to be in full sentences.

The length of 'answers' SHOULD BE STRICTLY EQUAL to that of questions.

Text:
{text}

Questions:
{questions}

JSON:
"""

def generate_complex_verdicts(answers):
    return f"""You are given a list of JSON objects. Each contains 'original_answer' and 'summary_answer'.
    Original answer is the correct answer to a question. 
    Your job is to assess if the summary answer is correct, based on the model answer which is the original answer.
    Give a score from 0 to 5, with 0 being completely wrong, and 5 being completely correct.
    If the 'summary_answer' is 'idk', return a score of 0.

    Return a JSON object with the key 'verdicts', which is a list of JSON objects, with the keys: 'score', and 'reason': a concise 1 sentence explanation for the score.

The length of the list SHOULD BE STRICTLY EQUAL to that of the answers list.

Answers:
{answers}

JSON:
"""

def generate_complex_questions(text, n):
        return f"""Based on the given text, generate a list of {n} questions that can be answered with the information in this document.
        The questions should be related to the main points of this document. 
        Then, provide a concise 1 sentence answer to the question, using only information that can be found in the document.
        Answer concisely, your answer does not need to be in full sentences.
        Make sure the questions are different from each other. 
        They should cover a combination of questions on cause, impact, policy, advantages/disadvantages, etc.

        Lastly, rate the importance of this question to the document on a scale of 1 to 5, with 1 being not important and 5 being most important. 
        Important question means the question is related to an essential or main point of the document,
        and that not knowing the answer to this question would mean that the reader has not understood the document's main point at all.
        A less important question is one asking about a smaller detail, that is not essential to understanding the document's main point.

        
** IMPORTANT
Return a JSON object with the key 'questions', which is a list of {n} JSON objects, with the keys 'question', 'answer', and 'importance'.
**
Text:
{text}

JSON:
"""
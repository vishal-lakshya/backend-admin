from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PracticeFilterOption(BaseModel):
    value: str
    label: str
    count: int = 0


class PracticeExamOption(BaseModel):
    id: int
    name: str
    code: str


class PracticeSubjectOption(BaseModel):
    id: int
    exam_id: int
    name: str
    code: str


class PracticeSessionStatsOut(BaseModel):
    attempted: int
    correct: int
    accuracy: float


class PracticeQuestionOptionOut(BaseModel):
    key: str
    text: str


class PracticeQuestionOut(BaseModel):
    id: str
    exam_id: int
    exam_name: str
    subject_id: int
    subject_name: str
    topic: str | None
    question_text: str
    options: list[PracticeQuestionOptionOut]
    correct_option: str
    explanation: str
    difficulty: str
    question_type: str = 'MCQ'
    pyq_year: int | None
    tags: list[str]
    is_bookmarked: bool = False
    selected_option: str | None = None
    is_attempted: bool = False
    is_correct: bool | None = None


class PracticeQuestionListOut(BaseModel):
    items: list[PracticeQuestionOut]
    total: int
    skip: int
    limit: int
    stats: PracticeSessionStatsOut


class PracticeBootstrapOut(BaseModel):
    exams: list[PracticeExamOption]
    subjects: list[PracticeSubjectOption]
    difficulty_options: list[PracticeFilterOption]
    question_type_options: list[PracticeFilterOption]
    pyq_years: list[int]
    stats: PracticeSessionStatsOut


class PracticeAttemptRequest(BaseModel):
    selected_option: str = Field(min_length=1, max_length=2)

    @field_validator('selected_option')
    @classmethod
    def normalize_option(cls, value: str) -> str:
        return value.strip().upper()


class PracticeAttemptOut(BaseModel):
    question_id: str
    selected_option: str
    correct_option: str
    is_correct: bool
    explanation: str
    stats: PracticeSessionStatsOut


class PracticeBookmarkToggleOut(BaseModel):
    question_id: str
    is_bookmarked: bool

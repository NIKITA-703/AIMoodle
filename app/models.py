from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuizRequirements:
    pass_grade: Optional[float] = None
    allowed_attempts: Optional[int] = None
    attempt_number: Optional[int] = None
    course_id: str = ""
    quiz_id: str = ""

    @property
    def remaining_attempts_after_current(self):
        if self.allowed_attempts is None or self.attempt_number is None:
            return None
        return max(self.allowed_attempts - self.attempt_number, 0)


@dataclass
class QuizResult:
    submitted: bool = False
    passed: bool = False
    score: Optional[float] = None
    max_score: Optional[float] = None
    grade_percent: Optional[float] = None
    pass_grade: Optional[float] = None
    attempt_number: Optional[int] = None
    remaining_attempts: Optional[int] = None
    new_confirmed_answers: int = 0
    source_counts: dict = field(
        default_factory=lambda: {
            "lecture": 0,
            "memory": 0,
            "general_knowledge": 0,
        }
    )
    error: str = ""


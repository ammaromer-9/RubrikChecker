from typing import Literal

# How tough the student's teacher is. "standard" is the unmodified rubric-only grader.
Strictness = Literal["lenient", "standard", "strict"]
STRICTNESS_LEVELS: tuple[str, ...] = ("lenient", "standard", "strict")

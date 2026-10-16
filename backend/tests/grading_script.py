"""A scripted stand-in for the LLM that plays grader, feedback writer and extractor."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.services.llm_client import Message

RUBRIC: dict[str, Any] = {
    "criteria": [
        {
            "id": "thesis", "name": "Thesis", "max_points": 10,
            "levels": [
                {"label": "Excellent", "points": 10, "description": "Clear, arguable thesis"},
                {"label": "Fair", "points": 5, "description": "Thesis present but vague"},
                {"label": "Weak", "points": 0, "description": "No thesis"},
            ],
        },
        {
            "id": "support", "name": "Evidence & Support", "max_points": 6,
            "levels": [
                {"label": "Strong", "points": 6, "description": "Specific, cited evidence"},
                {"label": "Some", "points": 3, "description": "General evidence"},
                {"label": "None", "points": 0, "description": "No evidence"},
            ],
        },
    ]
}

DRAFT = (
    "Social media harms teen sleep. Many students scroll late at night.\n\n"
    "However, schools should not ban phones outright because families differ."
)

LABELS = {"thesis": {10: "Excellent", 5: "Fair", 0: "Weak"}, "support": {6: "Strong", 3: "Some", 0: "None"}}


def grade_reply(criterion_id: str, points: int, evidence: list[dict] | None = None,
                confidence: str = "high", label: str | None = None) -> str:
    return json.dumps({
        "criterion_id": criterion_id,
        "reasoning": f"Reasoning for {criterion_id}",
        "level_label": label or LABELS[criterion_id][points],
        "points": points,
        "evidence": evidence or [],
        "confidence": confidence,
    })


def feedback_reply(missing: str = "The evidence is general rather than specific.",
                   questions: list[str] | None = None) -> str:
    return json.dumps({
        "whats_missing": missing,
        "where_in_draft": "The first paragraph",
        "evidence_indexes": [1, 99],
        "guiding_questions": questions or ["What specific study or statistic could you point to?"],
    })


class ScriptedLLM:
    """Replies are consumed per criterion in order; the last one repeats when exhausted.
    A reply that is an Exception is raised."""

    def __init__(self, grades: dict[str, list], feedback: dict[str, list] | None = None,
                 requirements: str | None = None) -> None:
        self.grades = grades
        self.feedback = feedback or {}
        self.requirements = requirements or '{"requirements": []}'
        self._seen: dict[str, int] = defaultdict(int)
        self.feedback_prompts: list[str] = []

    def _next(self, key: str, replies: list) -> str:
        reply = replies[min(self._seen[key], len(replies) - 1)]
        self._seen[key] += 1
        if isinstance(reply, Exception):
            raise reply
        return reply

    def handler(self, system: str, messages: list[Message]) -> str:
        prompt = messages[0]["content"]
        if "careful, consistent grader" in system:
            criterion_id = re.search(r"Criterion ID: (\S+)", prompt).group(1)  # type: ignore[union-attr]
            return self._next(f"grade:{criterion_id}", self.grades[criterion_id])
        if "writing coach" in system:
            self.feedback_prompts.append(prompt)
            name = re.search(r"Criterion: (.+?) \(the draft", prompt).group(1)  # type: ignore[union-attr]
            replies = self.feedback.get(name) or [feedback_reply()]
            return self._next(f"feedback:{name}", replies)
        if "machine-checkable" in system:
            return self.requirements
        raise AssertionError(f"unexpected system prompt: {system[:60]}")

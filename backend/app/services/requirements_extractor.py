from app.prompts.loader import load_prompt
from app.schemas.requirements import RequirementList
from app.services.llm_client import LLMClient

SYSTEM_PROMPT = (
    "You extract machine-checkable requirements from assignment instructions. "
    "You output only a single valid JSON object."
)


async def extract_requirements(
    llm: LLMClient, instructions_text: str, grading_id: int | None = None
) -> RequirementList:
    """The one LLM call in the instruction-check flow. Evaluation itself is plain Python
    (see instruction_checks.py)."""
    prompt = load_prompt("requirements_extract")
    return await llm.generate_structured(
        RequirementList,
        purpose="requirements_extract",
        system=SYSTEM_PROMPT,
        prompt=prompt.render(instructions_text=instructions_text),
        prompt_version=prompt.version,
        grading_id=grading_id,
        max_tokens=2048,
        temperature=0.0,
    )

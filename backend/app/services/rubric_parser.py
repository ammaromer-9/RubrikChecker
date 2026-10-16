from app.prompts.loader import load_prompt
from app.schemas.rubric import Rubric
from app.services.llm_client import LLMClient

SYSTEM_PROMPT = (
    "You convert grading rubrics into structured JSON. "
    "You output only a single valid JSON object."
)


async def parse_rubric(llm: LLMClient, rubric_text: str) -> Rubric:
    """Convert raw rubric text into a validated Rubric.

    Schema failures are retried once (with the validation error) inside the LLM client.
    """
    prompt = load_prompt("rubric_parse")
    return await llm.generate_structured(
        Rubric,
        purpose="rubric_parse",
        system=SYSTEM_PROMPT,
        prompt=prompt.render(rubric_text=rubric_text),
        prompt_version=prompt.version,
        max_tokens=4096,
        temperature=0.0,
    )

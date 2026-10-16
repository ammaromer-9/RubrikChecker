from pydantic import BaseModel


class ExtractedText(BaseModel):
    filename: str
    text: str
    char_count: int

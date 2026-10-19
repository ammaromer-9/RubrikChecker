from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.services.passwords import MAX_LENGTH, MIN_LENGTH

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
Password = Annotated[str, Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] = ""


class LoginRequest(BaseModel):
    email: Email
    # No length rule here: a login must never reveal the password rules to a guesser.
    password: Annotated[str, Field(min_length=1, max_length=MAX_LENGTH)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    created_at: datetime

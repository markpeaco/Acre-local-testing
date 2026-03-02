from typing import Optional

from pydantic import BaseModel, field_validator


class ClientPayload(BaseModel):
    contact_name: str
    email_address: str
    number: str
    client_user_originator: str
    income: str
    external_id: int
    external_name: str

    @field_validator("contact_name")
    @classmethod
    def must_include_last_name(cls, v: str) -> str:
        if len(v.strip().split(" ", 1)) < 2:
            raise ValueError("contact_name must include both a first and last name")
        return v.strip()


class CasePayload(BaseModel):
    client_ids: list[str]
    owner_user_id: Optional[str] = None
    owner_id: Optional[str] = None
    mortgage_amount: str


class GetClientPayload(BaseModel):
    client_id: str

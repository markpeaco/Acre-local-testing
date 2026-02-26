from pydantic import BaseModel, field_validator


class ClientPayload(BaseModel):
    contact_name: str
    email_address: str
    number: str

    @field_validator("contact_name")
    @classmethod
    def must_include_last_name(cls, v: str) -> str:
        if len(v.strip().split(" ", 1)) < 2:
            raise ValueError("contact_name must include both a first and last name")
        return v.strip()

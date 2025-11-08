"""Account-related types (credits, packages, etc.)."""

import decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Credits(BaseModel):
    """User's API credit balance."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    credit: decimal.Decimal
    created_at: str
    updated_at: str
    has_phone_sha256: Optional[bool] = None
    has_free_credit: Optional[bool] = None


class Package(BaseModel):
    """User's prepaid package information."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    type: str
    total: int
    balance: int
    created_at: str
    updated_at: str
    finished_at: Optional[str] = None

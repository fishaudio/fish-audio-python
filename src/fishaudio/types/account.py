"""Account-related types (credits, packages, etc.)."""

import decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Credits(BaseModel):
    """User's API credit balance.

    Attributes:
        id: Unique credits record identifier
        user_id: User identifier
        credit: Current credit balance (decimal for precise accounting)
        created_at: Timestamp when the credits record was created
        updated_at: Timestamp when the credits were last updated
        has_phone_sha256: Whether the user has a verified phone number. Optional
        has_free_credit: Whether the user has received free credits. Optional
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    credit: decimal.Decimal
    created_at: str
    updated_at: str
    has_phone_sha256: Optional[bool] = None
    has_free_credit: Optional[bool] = None


class Package(BaseModel):
    """User's prepaid package information.

    Attributes:
        id: Unique package identifier
        user_id: User identifier
        type: Package type identifier
        total: Total units in the package
        balance: Remaining units in the package
        created_at: Timestamp when the package was purchased
        updated_at: Timestamp when the package was last updated
        finished_at: Timestamp when the package was fully consumed. None if still active
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    user_id: str
    type: str
    total: int
    balance: int
    created_at: str
    updated_at: str
    finished_at: Optional[str] = None

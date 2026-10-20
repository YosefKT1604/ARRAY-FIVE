from typing import Any

from pydantic import BaseModel


class Problem(BaseModel):
    """RFC 9457 standard Problem Details."""
    type: str = "about:blank"
    title: str
    status: int
    detail : str | None = None
    instance : str | None = None
    errors: list[dict[str, Any]] | None = None
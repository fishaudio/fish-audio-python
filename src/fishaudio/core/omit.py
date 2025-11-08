"""OMIT sentinel for distinguishing None from not-provided parameters."""

from typing import Any


class _Omit:
    """
    Sentinel value to distinguish between explicitly passing None vs not providing a parameter.

    Example:
        def method(param: Optional[str] = OMIT):
            if param is OMIT:
                # Parameter not provided
                pass
            elif param is None:
                # Explicitly set to None
                pass
            else:
                # Has a value
                pass
    """

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "OMIT"


OMIT: Any = _Omit()

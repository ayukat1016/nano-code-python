"""
Simple calculator utility functions.

Functions return tuples of (result, error). On success, error is None.
This follows the project's coding conventions.
"""
from typing import Tuple, Optional


def add(a: float, b: float) -> Tuple[float, Optional[str]]:
    """Return sum of a and b."""
    try:
        return a + b, None
    except Exception as e:
        return 0.0, str(e)


def subtract(a: float, b: float) -> Tuple[float, Optional[str]]:
    """Return a - b."""
    try:
        return a - b, None
    except Exception as e:
        return 0.0, str(e)


def multiply(a: float, b: float) -> Tuple[float, Optional[str]]:
    """Return a * b."""
    try:
        return a * b, None
    except Exception as e:
        return 0.0, str(e)


def divide(a: float, b: float) -> Tuple[float, Optional[str]]:
    """Return a / b. Returns error string on division by zero."""
    try:
        if b == 0:
            return 0.0, "division by zero"
        return a / b, None
    except Exception as e:
        return 0.0, str(e)

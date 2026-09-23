from typing import Union

Number = Union[int, float]


def add(a: Number, b: Number) -> float:
    """Return the sum of a and b as a float."""
    return float(a + b)


def subtract(a: Number, b: Number) -> float:
    """Return the difference a - b as a float."""
    return float(a - b)


def multiply(a: Number, b: Number) -> float:
    """Return the product of a and b as a float."""
    return float(a * b)


def divide(a: Number, b: Number) -> float:
    """Return the quotient a / b as a float.

    Raises:
        ZeroDivisionError: If b is zero.
    """
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return float(a / b)

import pytest
from calculator import add, subtract, multiply, divide


def test_add():
    assert add(2, 3) == 5.0
    assert add(2.5, 0.5) == 3.0


def test_subtract():
    assert subtract(5, 3) == 2.0
    assert subtract(2.5, 0.5) == 2.0


def test_multiply():
    assert multiply(4, 2) == 8.0
    assert multiply(2.5, 2) == 5.0


def test_divide():
    assert divide(6, 3) == 2.0
    assert divide(5, 2) == 2.5


def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)

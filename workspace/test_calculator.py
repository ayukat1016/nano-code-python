from calculator import add, subtract, multiply, divide


def test_add():
    res, err = add(1, 2)
    assert err is None
    assert res == 3


def test_subtract():
    res, err = subtract(5, 3)
    assert err is None
    assert res == 2


def test_multiply():
    res, err = multiply(2, 4)
    assert err is None
    assert res == 8


def test_divide():
    res, err = divide(10, 2)
    assert err is None
    assert res == 5


def test_divide_by_zero():
    res, err = divide(1, 0)
    assert err == "division by zero"
    assert res == 0.0

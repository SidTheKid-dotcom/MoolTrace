from mooltrace.gate import is_caught


def test_caught_requires_warn_or_block():
    claim = {"n": 2, "name": "Allen 2013"}
    assert is_caught(claim, "warn")
    assert is_caught(claim, "block")
    assert not is_caught(claim, "pass")
    assert not is_caught(claim, "incomplete")


def test_retraction_fixture_requires_block():
    claim = {"n": 7, "name": "Lancet 2020", "expect_retraction": True}
    assert is_caught(claim, "block")
    assert not is_caught(claim, "warn")
    assert not is_caught(claim, "pass")

from ppa_frame_sampler.output.naming import safe_slug


def test_slug_is_filesystem_safe():
    s = safe_slug("Hello / World? * (PPA)")
    assert "/" not in s
    assert "?" not in s
    assert "*" not in s
    assert "\\" not in s


def test_slug_collapses_underscores():
    s = safe_slug("a___b___c")
    assert "__" not in s


def test_slug_respects_max_len():
    s = safe_slug("a" * 200, max_len=80)
    assert len(s) <= 80


def test_slug_empty_input():
    s = safe_slug("")
    assert s == "item"


def test_slug_preserves_alphanumeric():
    s = safe_slug("abc123XYZ")
    assert s == "abc123XYZ"

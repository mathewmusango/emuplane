"""The two input shapes the analysis flagged: a response header and an email address."""

from __future__ import annotations


def test_a_header_value_cannot_carry_a_line_break(control):
    """The gateway echoes the backend's headers, so a line break there would split the response."""
    captured: list[tuple[str, str]] = []

    class Downstream:
        def send_header(self, keyword: str, value: str) -> None:
            captured.append((keyword, value))

    class Handler(control.SafeHeaders, Downstream):
        """The mixin's `super()` writes to the downstream stub."""

    Handler().send_header("X-Backend", "ok\r\nX-Injected: yes")

    assert captured == [("X-Backend", "okX-Injected: yes")]


def test_an_email_is_bounded_before_the_pattern_runs(control):
    """A long, dotless address is refused without the pattern scanning it quadratically."""
    assert control.looks_like_email("a@b.co")
    assert control.looks_like_email("first.last@sub.example.co.uk")
    assert not control.looks_like_email("a" * 5000)
    assert not control.looks_like_email("a" * 300 + "@" + "b" * 300)

import pytest

from content_factory.formatting import MAX_MESSAGE_UTF16, MessageTooLong, Span, render, utf16_len


def test_utf16_len_counts_emoji_as_two_units():
    assert len("🚀") == 1
    assert utf16_len("🚀") == 2


def test_bold_offset_after_emoji_uses_utf16_units():
    rendered = render("🚀 **Launch** day")
    assert rendered.text == "🚀 Launch day"
    assert rendered.spans == (Span("bold", 3, 6),)


def test_link_is_parsed():
    rendered = render("Read [the report](https://example.com/a) now")
    assert rendered.text == "Read the report now"
    assert rendered.spans == (Span("url", 5, 10, "https://example.com/a"),)


def test_non_http_link_stays_as_text():
    assert render("[x](javascript:alert)").spans == ()


def test_custom_emoji_finds_every_occurrence():
    rendered = render("🔥 one 🔥", {"🔥": "111"})
    assert rendered.spans == (
        Span("custom_emoji", 0, 2, "111"),
        Span("custom_emoji", 7, 2, "111"),
    )


def test_longer_emoji_wins_over_its_prefix():
    flag = "🏳️‍🌈"
    rendered = render(flag, {"🏳": "1", flag: "2"})
    assert rendered.spans == (Span("custom_emoji", 0, utf16_len(flag), "2"),)


def test_custom_emoji_inside_bold_keeps_both_spans():
    rendered = render("**a🔥b**", {"🔥": "9"})
    assert Span("bold", 0, 4) in rendered.spans
    assert Span("custom_emoji", 1, 2, "9") in rendered.spans


def test_limit_is_measured_in_utf16_units():
    render("a" * MAX_MESSAGE_UTF16)
    with pytest.raises(MessageTooLong):
        render("🚀" * (MAX_MESSAGE_UTF16 // 2 + 1))

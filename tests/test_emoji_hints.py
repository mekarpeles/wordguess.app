import pytest

from game.emoji_hints import ALL_EMOJI, EMOJI_INDEX, WORD_ID_EMOJI, annotate_hint
from game.wordbank import load_wordbank


def test_word_id_emoji_only_references_real_wordbank_ids():
    valid_ids = {w["id"] for w in load_wordbank()}
    for word_id in WORD_ID_EMOJI:
        assert word_id in valid_ids, f"{word_id!r} is not a real wordbank id"


def test_index_is_scoped_per_language_no_cross_language_leakage():
    # French "chat" (cat) must not annotate an English-language hint just
    # because "chat" happens to be a party in the French index.
    assert "chat" in EMOJI_INDEX["fr"]
    assert "chat" not in EMOJI_INDEX["en"]


def test_annotate_hint_appends_emoji_for_wordbank_word():
    result = annotate_hint("it's like an apple", "en")
    assert "apple 🍎" in result


def test_annotate_hint_appends_emoji_for_common_descriptor():
    result = annotate_hint("it's red and like an apple", "en")
    assert "red 🔴" in result
    assert "apple 🍎" in result


def test_annotate_hint_is_case_insensitive():
    result = annotate_hint("It's RED", "en")
    assert "🔴" in result


def test_annotate_hint_handles_punctuation():
    result = annotate_hint("It's an apple.", "en")
    assert "apple 🍎." in result


def test_annotate_hint_no_match_leaves_text_unchanged():
    result = annotate_hint("something totally unrelated here", "en")
    assert result == "something totally unrelated here"


def test_annotate_hint_preserves_original_text_exactly_when_emoji_stripped():
    text = "it's red and like an apple, very common"
    result = annotate_hint(text, "en")
    # every emoji-annotation should be a pure addition -- removing every
    # " <emoji>" occurrence must recover the original text exactly.
    stripped = result
    for emoji in ALL_EMOJI:
        stripped = stripped.replace(f" {emoji}", "")
    assert stripped == text


def test_annotate_hint_respects_target_language():
    fr_result = annotate_hint("c'est comme un chat", "fr")
    assert "chat 🐱" in fr_result
    en_result = annotate_hint("it's like a chat", "en")  # "chat" isn't an English word
    assert "🐱" not in en_result


def test_annotate_hint_unknown_language_returns_text_unchanged():
    assert annotate_hint("anything", "xx") == "anything"

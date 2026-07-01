import pytest

from game.errors import NoWordsAvailableError
from game.wordbank import WordBank, load_wordbank


def test_pick_word_returns_word_of_requested_level(wordbank):
    word = wordbank.pick_word(level="beginner", exclude_ids=set())
    assert word["level"] == "beginner"
    assert word["id"] in {"apple", "dog", "cat"}


def test_pick_word_excludes_recent_ids(wordbank):
    seen = set()
    for _ in range(3):
        word = wordbank.pick_word(level="beginner", exclude_ids=seen)
        assert word["id"] not in seen
        seen.add(word["id"])
    # all 3 beginner words have now been used
    assert seen == {"apple", "dog", "cat"}


def test_pick_word_raises_when_level_exhausted(wordbank):
    with pytest.raises(NoWordsAvailableError):
        wordbank.pick_word(level="beginner", exclude_ids={"apple", "dog", "cat"})


def test_pick_word_raises_for_unknown_level(wordbank):
    with pytest.raises(NoWordsAvailableError):
        wordbank.pick_word(level="expert", exclude_ids=set())


def test_load_real_wordbank_has_valid_schema():
    words = load_wordbank()
    assert len(words) >= 30
    required_langs = {"en", "fr", "es", "zh"}
    ids = set()
    for w in words:
        assert w["level"] in {"beginner", "intermediate", "advanced"}
        assert required_langs.issubset(w["translations"].keys())
        for lang, text in w["translations"].items():
            assert isinstance(text, str) and text.strip()
        assert w["id"] not in ids, f"duplicate word id {w['id']}"
        ids.add(w["id"])

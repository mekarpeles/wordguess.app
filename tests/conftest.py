import pytest

from game.wordbank import WordBank

SAMPLE_WORDS = [
    {"id": "apple", "level": "beginner", "translations": {"en": "apple", "fr": "pomme", "es": "manzana", "zh": "苹果"}},
    {"id": "dog", "level": "beginner", "translations": {"en": "dog", "fr": "chien", "es": "perro", "zh": "狗"}},
    {"id": "cat", "level": "beginner", "translations": {"en": "cat", "fr": "chat", "es": "gato", "zh": "猫"}},
    {"id": "freedom", "level": "advanced", "translations": {"en": "freedom", "fr": "liberté", "es": "libertad", "zh": "自由"}},
]


@pytest.fixture
def wordbank():
    return WordBank(SAMPLE_WORDS)

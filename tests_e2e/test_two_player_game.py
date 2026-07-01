"""
End-to-end verification of the two-player game, driven through two real
Playwright browser contexts against a running instance (Docker by default).

This is the "definition of done" check described in README.md — it exists
because passing unit/socket tests is not proof the game is actually playable
by two humans through the UI. Every assertion here reads the rendered DOM,
never calls socket.io directly.

Run against the Docker instance (must already be up):
    WORDGUESS_BASE_URL=http://localhost:5050 \
        python -m pytest tests_e2e/ -v

Or against a local `python app.py`:
    WORDGUESS_BASE_URL=http://localhost:5050 python -m pytest tests_e2e/ -v
"""

import os
import re

import pytest

from game.wordbank import load_wordbank

BASE_URL = os.environ.get("WORDGUESS_BASE_URL", "http://localhost:5050")

ALICE = {"name": "Alice", "native_lang": "en", "target_lang": "fr", "level": "beginner"}
BOB = {"name": "Bob", "native_lang": "fr", "target_lang": "en", "level": "beginner"}

# A hint the test sends regardless of which random word the round picked.
# It must never collide with any wordbank translation, or the taboo check
# will legitimately (and correctly) reject it as if it gave away the
# answer -- which showed up as test flakiness once "tree" appeared as a
# literal word in a hint that was sent during a round whose secret word
# happened to be "tree". Guarded below so future wordbank growth can't
# silently reintroduce the same flakiness.
SAFE_HINT_TEXT = "it's something common that people often think about"


def _assert_hint_is_collision_free():
    hint_words = set(re.findall(r"[a-z]+", SAFE_HINT_TEXT.lower()))
    for entry in load_wordbank():
        for translation in entry["translations"].values():
            assert translation.lower() not in hint_words, (
                f"SAFE_HINT_TEXT collides with wordbank entry {entry['id']!r} "
                f"({translation!r}) -- pick a different filler hint"
            )


_assert_hint_is_collision_free()


def fill_profile_and_submit(page, profile, code=None):
    page.goto(BASE_URL)
    page.fill("#name", profile["name"])
    page.select_option("#native-lang", profile["native_lang"])
    page.select_option("#target-lang", profile["target_lang"])
    page.select_option("#level", profile["level"])
    if code is None:
        page.click("#create-room-btn")
        page.wait_for_selector("#room-code-badge:not(:empty)")
        return page.text_content("#room-code-badge").strip()
    else:
        page.fill("#join-code", code)
        page.click("#join-room-btn")
        return code


def word_card_visible(page):
    return "hidden" not in (page.get_attribute("#word-card", "class") or "")


def wait_for_round(page_a, page_b):
    page_a.wait_for_selector("#role-banner:not(:empty)")
    page_b.wait_for_selector("#role-banner:not(:empty)")


def identify_roles(page_a, page_b):
    a_has_word = word_card_visible(page_a)
    b_has_word = word_card_visible(page_b)
    assert a_has_word != b_has_word, "exactly one player should see the secret word"
    return (page_a, page_b) if a_has_word else (page_b, page_a)


def send(page, text):
    page.fill("#chat-input", text)
    page.click("#send-btn")


@pytest.fixture
def two_pages(browser):
    ctx_a = browser.new_context()
    ctx_b = browser.new_context()
    page_a = ctx_a.new_page()
    page_b = ctx_b.new_page()

    console_errors = []

    def watch(label, page):
        page.on(
            "console",
            lambda msg: console_errors.append(f"{label}: {msg.text}") if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: console_errors.append(f"{label} pageerror: {exc}"))

    watch("A", page_a)
    watch("B", page_b)

    yield page_a, page_b, console_errors
    ctx_a.close()
    ctx_b.close()


def test_full_round_win_path_and_role_swap(two_pages):
    page_a, page_b, console_errors = two_pages

    # 1 & 2: player A creates a room and sees a code rendered in the DOM
    code = fill_profile_and_submit(page_a, ALICE)
    assert re.match(r"^[A-Z]{4}$", code)

    # 3: player B joins with that code
    fill_profile_and_submit(page_b, BOB, code=code)

    # 4: both transition to the game view automatically (no reload issued)
    wait_for_round(page_a, page_b)
    assert "hidden" not in (page_a.get_attribute("#game", "class") or "")
    assert "hidden" not in (page_b.get_attribute("#game", "class") or "")

    # 5: exactly one DOM shows the secret word
    prompter, guesser = identify_roles(page_a, page_b)
    secret = prompter.text_content("#secret-word").strip()
    assert secret
    # the secret word must never appear anywhere in the guesser's page
    assert secret not in guesser.content()

    # 6: prompter tries to use the secret word itself -> rejected, not broadcast
    send(prompter, f"it sounds a lot like {secret}")
    prompter.wait_for_selector(".msg.rejected")
    assert secret not in (guesser.text_content("#chat-log") or "")

    # 7: prompter sends a valid hint -> appears in guesser's chat in real time
    send(prompter, SAFE_HINT_TEXT)
    guesser.wait_for_selector(f"#chat-log >> text={SAFE_HINT_TEXT}")

    # 8: guesser sends a wrong guess -> both see it, remaining count decrements
    send(guesser, "definitely-wrong-guess")
    prompter.wait_for_selector("#chat-log >> text=definitely-wrong-guess")
    guesser.wait_for_function(
        "document.querySelector('#guesses-remaining-guesser').textContent.includes('9')"
    )

    # 9: guesser sends the correct answer -> round-result + scoreboard update, both sides
    from game.wordbank import load_wordbank

    words = load_wordbank()
    match = next(w for w in words if w["translations"][prompter_lang(secret, words)] == secret)
    guesser_native = ALICE["native_lang"] if guesser is page_a else BOB["native_lang"]
    answer = match["translations"][guesser_native]

    send(guesser, answer)
    guesser.wait_for_selector(".msg.system.win")
    prompter.wait_for_selector(".msg.system.win")

    guesser_score_text = guesser.text_content("#scoreboard")
    prompter_score_text = prompter.text_content("#scoreboard")
    # one wrong guess was already made above, so the correct guess is the
    # 2nd attempt -> SCORE_TABLE[1] == 9 points, not the max of 10
    assert "9" in guesser_score_text
    assert "You" in guesser_score_text
    assert prompter_score_text  # opponent's board also updated

    # 10: roles visibly swap for round 2 (re-read DOM, don't assume)
    wait_for_round(page_a, page_b)
    new_prompter, new_guesser = identify_roles(page_a, page_b)
    assert new_prompter is guesser, "the player who just guessed correctly should now be prompting"
    assert new_guesser is prompter, "the previous prompter should now be guessing"

    # 12: no unhandled console/page errors during the whole sequence
    assert console_errors == [], f"unexpected console/page errors: {console_errors}"


def prompter_lang(secret_word, words):
    for w in words:
        for lang, text in w["translations"].items():
            if text == secret_word:
                return lang
    raise AssertionError(f"secret word {secret_word!r} not found in word bank")


def test_ten_failed_guesses_reveals_word_and_swaps_roles(two_pages):
    page_a, page_b, console_errors = two_pages

    code = fill_profile_and_submit(page_a, ALICE)
    fill_profile_and_submit(page_b, BOB, code=code)
    wait_for_round(page_a, page_b)

    prompter, guesser = identify_roles(page_a, page_b)

    for i in range(10):
        send(guesser, f"wrong-guess-{i}")
        guesser.wait_for_timeout(50)

    guesser.wait_for_selector(".msg.system.lose")
    prompter.wait_for_selector(".msg.system.lose")

    # roles still swap after a loss
    wait_for_round(page_a, page_b)
    new_prompter, _new_guesser = identify_roles(page_a, page_b)
    assert new_prompter is guesser, "roles must swap even when the guesser loses the round"

    assert console_errors == [], f"unexpected console/page errors: {console_errors}"

"""
End-to-end verification for the second feature batch (timer, difficulty
flag, and language-matched game browsing), driven through real Playwright
browser contexts against a running instance, same standard as
test_two_player_game.py.
"""

import os

import pytest

from tests_e2e.test_two_player_game import (
    ALICE,
    BOB,
    fill_profile_and_submit,
    identify_roles,
    send,
    two_pages,
    wait_for_round,
)

BASE_URL = os.environ.get("WORDGUESS_BASE_URL", "http://localhost:5050")

# The other e2e tests (win path, loss path, etc.) run several sequential
# network round-trips per round and need the real (or near-real) round
# time limit so they don't get spuriously cut off by a timeout mid-test.
# The timer test itself needs a short limit or it has to wait out a real
# 2 minutes. These requirements conflict for a single shared server
# instance, so: run the general e2e suite against the default 120s limit,
# and run this one test separately against an instance started with a
# short override, matching the same value in both places, e.g.:
#   ROUND_TIME_LIMIT_SECONDS=5 docker compose -p wordguess-timer up -d --build web
#   ROUND_TIME_LIMIT_SECONDS=5 WORDGUESS_BASE_URL=http://localhost:5050 \
#       python -m pytest tests_e2e/test_new_features.py::test_round_timer_counts_down_and_times_out -v
_ROUND_TIME_LIMIT_SECONDS = int(os.environ.get("ROUND_TIME_LIMIT_SECONDS", 120))


def test_flag_difficult_message_visible_to_both_and_button_role_scoped(two_pages):
    page_a, page_b, console_errors = two_pages
    fill_profile_and_submit(page_a, ALICE)
    code = page_a.text_content("#room-code-badge").strip()
    fill_profile_and_submit(page_b, BOB, code=code)
    wait_for_round(page_a, page_b)

    prompter, guesser = identify_roles(page_a, page_b)

    assert not prompter.is_visible("#flag-difficult-btn")
    assert guesser.is_visible("#flag-difficult-btn")

    guesser.click("#flag-difficult-btn")
    guesser.wait_for_selector("#chat-log >> text=too hard")
    prompter.wait_for_selector("#chat-log >> text=too hard")

    # client-side debounce disables the button briefly after a click
    assert guesser.is_disabled("#flag-difficult-btn")

    assert console_errors == []


def test_hint_with_recognized_word_gets_emoji_annotation_live(two_pages):
    page_a, page_b, console_errors = two_pages
    fill_profile_and_submit(page_a, ALICE)
    code = page_a.text_content("#room-code-badge").strip()
    fill_profile_and_submit(page_b, BOB, code=code)
    wait_for_round(page_a, page_b)

    prompter, guesser = identify_roles(page_a, page_b)
    hint_text = "it's red and common" if prompter is page_a else "c'est rouge et commun"

    send(prompter, hint_text)
    guesser.wait_for_selector("#chat-log >> text=🔴")

    assert console_errors == []


@pytest.mark.skipif(
    _ROUND_TIME_LIMIT_SECONDS > 30,
    reason=(
        "run separately against an instance started with a short "
        "ROUND_TIME_LIMIT_SECONDS override (see module docstring above) -- "
        "against the default 120s limit this test would have to wait out a "
        "real 2 minutes. The reverse is also true: don't lower the server's "
        "limit for a full test_e2e/ run just to make this one test fast -- "
        "the other multi-step tests would then risk racing against that "
        "same short timeout mid-round."
    ),
)
def test_round_timer_counts_down_and_times_out(two_pages):
    page_a, page_b, console_errors = two_pages
    fill_profile_and_submit(page_a, ALICE)
    code = page_a.text_content("#room-code-badge").strip()
    fill_profile_and_submit(page_b, BOB, code=code)
    wait_for_round(page_a, page_b)

    initial_timer_text = page_a.text_content("#round-timer")
    assert "⏱" in initial_timer_text

    prompter, guesser = identify_roles(page_a, page_b)
    # Do nothing and let the round time out.
    guesser.wait_for_selector(".msg.system.lose", timeout=15000)
    assert "Time's up" in guesser.text_content("#chat-log")

    # Roles should still swap after a timeout, same as a 10-guess loss.
    wait_for_round(page_a, page_b)
    new_prompter, _new_guesser = identify_roles(page_a, page_b)
    assert new_prompter is guesser

    assert console_errors == []


def test_open_games_list_filters_by_strict_mutual_language_match(browser):
    ctx_a = browser.new_context()
    ctx_b = browser.new_context()
    ctx_c = browser.new_context()
    page_a, page_b, page_c = ctx_a.new_page(), ctx_b.new_page(), ctx_c.new_page()
    try:
        # Alice creates a room and waits.
        code = fill_profile_and_submit(page_a, ALICE)

        # Carol has mismatched languages -- should see no games.
        carol = {"name": "Carol", "native_lang": "es", "target_lang": "zh", "level": "beginner"}
        page_c.goto(BASE_URL)
        page_c.fill("#name", carol["name"])
        page_c.select_option("#native-lang", carol["native_lang"])
        page_c.select_option("#target-lang", carol["target_lang"])
        page_c.select_option("#level", carol["level"])
        page_c.click("#find-match-btn")
        page_c.wait_for_selector("#open-games-list .no-games-message, #open-games-list .game-row")
        assert "Alice" not in page_c.text_content("#open-games-list")

        # Bob is Alice's mirror (native fr / target en) -- should see her game.
        page_b.goto(BASE_URL)
        page_b.fill("#name", BOB["name"])
        page_b.select_option("#native-lang", BOB["native_lang"])
        page_b.select_option("#target-lang", BOB["target_lang"])
        page_b.select_option("#level", BOB["level"])
        page_b.click("#find-match-btn")
        page_b.wait_for_selector("#open-games-list .game-row")
        assert "Alice" in page_b.text_content("#open-games-list")

        page_b.click("#open-games-list .game-row button")
        wait_for_round(page_a, page_b)
        assert code  # sanity: room existed and was joinable via the list
    finally:
        ctx_a.close()
        ctx_b.close()
        ctx_c.close()

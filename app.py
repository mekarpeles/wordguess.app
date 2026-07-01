import logging
import os

from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room as sio_join_room

from game.emoji_hints import annotate_hint
from game.engine import MAX_GUESSES, ROUND_TIME_LIMIT_SECONDS, Player
from game.errors import (
    NoActiveRoundError,
    NotYourTurnError,
    RoomFullError,
    TabooViolationError,
)
from game.rooms import RoomRegistry

REQUIRED_PROFILE_FIELDS = ("native_lang", "target_lang")

logger = logging.getLogger("wordguess")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret")
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

    registry = RoomRegistry()
    sid_to_room_code: dict[str, str] = {}

    def _scores_payload(room):
        return {sid: {"name": p.name, "score": p.score} for sid, p in room.players.items()}

    def _players_payload(room):
        return [
            {"sid": p.sid, "name": p.name, "native_lang": p.native_lang, "target_lang": p.target_lang}
            for p in room.players.values()
        ]

    def _broadcast_round_started(room):
        round_ = room.round
        guesser = room.players[round_.guesser_sid]
        prompter = room.players[round_.prompter_sid]
        base = {
            "target_lang": round_.target_lang,
            "guesses_remaining": MAX_GUESSES,
            "time_limit_seconds": ROUND_TIME_LIMIT_SECONDS,
            "scores": _scores_payload(room),
        }
        socketio.emit(
            "round_started",
            {**base, "role": "guesser", "guesser_native_lang": guesser.native_lang},
            to=guesser.sid,
        )
        socketio.emit(
            "round_started",
            {**base, "role": "prompter", "secret_word": round_.word["translations"][round_.target_lang]},
            to=prompter.sid,
        )
        _schedule_round_timeout(room)

    def _schedule_round_timeout(room):
        round_ = room.round

        def watch():
            socketio.sleep(ROUND_TIME_LIMIT_SECONDS)
            if room.round is not round_:
                return  # round already ended for another reason
            result = room.expire_round_if_timed_out()
            if result is None:
                return
            logger.info("room=%s round TIMED OUT word_id=%s", room.code, result["word"]["id"])
            _finish_round_and_advance(room, result, winner_name=None)

        socketio.start_background_task(watch)

    def _finish_round_and_advance(room, result, winner_name):
        socketio.emit(
            "round_result",
            {
                "correct": result["correct"],
                "winner_name": winner_name,
                "score_awarded": result.get("score", 0),
                "revealed_word": result["word"]["translations"],
                "scores": _scores_payload(room),
                "timed_out": result.get("timed_out", False),
            },
            to=room.code,
        )
        if len(room.players) < 2:
            # The opponent disconnected between the last action and this
            # round ending (a real race: guess submitted right as the other
            # player leaves, or the round-timeout timer firing after a
            # disconnect). Nothing to advance to -- the remaining player
            # already got "opponent_left" from the disconnect handler.
            return
        next_round = room.next_round()
        logger.info(
            "room=%s round_started word_id=%s target_lang=%s guesser=%r prompter=%r",
            room.code, next_round.word["id"], next_round.target_lang,
            room.players[next_round.guesser_sid].name, room.players[next_round.prompter_sid].name,
        )
        _broadcast_round_started(room)

    def _add_player_and_reply(room, data):
        for field in REQUIRED_PROFILE_FIELDS:
            if not data.get(field):
                socketio.emit("error", {"message": f"missing required field: {field}"}, to=request.sid)
                return
        player = Player(
            sid=request.sid,
            name=(data.get("name") or "Player").strip()[:40],
            native_lang=data["native_lang"],
            target_lang=data["target_lang"],
            level=data.get("level", "beginner"),
        )
        room.add_player(player)
        sid_to_room_code[request.sid] = room.code
        sio_join_room(room.code)
        logger.info(
            "room=%s joined name=%r native=%s target=%s level=%s (%d/2)",
            room.code, player.name, player.native_lang, player.target_lang, player.level, len(room.players),
        )
        socketio.emit(
            "joined",
            {"code": room.code, "sid": request.sid, "players": _players_payload(room)},
            to=room.code,
        )
        if len(room.players) == 2:
            round_ = room.start_round()
            logger.info(
                "room=%s round_started word_id=%s target_lang=%s guesser=%r prompter=%r",
                room.code, round_.word["id"], round_.target_lang,
                room.players[round_.guesser_sid].name, room.players[round_.prompter_sid].name,
            )
            _broadcast_round_started(room)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/room/<code>")
    def room_page(code):
        # Shares the same single-page app as "/"; prefills the join-code
        # field so a shared room link drops the second player straight into
        # the join form instead of making them retype the code.
        return render_template("index.html", prefill_code=code.upper())

    @socketio.on("create_room")
    def handle_create_room(data):
        room = registry.create()
        _add_player_and_reply(room, data)

    @socketio.on("join_room")
    def handle_join_room(data):
        room = registry.get(data.get("code", ""))
        if room is None:
            socketio.emit("error", {"message": f"Room {data.get('code', '')} not found"}, to=request.sid)
            return
        try:
            _add_player_and_reply(room, data)
        except RoomFullError:
            socketio.emit("error", {"message": f"Room {room.code} is already full"}, to=request.sid)

    @socketio.on("list_open_games")
    def handle_list_open_games(data):
        native_lang = data.get("native_lang", "")
        target_lang = data.get("target_lang", "")
        if not native_lang or not target_lang:
            socketio.emit("error", {"message": "native_lang and target_lang are required"}, to=request.sid)
            return
        matches = registry.list_open(native_lang=native_lang, target_lang=target_lang)
        socketio.emit("open_games", {"games": matches}, to=request.sid)

    @socketio.on("send_hint")
    def handle_send_hint(data):
        room = registry.get(sid_to_room_code.get(request.sid, ""))
        if room is None:
            return
        text = (data.get("text") or "").strip()
        if not text:
            return
        try:
            hint = room.submit_hint(request.sid, text)
        except TabooViolationError as e:
            logger.info("room=%s hint REJECTED text=%r reason=%s", room.code, text, e)
            socketio.emit("hint_rejected", {"message": str(e)}, to=request.sid)
            return
        except (NotYourTurnError, NoActiveRoundError) as e:
            socketio.emit("error", {"message": str(e)}, to=request.sid)
            return
        sender = room.players[request.sid]
        logger.info("room=%s hint from=%r text=%r", room.code, sender.name, text)
        display_text = annotate_hint(hint["text"], room.round.target_lang)
        socketio.emit("hint", {"text": display_text, "from_sid": request.sid, "from_name": sender.name}, to=room.code)

    @socketio.on("flag_difficult")
    def handle_flag_difficult(_data=None):
        room = registry.get(sid_to_room_code.get(request.sid, ""))
        if room is None:
            return
        try:
            room.flag_difficult(request.sid)
        except (NotYourTurnError, NoActiveRoundError) as e:
            socketio.emit("error", {"message": str(e)}, to=request.sid)
            return
        sender = room.players[request.sid]
        logger.info("room=%s difficulty flagged by=%r", room.code, sender.name)
        socketio.emit("difficulty_flagged", {"from_name": sender.name}, to=room.code)

    @socketio.on("send_guess")
    def handle_send_guess(data):
        room = registry.get(sid_to_room_code.get(request.sid, ""))
        if room is None:
            return
        text = (data.get("text") or "").strip()
        if not text:
            return
        try:
            result = room.submit_guess(request.sid, text)
        except (NotYourTurnError, NoActiveRoundError) as e:
            socketio.emit("error", {"message": str(e)}, to=request.sid)
            return
        sender = room.players[request.sid]
        logger.info(
            "room=%s guess from=%r text=%r correct=%s lost=%s wrong_language=%s",
            room.code, sender.name, text, result["correct"], result.get("lost", False),
            result.get("wrong_language", False),
        )
        socketio.emit("guess", {"text": text, "from_sid": request.sid, "from_name": sender.name}, to=room.code)

        if result["correct"] or result["lost"]:
            _finish_round_and_advance(room, result, winner_name=sender.name if result["correct"] else None)
        else:
            socketio.emit(
                "guess_result",
                {
                    "correct": False,
                    "remaining": result["remaining"],
                    "wrong_language": result["wrong_language"],
                },
                to=room.code,
            )

    @socketio.on("disconnect")
    def handle_disconnect():
        code = sid_to_room_code.pop(request.sid, None)
        if not code:
            return
        room = registry.get(code)
        if room is None:
            return
        player = room.players.pop(request.sid, None)
        room.player_order = [sid for sid in room.player_order if sid in room.players]
        logger.info("room=%s disconnected name=%r", code, player.name if player else request.sid)
        if room.players:
            socketio.emit("opponent_left", {}, to=code)
        else:
            registry.remove(code)

    return app, socketio


app, socketio = create_app()

if __name__ == "__main__":
    debug = bool(os.environ.get("FLASK_DEBUG", False))
    # Default port 5000 collides with macOS AirPlay Receiver on many Macs
    # (returns 403 instead of failing loudly) -- default to 5050 instead.
    port = int(os.environ.get("PORT", 5050))
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True)

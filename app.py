import logging
import os

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room as sio_join_room

from game.engine import MAX_GUESSES, Player
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
            "scores": _scores_payload(room),
        }
        emit(
            "round_started",
            {**base, "role": "guesser", "guesser_native_lang": guesser.native_lang},
            to=guesser.sid,
        )
        emit(
            "round_started",
            {**base, "role": "prompter", "secret_word": round_.word["translations"][round_.target_lang]},
            to=prompter.sid,
        )

    def _add_player_and_reply(room, data):
        for field in REQUIRED_PROFILE_FIELDS:
            if not data.get(field):
                emit("error", {"message": f"missing required field: {field}"})
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
        emit(
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
            emit("error", {"message": f"Room {data.get('code', '')} not found"})
            return
        try:
            _add_player_and_reply(room, data)
        except RoomFullError:
            emit("error", {"message": f"Room {room.code} is already full"})

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
            emit("hint_rejected", {"message": str(e)})
            return
        except (NotYourTurnError, NoActiveRoundError) as e:
            emit("error", {"message": str(e)})
            return
        sender = room.players[request.sid]
        logger.info("room=%s hint from=%r text=%r", room.code, sender.name, text)
        emit("hint", {"text": hint["text"], "from_sid": request.sid, "from_name": sender.name}, to=room.code)

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
            emit("error", {"message": str(e)})
            return
        sender = room.players[request.sid]
        logger.info(
            "room=%s guess from=%r text=%r correct=%s lost=%s wrong_language=%s",
            room.code, sender.name, text, result["correct"], result.get("lost", False),
            result.get("wrong_language", False),
        )
        emit("guess", {"text": text, "from_sid": request.sid, "from_name": sender.name}, to=room.code)

        if result["correct"] or result["lost"]:
            emit(
                "round_result",
                {
                    "correct": result["correct"],
                    "winner_name": sender.name if result["correct"] else None,
                    "score_awarded": result.get("score", 0),
                    "revealed_word": result["word"]["translations"],
                    "scores": _scores_payload(room),
                },
                to=room.code,
            )
            next_round = room.next_round()
            logger.info(
                "room=%s round_started word_id=%s target_lang=%s guesser=%r prompter=%r",
                room.code, next_round.word["id"], next_round.target_lang,
                room.players[next_round.guesser_sid].name, room.players[next_round.prompter_sid].name,
            )
            _broadcast_round_started(room)
        else:
            emit(
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
            emit("opponent_left", {}, to=code)
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

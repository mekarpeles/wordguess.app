import random
import string

from game.engine import Room

CODE_ALPHABET = string.ascii_uppercase
CODE_LENGTH = 4


class RoomRegistry:
    def __init__(self):
        self._rooms: dict[str, Room] = {}

    def create(self) -> Room:
        code = self._new_code()
        room = Room(code=code)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get((code or "").strip().upper())

    def remove(self, code: str) -> None:
        self._rooms.pop(code, None)

    def _new_code(self) -> str:
        while True:
            code = "".join(random.choices(CODE_ALPHABET, k=CODE_LENGTH))
            if code not in self._rooms:
                return code

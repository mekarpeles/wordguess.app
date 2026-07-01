class GameError(Exception):
    """Base class for all game-logic errors."""


class RoomFullError(GameError):
    pass


class RoomNotReadyError(GameError):
    pass


class NoActiveRoundError(GameError):
    pass


class NotYourTurnError(GameError):
    pass


class TabooViolationError(GameError):
    pass


class NoWordsAvailableError(GameError):
    pass

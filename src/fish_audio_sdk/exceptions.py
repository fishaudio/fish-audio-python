from dataclasses import dataclass


@dataclass(init=False)
class HttpCodeErr(Exception):
    status: int
    message: str

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"{status} {message}")


class WebSocketErr(Exception):
    """
    {"event": "finish", "reason": "error"} or WebSocketDisconnect
    """

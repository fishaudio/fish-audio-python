from dataclasses import dataclass


@dataclass
class HttpCodeErr(Exception):
    status: int
    message: str

"""Namespace resource clients."""

from .account import AccountClient, AsyncAccountClient
from .asr import ASRClient, AsyncASRClient
from .tts import AsyncTTSClient, TTSClient
from .voices import AsyncVoicesClient, VoicesClient

__all__ = [
    # Sync clients
    "AccountClient",
    "ASRClient",
    "TTSClient",
    "VoicesClient",
    # Async clients
    "AsyncAccountClient",
    "AsyncASRClient",
    "AsyncTTSClient",
    "AsyncVoicesClient",
]

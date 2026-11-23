"""Types for realtime speech-to-text (``/v1/asr/realtime``)."""

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict

ASRSampleRate = Literal[8000, 12000, 16000, 22050, 24000, 32000, 44100, 48000]
TurnDetectionMode = Literal["auto", "vad", "manual"]


# Session configuration


class ASRTurnDetection(BaseModel):
    """How the server decides that a turn has ended.

    Fields left as None are not sent: the server uses its default at session
    start, and keeps the current value in a mid-session ``configure``.

    Attributes:
        mode: "auto" (default): the server judges when the user has finished and tells
            user turns from noise and other voices. "vad": a turn ends after
            silence_timeout_ms of silence. "manual": a turn ends when you send finalize
        eager: Send eager_end_of_turn events (auto mode only). Server default: False
        silence_timeout_ms: Silence that ends a turn. auto: default 5000, allowed
            3000-60000. vad: default 700, allowed 300-60000. manual: default 60000,
            allowed 300-60000
    """

    mode: Optional[TurnDetectionMode] = None
    eager: Optional[bool] = None
    silence_timeout_ms: Optional[int] = None


class ASRResults(BaseModel):
    """Which results the server sends, and what the transcript text contains.

    Fields left as None are not sent: the server uses its default at session
    start, and keeps the current value in a mid-session ``configure``.

    Attributes:
        drafts: Send live draft events. Server default: False
        ignore_timestamps: False adds word timings to committed events. Server default: True
        diarize: Speaker tags such as ``<|speaker:0|>`` in the text. Server default: True
        tag_audio_events: Sound tags such as ``[laughter]`` in the text. Server default: True
        vad_events: Send vad events (voice activity, up to 10 per second). Server default: False
        eot_events: Send eot_prob events (end-of-turn likelihood). Server default: False
    """

    drafts: Optional[bool] = None
    ignore_timestamps: Optional[bool] = None
    diarize: Optional[bool] = None
    tag_audio_events: Optional[bool] = None
    vad_events: Optional[bool] = None
    eot_events: Optional[bool] = None


class ASRContextItem(BaseModel):
    """One line of conversation given to the server as context.

    Attributes:
        role: Who said it: "user" or "assistant"
        text: What was said (up to 2000 characters)
    """

    role: Literal["user", "assistant"]
    text: str


class ASRContext(BaseModel):
    """Conversation context that helps the server recognize names and follow-ups.

    Attributes:
        history: Earlier conversation, oldest first (up to 32 items). Only accepted
            at session start; add lines later with context_add
        terms: Names, products and jargon to recognize (up to 100 terms of up to
            32 characters)
    """

    history: Optional[list[ASRContextItem]] = None
    terms: Optional[list[str]] = None


class ASRRealtimeConfig(BaseModel):
    """Configuration for a realtime speech-to-text session.

    Attributes:
        sample_rate: Sample rate of the audio you send, in Hz. The server converts
            other rates to 16000, so you never need to resample. Default: 16000
        turn_detection: Turn detection settings. Default: None (server defaults)
        results: Result settings. Default: None (server defaults)
        context: Conversation history and custom vocabulary. Default: None
        client_reference_id: Your own ID for the session (up to 256 characters).
            Recorded with the session; not sent back. Default: None
    """

    sample_rate: ASRSampleRate = 16000
    turn_detection: Optional[ASRTurnDetection] = None
    results: Optional[ASRResults] = None
    context: Optional[ASRContext] = None
    client_reference_id: Optional[str] = None


# Control messages you can send during a session


class ASRFinalizeEvent(BaseModel):
    """Commit the current turn now (push-to-talk: the button was released).

    Attributes:
        type: Message type identifier, always "finalize"
    """

    type: Literal["finalize"] = "finalize"


class ASRAgentSpeakingEvent(BaseModel):
    """Tell the server whether your voice agent is speaking (auto mode).

    While the agent speaks, a short acknowledgement from the user produces
    user_backchannel instead of user_turn_taken.

    Attributes:
        type: Message type identifier, always "agent_speaking"
        speaking: True when you commit to playing a reply; False when its last
            sample has played or you stop it
    """

    type: Literal["agent_speaking"] = "agent_speaking"
    speaking: bool


class ASRContextAddEvent(BaseModel):
    """Add conversation context, typically each line your agent speaks.

    Attributes:
        type: Message type identifier, always "context_add"
        items: Conversation items, oldest first (up to 32)
        reset_history: First drop the items you added before. Default: False
    """

    type: Literal["context_add"] = "context_add"
    items: list[ASRContextItem]
    reset_history: bool = False


class ASRConfigureEvent(BaseModel):
    """Change settings during the session. Answered by a configured event.

    Attributes:
        type: Message type identifier, always "configure"
        turn_detection: Turn detection changes; omitted fields keep their values
        results: Result changes; omitted fields keep their values
        context: Only ``terms`` is accepted here; it replaces the list of terms
    """

    type: Literal["configure"] = "configure"
    turn_detection: Optional[ASRTurnDetection] = None
    results: Optional[ASRResults] = None
    context: Optional[ASRContext] = None


class ASRKeepaliveEvent(BaseModel):
    """Keep an idle session open.

    Rarely needed: the SDK's WebSocket pings already count as client activity.

    Attributes:
        type: Message type identifier, always "keepalive"
    """

    type: Literal["keepalive"] = "keepalive"


ASRRealtimeControl = Union[
    ASRFinalizeEvent,
    ASRAgentSpeakingEvent,
    ASRContextAddEvent,
    ASRConfigureEvent,
    ASRKeepaliveEvent,
]


# Events the server sends


class _ServerEvent(BaseModel):
    # The protocol only ever adds fields, so keep the ones this SDK version does
    # not know yet reachable as attributes instead of dropping them.
    model_config = ConfigDict(extra="allow")

    seq: Optional[int] = None


class ASRWord(BaseModel):
    """A word of a committed transcript with its position in the audio.

    Attributes:
        text: The word
        start_ms: Where the word starts, in milliseconds of session audio
        end_ms: Where the word ends, in milliseconds of session audio
    """

    text: str
    start_ms: int
    end_ms: int


class ASRSessionStartedEvent(_ServerEvent):
    """The session is ready; audio is sent after this event.

    Attributes:
        type: Event type identifier, always "session_started"
        seq: Sequence number, increasing by one per server message
        session_id: The session's ID
        request_id: Identifier of this request; quote it when reporting a problem
        config: The configuration in effect, with defaults filled in
        limits: Session limits (max_session_ms, max_turn_ms, max_frame_bytes)
    """

    type: Literal["session_started"] = "session_started"
    session_id: str
    request_id: Optional[str] = None
    config: dict[str, Any] = {}
    limits: dict[str, Any] = {}


class ASRSpeechStartEvent(_ServerEvent):
    """A turn opened on voice activity.

    In auto mode noise and other voices open turns too: wait for
    user_turn_taken before treating it as the user's turn.

    Attributes:
        type: Event type identifier, always "speech_start"
        seq: Sequence number
        turn_index: The turn that opened, counting from 0
        audio_ms: Where the turn starts, slightly before the speech
    """

    type: Literal["speech_start"] = "speech_start"
    turn_index: int
    audio_ms: Optional[int] = None


class ASRUserTurnTakenEvent(_ServerEvent):
    """Auto mode: the server judged that the user is taking their turn.

    For a voice agent that is speaking, this is the signal to stop (barge-in).

    Attributes:
        type: Event type identifier, always "user_turn_taken"
        seq: Sequence number
        turn_index: The turn the user took
        audio_ms: Where the server judged that the user took the turn
    """

    type: Literal["user_turn_taken"] = "user_turn_taken"
    turn_index: int
    audio_ms: Optional[int] = None


class ASRDraftEvent(_ServerEvent):
    """Live draft of the open turn (with ``drafts=True``). Not final.

    Attributes:
        type: Event type identifier, always "draft"
        seq: Sequence number
        turn_index: The open turn
        text: The whole turn so far. Replaces the previous draft
        settled_text: The beginning of text that the server is confident will not
            change. Often empty
        language: English name of the detected language. None if not identified
        language_code: ISO 639-1 code of the detected language. None if not identified
        audio_ms: The audio position the draft covers up to
        audio_received_ms: Audio received so far
        audio_processed_ms: Audio processed so far
        audio_committed_ms: Audio covered by committed turns so far
    """

    type: Literal["draft"] = "draft"
    turn_index: int
    text: str
    settled_text: str = ""
    language: Optional[str] = None
    language_code: Optional[str] = None
    audio_ms: Optional[int] = None
    audio_received_ms: Optional[int] = None
    audio_processed_ms: Optional[int] = None
    audio_committed_ms: Optional[int] = None


class ASREagerEndOfTurnEvent(_ServerEvent):
    """The turn has probably ended (auto mode with ``eager=True``).

    Start preparing your response; a turn_resumed event cancels it.

    Attributes:
        type: Event type identifier, always "eager_end_of_turn"
        seq: Sequence number
        turn_index: The turn that probably ended
        text: Exactly what committed will say unless turn_resumed follows. Can be empty
        language: English name of the detected language. None if not identified
        language_code: ISO 639-1 code of the detected language. None if not identified
        audio_ms: The audio position of the signal
    """

    type: Literal["eager_end_of_turn"] = "eager_end_of_turn"
    turn_index: int
    text: str
    language: Optional[str] = None
    language_code: Optional[str] = None
    audio_ms: Optional[int] = None


class ASRTurnResumedEvent(_ServerEvent):
    """The speaker went on after eager_end_of_turn: discard that text.

    Attributes:
        type: Event type identifier, always "turn_resumed"
        seq: Sequence number
        turn_index: The turn that resumed
    """

    type: Literal["turn_resumed"] = "turn_resumed"
    turn_index: int


class ASRUserBackchannelEvent(_ServerEvent):
    """Auto mode, while your agent speaks: the user only acknowledged ("mm-hm").

    Attributes:
        type: Event type identifier, always "user_backchannel"
        seq: Sequence number
        turn_index: The open turn, or the index the next turn will get
        audio_ms: Where the acknowledgement is in the audio
    """

    type: Literal["user_backchannel"] = "user_backchannel"
    turn_index: int
    audio_ms: Optional[int] = None


class ASRCommittedEvent(_ServerEvent):
    """The final transcript of a turn. Every turn has exactly one.

    Attributes:
        type: Event type identifier, always "committed"
        seq: Sequence number
        turn_index: The turn that ended
        text: The final transcript. Can contain speaker tags such as ``<|speaker:0|>``
            and sound tags such as ``[laughter]``. Can be empty
        words: Word timings. Only with ``ignore_timestamps=False``; None otherwise
        language: English name of the detected language. None if not identified
        language_code: ISO 639-1 code of the detected language. None if not identified
        audio_start_ms: Where the turn starts in the session audio
        audio_end_ms: Where the turn ends in the session audio
        reason: Why the turn ended: "eot", "finalize", "silence_timeout",
            "max_turn_duration" or "audio_done". Treat an unknown value like "eot"
        degraded: True when the final pass failed and the text comes from the last draft
        user_turn: True for the user's turn. Decide whether to answer by this field
        turn_kind: "user", "backchannel" or "other"
        audio_received_ms: Audio received so far
        audio_processed_ms: Audio processed so far
        audio_committed_ms: Audio covered by committed turns so far
    """

    type: Literal["committed"] = "committed"
    turn_index: int
    text: str
    words: Optional[list[ASRWord]] = None
    language: Optional[str] = None
    language_code: Optional[str] = None
    audio_start_ms: Optional[int] = None
    audio_end_ms: Optional[int] = None
    reason: str = "eot"
    degraded: bool = False
    user_turn: bool = True
    turn_kind: Optional[str] = None
    audio_received_ms: Optional[int] = None
    audio_processed_ms: Optional[int] = None
    audio_committed_ms: Optional[int] = None


class ASRVadEvent(_ServerEvent):
    """Voice activity (with ``vad_events=True``), up to 10 per second.

    Attributes:
        type: Event type identifier, always "vad"
        seq: Sequence number
        audio_ms: The audio position of the score
        score: Voice activity, from 0 to 1
    """

    type: Literal["vad"] = "vad"
    audio_ms: Optional[int] = None
    score: float


class ASREotProbEvent(_ServerEvent):
    """End-of-turn likelihood for display (with ``eot_events=True``).

    Attributes:
        type: Event type identifier, always "eot_prob"
        seq: Sequence number
        turn_index: The open turn
        audio_ms: The audio position of the estimate
        prob: End-of-turn likelihood, from 0 to 1
    """

    type: Literal["eot_prob"] = "eot_prob"
    turn_index: Optional[int] = None
    audio_ms: Optional[int] = None
    prob: float


class ASRConfiguredEvent(_ServerEvent):
    """The reply to a configure message.

    Attributes:
        type: Event type identifier, always "configured"
        seq: Sequence number
        ok: False means nothing changed
        config: The configuration in effect
        message: Why the change was refused, in English. None when ok is True
    """

    type: Literal["configured"] = "configured"
    ok: bool
    config: dict[str, Any] = {}
    message: Optional[str] = None


class ASRProgressEvent(_ServerEvent):
    """Audio watermarks, sent every 5 seconds while the client sends nothing.

    Attributes:
        type: Event type identifier, always "progress"
        seq: Sequence number
        audio_received_ms: Audio received so far
        audio_processed_ms: Audio processed so far
        audio_committed_ms: Audio covered by committed turns so far
    """

    type: Literal["progress"] = "progress"
    audio_received_ms: Optional[int] = None
    audio_processed_ms: Optional[int] = None
    audio_committed_ms: Optional[int] = None


class ASRErrorEvent(_ServerEvent):
    """A recoverable error: the session continues.

    Errors that end the session are raised as ASRRealtimeError instead.

    Attributes:
        type: Event type identifier, always "error"
        seq: Sequence number
        code: HTTP-style status
        error_type: Machine-readable error type, e.g. "invalid_request". Match on this
        message: A short English description, for humans
        request_id: Identifier of this request; quote it when reporting a problem
        recoverable: True when the session continues
    """

    type: Literal["error"] = "error"
    code: Optional[int] = None
    error_type: str
    message: str = ""
    request_id: Optional[str] = None
    recoverable: bool = False


class ASRSessionStats(BaseModel):
    """Totals for a finished session.

    Attributes:
        audio_ms: Audio received in the session
        turns: Every committed turn, user turn or not
        request_id: Identifier of this request
    """

    model_config = ConfigDict(extra="allow")

    audio_ms: Optional[int] = None
    turns: Optional[int] = None
    request_id: Optional[str] = None


class ASRSessionDoneEvent(_ServerEvent):
    """The session ended normally. Always the last event.

    Attributes:
        type: Event type identifier, always "session_done"
        seq: Sequence number
        stats: Totals for the session
    """

    type: Literal["session_done"] = "session_done"
    stats: ASRSessionStats = ASRSessionStats()


ASRRealtimeEvent = Union[
    ASRSessionStartedEvent,
    ASRSpeechStartEvent,
    ASRUserTurnTakenEvent,
    ASRDraftEvent,
    ASREagerEndOfTurnEvent,
    ASRTurnResumedEvent,
    ASRUserBackchannelEvent,
    ASRCommittedEvent,
    ASRVadEvent,
    ASREotProbEvent,
    ASRConfiguredEvent,
    ASRProgressEvent,
    ASRErrorEvent,
    ASRSessionDoneEvent,
]

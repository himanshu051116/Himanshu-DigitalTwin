"""Bounded anonymous browser-session store for the LOCAL research demonstration.

NOT authentication, persistence, a distributed cache, or patient-data protection.
Each token owns a separate set of synthetic ReplaySession instances. The store
enforces a finite lifetime and capacity so anonymous requests cannot grow it
without bound. Multi-worker deployments require a different architecture.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from secrets import token_urlsafe

from .engine import ReplaySession

COOKIE_NAME = "hdt_demo_session"
SESSION_TTL_SECONDS = 30 * 60
MAX_SESSIONS = 32


@dataclass
class BrowserSession:
    patients: dict[str, ReplaySession]
    touched_at: float
    lock: RLock = field(default_factory=RLock)


class SessionCapacityError(Exception):
    """No remaining slots; fail closed rather than evict a live visitor."""


class BrowserSessionStore:
    def __init__(self, demo, model, model_label: str, *, ttl: float = SESSION_TTL_SECONDS,
                 max_sessions: int = MAX_SESSIONS):
        self._demo = demo
        self._model = model
        self._model_label = model_label
        self._ttl = ttl
        self._limit = max_sessions
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = RLock()

    def _new_session(self, now: float) -> BrowserSession:
        patients = {
            pid: ReplaySession(
                pid, deepcopy(patient.profile), deepcopy(patient.stream),
                model=self._model, model_label=self._model_label, cadence_min=5,
            )
            for pid, patient in self._demo.items()
        }
        return BrowserSession(patients=patients, touched_at=now)

    def _cleanup(self, now: float) -> None:
        for key, state in list(self._sessions.items()):
            if now - state.touched_at >= self._ttl:
                del self._sessions[key]

    def obtain(self, token: str | None) -> tuple[str, BrowserSession]:
        """Return a live token/state, or a new unpredictable token/state."""
        now = monotonic()
        with self._lock:
            self._cleanup(now)
            if token and len(token) <= 64 and token in self._sessions:
                state = self._sessions[token]
                state.touched_at = now
                return token, state
            if len(self._sessions) >= self._limit:
                raise SessionCapacityError("Demo session capacity reached; retry later.")
            new_token = token_urlsafe(32)
            state = self._new_session(now)
            self._sessions[new_token] = state
            return new_token, state

    def existing(self, token: str | None) -> BrowserSession | None:
        """WebSocket handshake must carry an existing browser cookie."""
        if not token or len(token) > 64:
            return None
        now = monotonic()
        with self._lock:
            self._cleanup(now)
            state = self._sessions.get(token)
            if state is not None:
                state.touched_at = now
            return state

"""The Coach loopback app.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-104…106`.

One WebSocket endpoint carrying JSON-RPC, and nothing else: no PTY, no TUI
dispatch, no dashboard admin routes, no login. Every connection passes
`LoopbackGuard` before a single RPC method runs.

Requests are dispatched as concurrent tasks rather than awaited in the read
loop. A coaching turn is a slow model call, and a serial loop could not receive
the cancel that stops it. Each connection owns its tasks, so closing the window
cancels the work instead of leaving it running against a socket nobody reads.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from hermes_coach.api.security import AccessRejected, LoopbackGuard
from hermes_coach.application.coaching_turn_service import Persisted
from hermes_coach.infrastructure.repositories.rpc_repository import (
    IdempotencyRepository,
    SessionRevisionRepository,
    StaleRevision,
)
from hermes_coach.infrastructure.sqlite.database import CoachDatabase


LOGGER = logging.getLogger("hermes_coach")

COACH_WS_PATH = "/api/coach/ws"

# 1008 is "policy violation": a failed loopback check is a well-formed request
# that is not allowed, not a malformed one.
CLOSE_UNAUTHORIZED = 1008

CANCEL_METHOD = "coach.cancel"

RpcMethod = Callable[[dict[str, Any]], Awaitable[Any] | Any]


class RpcError(Exception):
    """A method-level failure. `code` is a stable string the UI can branch on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TurnCancelled(Exception):
    """The turn was cancelled. Not a failure — the Coachee asked for it."""


class CancellationRegistry:
    """Cancellation flags keyed by one turn, never by a whole session."""

    def __init__(self) -> None:
        self._cancelled: set[tuple[str, str]] = set()

    def cancel(self, session_id: str, turn_id: str) -> None:
        self._cancelled.add((session_id, turn_id))

    def is_cancelled(self, session_id: str, turn_id: str) -> bool:
        return (session_id, turn_id) in self._cancelled

    def raise_if_cancelled(self, session_id: str, turn_id: str) -> None:
        if self.is_cancelled(session_id, turn_id):
            raise TurnCancelled(f"{session_id}/{turn_id} was cancelled")

    def forget(self, session_id: str, turn_id: str) -> None:
        """Clear the flag once a turn is over, so a retry is not poisoned."""
        self._cancelled.discard((session_id, turn_id))


@dataclass
class _Registration:
    method: RpcMethod
    wants_cancellation: bool = False
    mutating: bool = False


@dataclass
class MethodRegistry:
    """Explicit allowlist — an unregistered name is simply not callable."""

    _methods: dict[str, _Registration] = field(default_factory=dict)

    def register(
        self,
        name: str,
        method: RpcMethod,
        *,
        wants_cancellation: bool = False,
        mutating: bool = False,
    ) -> None:
        """`mutating=True` puts the command behind revision and idempotency."""
        if name in self._methods:
            raise ValueError(f"RPC method {name} is already registered")
        self._methods[name] = _Registration(method, wants_cancellation, mutating)

    def has_mutating_method(self) -> bool:
        return any(entry.mutating for entry in self._methods.values())

    def get(self, name: str) -> _Registration | None:
        return self._methods.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._methods))


def create_app(
    guard: LoopbackGuard,
    registry: MethodRegistry | None = None,
    *,
    cancellations: CancellationRegistry | None = None,
    database: CoachDatabase | None = None,
    clock: Callable[[], str] | None = None,
    ui_directory: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Hermes Coach", docs_url=None, redoc_url=None, openapi_url=None)
    methods = registry or MethodRegistry()
    cancel_registry = cancellations or CancellationRegistry()

    if methods.has_mutating_method() and database is None:
        # Fail at wiring time, not at the first mutation in front of the user.
        raise ValueError("a mutating RPC method needs a database for its envelope")

    app.state.guard = guard
    app.state.database = database
    app.state.methods = methods
    app.state.cancellations = cancel_registry
    # Connection id -> its outstanding tasks. Emptied on disconnect.
    app.state.in_flight: dict[int, set[asyncio.Task]] = {}

    if ui_directory is not None:
        _serve_ui(app, guard, ui_directory)

    @app.websocket(COACH_WS_PATH)
    async def coach_socket(websocket: WebSocket) -> None:
        try:
            guard.authorize(
                token=websocket.query_params.get("token"),
                peer=websocket.client.host if websocket.client else None,
                host=websocket.headers.get("host"),
                origin=websocket.headers.get("origin"),
            )
        except AccessRejected as rejected:
            # Refuse before accepting: an unauthorized caller never gets an open
            # socket, and the reason stays generic.
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason=str(rejected))
            return

        await websocket.accept()
        connection_id = id(websocket)
        tasks: set[asyncio.Task] = set()
        app.state.in_flight[connection_id] = tasks
        send_lock = asyncio.Lock()

        async def answer(request: Any) -> None:
            reply = await _dispatch(
                methods, cancel_registry, request, database, clock
            )
            async with send_lock:
                await websocket.send_json(reply)

        try:
            while True:
                request = await websocket.receive_json()
                task = asyncio.create_task(answer(request))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        except WebSocketDisconnect:
            return
        finally:
            for task in tuple(tasks):
                task.cancel()
            # Let the cancellations settle before the connection's slot goes.
            await asyncio.gather(*tasks, return_exceptions=True)
            app.state.in_flight.pop(connection_id, None)

    return app


def _serve_ui(app: FastAPI, guard: LoopbackGuard, directory: Path) -> None:
    """Serve the built page and its bundle from this same port.

    Same port, not a second server: the page reads `window.location.port` to
    find the backend, so a UI served from anywhere else hands the browser the
    wrong socket. Only `/` and `/assets` are routed — the app uses hash routing,
    so every destination stays on `/` and an SPA fallback would only turn a
    typo into a silently blank page.
    """
    root = directory.resolve()

    def check(request: Request) -> Response | None:
        try:
            guard.authorize_page(
                peer=request.client.host if request.client else None,
                host=request.headers.get("host"),
                origin=request.headers.get("origin"),
            )
        except AccessRejected as rejected:
            return Response(str(rejected), status_code=403)
        return None

    @app.get("/")
    async def page(request: Request) -> Response:
        refused = check(request)
        if refused is not None:
            return refused
        index = root / "index.html"
        if not index.is_file():
            return Response("no built UI", status_code=404)
        return FileResponse(index, media_type="text/html")

    @app.get("/assets/{asset_path:path}")
    async def asset(request: Request, asset_path: str) -> Response:
        refused = check(request)
        if refused is not None:
            return refused
        target = (root / "assets" / asset_path).resolve()
        # Resolve first, then confirm containment: a crafted path must not be
        # able to name a file outside the built UI.
        if not target.is_relative_to(root) or not target.is_file():
            return Response("not found", status_code=404)
        return FileResponse(target)


async def _dispatch(
    methods: MethodRegistry,
    cancellations: CancellationRegistry,
    request: Any,
    database: CoachDatabase | None = None,
    clock: Callable[[], str] | None = None,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        return _error(None, "invalid_request", "request must be a JSON object")

    request_id = request.get("id")
    name = request.get("method")
    if not isinstance(name, str):
        return _error(request_id, "invalid_request", "method must be a string")

    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _error(request_id, "invalid_request", "params must be an object")

    if name == CANCEL_METHOD:
        return _cancel(request_id, params, cancellations)

    registration = methods.get(name)
    if registration is None:
        return _error(request_id, "unknown_method", f"no such method: {name}")

    envelope: _Envelope | None = None
    if registration.mutating:
        if database is None:  # pragma: no cover - create_app refuses this
            return _error(request_id, "internal_error", "no database configured")
        try:
            envelope = _Envelope.parse(params, database, clock)
        except ValueError as invalid:
            return _error(request_id, "invalid_request", str(invalid))

        remembered = envelope.recall()
        if remembered is not None:
            # Answer the retry before checking revision. The first application
            # already moved the session, so a genuine retry is always "stale";
            # checking revision first would make retries impossible.
            return {"id": request_id, "result": remembered}
        try:
            envelope.require_current_revision()
        except StaleRevision as stale:
            return _error(request_id, "stale_revision", str(stale))

    call_params = dict(params)
    if registration.wants_cancellation:
        call_params["_cancellations"] = cancellations

    try:
        result = registration.method(call_params)
        if isinstance(result, Awaitable):
            result = await result
    except TurnCancelled:
        return _error(request_id, "cancelled", "the turn was cancelled")
    except RpcError as failure:
        return _error(request_id, failure.code, failure.message)
    except asyncio.CancelledError:
        raise
    except Exception:
        # Never surface an internal message: it can carry a path or a prompt.
        # The operator still needs it, so the traceback goes to the server log
        # only — an `internal_error` that leaves no trace anywhere cannot be
        # diagnosed, which is how this line came to exist.
        LOGGER.exception("method %s failed", name)
        return _error(request_id, "internal_error", "the request could not be completed")
    finally:
        session_id, turn_id = params.get("session_id"), params.get("turn_id")
        if isinstance(session_id, str) and isinstance(turn_id, str):
            cancellations.forget(session_id, turn_id)

    if envelope is not None:
        # Bump and remember in one transaction: a command that applied must
        # never look unapplied, and a remembered one must have moved the
        # session. A command that raised reaches neither.
        #
        # Inside a try, because a dispatcher that raises here answers nothing
        # at all and the client waits forever. Known gap: the method's own
        # writes and this envelope are separate transactions, so a failure here
        # leaves a command applied but unrecorded — reported, never silent.
        try:
            result = envelope.commit(name, result)
        except Exception:
            LOGGER.exception("envelope commit failed for %s", name)
            return _error(
                request_id,
                "envelope_failed",
                "the command could not be committed",
            )

    return {"id": request_id, "result": result}


@dataclass(frozen=True)
class _Envelope:
    """Revision and idempotency around one mutating command."""

    session_id: str
    revision: int
    idempotency_key: str
    database: CoachDatabase
    now: str

    @classmethod
    def parse(
        cls,
        params: dict[str, Any],
        database: CoachDatabase,
        clock: Callable[[], str] | None,
    ) -> "_Envelope":
        session_id = params.get("session_id")
        revision = params.get("revision")
        key = params.get("idempotency_key")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("a mutating command needs session_id")
        # bool is an int subclass; `revision: true` is not a revision.
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise ValueError("a mutating command needs an integer revision")
        if not isinstance(key, str) or not key:
            raise ValueError("a mutating command needs idempotency_key")
        return cls(
            session_id=session_id,
            revision=revision,
            idempotency_key=key,
            database=database,
            now=clock() if clock else "",
        )

    def recall(self) -> Any | None:
        return IdempotencyRepository(self.database.connection).recall(
            self.idempotency_key
        )

    def require_current_revision(self) -> None:
        SessionRevisionRepository(self.database.connection).require(
            self.session_id, self.revision
        )

    def commit(self, method: str, result: Any) -> Any:
        """Apply the command's own write and this envelope, atomically.

        A method that returns `Persisted` hands back the rows it wants written
        rather than committing them itself, so its write, the revision bump and
        the idempotency record share one transaction. Without that, a crash
        between them could leave a turn stored but replayable, or recorded but
        absent.
        """
        payload = result.result if isinstance(result, Persisted) else result
        with self.database.transaction():
            if isinstance(result, Persisted):
                result.apply(self.database.connection)
            SessionRevisionRepository(self.database.connection).bump(
                self.session_id, self.now
            )
            IdempotencyRepository(self.database.connection).remember(
                self.idempotency_key,
                method=method,
                session_id=self.session_id,
                result=payload,
                now=self.now,
            )
        return payload


def _cancel(
    request_id: Any, params: dict[str, Any], cancellations: CancellationRegistry
) -> dict[str, Any]:
    session_id, turn_id = params.get("session_id"), params.get("turn_id")
    if not isinstance(session_id, str) or not isinstance(turn_id, str):
        return _error(
            request_id, "invalid_request", "cancel needs session_id and turn_id"
        )
    # Cancelling a turn that already finished is a no-op, not an error: the UI
    # cannot know the turn ended before its click arrived.
    cancellations.cancel(session_id, turn_id)
    return {"id": request_id, "result": {"cancelled": True}}


def _error(request_id: Any, code: str, message: str) -> dict[str, Any]:
    return {"id": request_id, "error": {"code": code, "message": message}}

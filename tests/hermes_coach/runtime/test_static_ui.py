"""Serving the built web UI from the Coach backend.

Requirement families: `HC-PRODUCT`, `HC-PRIVACY`; sources `SRC-104…106`.

The page reads its port from `window.location.port`, so the UI has to be served
by the backend itself rather than a second dev server on another port — the two
cannot be split without the handshake pointing at the wrong socket.

The page is loopback-gated but NOT token-gated, and that asymmetry is the point
of most of this file: the browser cannot attach a token to the asset requests
`index.html` triggers, so gating them would make the app unloadable. The token
gates the WebSocket, which is the only thing that reaches data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hermes_coach.api.app import COACH_WS_PATH, MethodRegistry, create_app
from hermes_coach.api.security import LoopbackGuard


TOKEN = "t" * 32
PORT = 8731
INDEX = "<!doctype html><title>Hermes Coach</title>"
BUNDLE = "console.log('coach')"


@pytest.fixture
def ui(tmp_path: Path) -> Path:
    """A built UI directory, shaped the way `vite build` leaves one."""
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text(BUNDLE, encoding="utf-8")
    return tmp_path


def client(
    ui_directory: Path | None, *, peer: str = "127.0.0.1"
) -> TestClient:
    app = create_app(
        LoopbackGuard(token=TOKEN, port=PORT),
        MethodRegistry(),
        ui_directory=ui_directory,
    )
    return TestClient(
        app, base_url=f"http://127.0.0.1:{PORT}", client=(peer, 54321)
    )


def test_the_page_is_served_at_the_root(ui: Path) -> None:
    response = client(ui).get("/")
    assert response.status_code == 200
    assert "Hermes Coach" in response.text


def test_the_page_is_html(ui: Path) -> None:
    assert "text/html" in client(ui).get("/").headers["content-type"]


def test_the_launcher_url_with_its_token_reaches_the_page(ui: Path) -> None:
    """The printed link carries `?token=`; the page must still load."""
    assert client(ui).get(f"/?token={TOKEN}").status_code == 200


def test_an_asset_is_served(ui: Path) -> None:
    response = client(ui).get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert BUNDLE in response.text


def test_an_asset_needs_no_token(ui: Path) -> None:
    """The browser cannot attach one, so requiring it would break the app."""
    assert client(ui).get("/assets/index-abc123.js").status_code == 200


def test_the_websocket_still_needs_a_token(ui: Path) -> None:
    """Serving the page freely must not loosen what reaches data."""
    with client(ui) as test_client:
        with pytest.raises(WebSocketDisconnect):
            with test_client.websocket_connect(
                f"{COACH_WS_PATH}?token=wrong", headers={"host": f"127.0.0.1:{PORT}"}
            ):
                pass


def test_a_non_loopback_peer_cannot_fetch_the_page(ui: Path) -> None:
    assert client(ui, peer="192.168.1.10").get("/").status_code == 403


def test_a_non_loopback_peer_cannot_fetch_an_asset(ui: Path) -> None:
    response = client(ui, peer="192.168.1.10").get("/assets/index-abc123.js")
    assert response.status_code == 403


def test_a_foreign_host_header_is_refused(ui: Path) -> None:
    """The defence against DNS rebinding, which arrives as a loopback peer."""
    response = client(ui).get("/", headers={"host": "coach.example.com"})
    assert response.status_code == 403


def test_a_foreign_origin_is_refused(ui: Path) -> None:
    response = client(ui).get("/", headers={"origin": "https://example.com"})
    assert response.status_code == 403


def test_a_loopback_origin_is_accepted(ui: Path) -> None:
    response = client(ui).get("/", headers={"origin": f"http://localhost:{PORT}"})
    assert response.status_code == 200


def test_a_path_outside_the_ui_directory_is_refused(ui: Path) -> None:
    secret = ui.parent / "secret.txt"
    secret.write_text("khong duoc doc", encoding="utf-8")
    response = client(ui).get("/assets/../../secret.txt")
    assert response.status_code in (403, 404)
    assert "khong duoc doc" not in response.text


def test_an_unknown_path_is_not_the_page(ui: Path) -> None:
    """Hash routing keeps every destination on `/`, so no SPA fallback."""
    assert client(ui).get("/goals").status_code == 404


def test_the_backend_runs_with_no_built_ui() -> None:
    """A backend with no UI still serves RPC; only the page is missing."""
    assert client(None).get("/").status_code == 404


def test_the_websocket_works_with_no_built_ui() -> None:
    with client(None) as test_client:
        with test_client.websocket_connect(
            f"{COACH_WS_PATH}?token={TOKEN}", headers={"host": f"127.0.0.1:{PORT}"}
        ) as socket:
            socket.send_json({"id": 1, "method": "nope"})
            assert socket.receive_json()["error"]["code"] == "unknown_method"

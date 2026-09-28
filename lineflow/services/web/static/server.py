"""
Servidor HTTP basado únicamente en la biblioteca estándar de Python.

* ``/api/...``  -> API JSON (ver :mod:`lineflow.web.api`).
* ``/``         -> interfaz web (``static/index.html``).
* ``/static/..``-> hojas de estilo, scripts e íconos.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import unquote, urlsplit

from ..core import LinkedListError, NodeNotFoundError
from ..domain import LineError
from ..service import LineFlowService
from .api import ROUTES

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 2 * 1024 * 1024
log = logging.getLogger("lineflow")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class LineFlowServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: Tuple[str, int], service: LineFlowService, verbose: bool = False) -> None:
        super().__init__(address, RequestHandler)
        self.service = service
        self.verbose = verbose


class RequestHandler(BaseHTTPRequestHandler):
    server: LineFlowServer
    server_version = "LineFlow/1.0"
    protocol_version = "HTTP/1.1"

    # --- verbos HTTP -------------------------------------------------------
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    # --- utilidades --------------------------------------------------------
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if self.server.verbose:
            super().log_message(format, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Body must be valid JSON") from None
        if not isinstance(data, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Body must be a JSON object")
        return data

    # --- enrutamiento ------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        path = unquote(urlsplit(self.path).path)
        try:
            if path.startswith("/api/"):
                self._handle_api(method, path)
            elif method == "GET":
                self._handle_static(path)
            else:
                raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")
        except ApiError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except NodeNotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except (LineError, LinkedListError, ValueError, TypeError, KeyError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:  # pragma: no cover - errores inesperados
            log.error("Unexpected error on %s %s\n%s", method, path, traceback.format_exc())
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error"})

    def _handle_api(self, method: str, path: str) -> None:
        allowed = False
        for route_method, pattern, handler in ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            allowed = True
            if route_method != method:
                continue
            body = self._read_json() if method in ("POST", "PUT", "PATCH", "DELETE") else {}
            result = handler(self.server.service, match.groups(), body)
            self._send_json(HTTPStatus.OK, result)
            return
        if allowed:
            raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, f"{method} not allowed on {path}")
        raise ApiError(HTTPStatus.NOT_FOUND, f"Unknown endpoint {path}")

    def _handle_static(self, path: str) -> None:
        if path in ("/", "/index.html"):
            target = STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            target = (STATIC_DIR / path[len("/static/"):]).resolve()
            if STATIC_DIR not in target.parents:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found")
        elif path == "/favicon.ico":
            target = STATIC_DIR / "favicon.svg"
        else:
            raise ApiError(HTTPStatus.NOT_FOUND, "Not found")
        if not target.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "image/svg+xml"):
            content_type += "; charset=utf-8"
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)


def create_server(host: str = "127.0.0.1", port: int = 8000,
                  service: Optional[LineFlowService] = None, verbose: bool = False) -> LineFlowServer:
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    return LineFlowServer((host, port), service or LineFlowService(), verbose)

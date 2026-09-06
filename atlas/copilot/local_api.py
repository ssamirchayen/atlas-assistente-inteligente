from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from .business_lab import BusinessLabCopilotBridge
from .models import CopilotResponse

JsonPayload = dict[str, Any]
CopilotHandler = Callable[[JsonPayload], CopilotResponse]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_ALLOWED_ORIGIN = "http://127.0.0.1:5055"
REPORT_DOWNLOAD_PREFIX = "business_lab_smart_report"
REPORT_DOWNLOAD_EXTENSIONS = {".json", ".csv", ".md", ".html", ".xlsx"}


class AtlasCopilotHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        copilot_handler: CopilotHandler,
        allowed_origin: str,
        api_token: str,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.copilot_handler = copilot_handler
        self.allowed_origin = allowed_origin
        self.api_token = api_token


class AtlasCopilotRequestHandler(BaseHTTPRequestHandler):
    server: AtlasCopilotHttpServer

    def do_OPTIONS(self) -> None:
        self._send_json(
            204,
            {},
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/api/copilot/health"}:
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "status": "ok",
                        "service": "atlas-copilot-bridge",
                        "host": self.server.server_address[0],
                        "port": self.server.server_address[1],
                    },
                },
            )
            return

        if path.startswith("/api/copilot/reports/"):
            self._serve_report_download(path)
            return

        self._send_json(
            404,
            {
                "ok": False,
                "error": {
                    "code": "not_found",
                    "message": "Endpoint não encontrado.",
                },
            },
        )

    def do_POST(self) -> None:
        if self.path != "/api/copilot/message":
            self._send_json(
                404,
                {
                    "ok": False,
                    "error": {
                        "code": "not_found",
                        "message": "Endpoint não encontrado.",
                    },
                },
            )
            return

        if not self._authorized():
            self._send_json(
                401,
                {
                    "ok": False,
                    "error": {
                        "code": "unauthorized",
                        "message": "Token local do Copilot inválido.",
                    },
                },
            )
            return

        try:
            payload = self._read_json_body()
        except ValueError as error:
            self._send_json(
                400,
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_json",
                        "message": str(error),
                    },
                },
            )
            return

        response = self.server.copilot_handler(payload)
        self._send_json(
            200 if response.ok else 422,
            response.to_api_payload(),
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if os.getenv("ATLAS_COPILOT_DEBUG") == "1":
            super().log_message(format, *args)

    def _authorized(self) -> bool:
        configured = self.server.api_token
        if not configured:
            return True
        provided = self.headers.get("X-Atlas-Copilot-Token", "")
        return provided == configured

    def _read_json_body(self) -> JsonPayload:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("Corpo JSON inválido.") from error
        if not isinstance(decoded, dict):
            raise ValueError("O corpo precisa ser um objeto JSON.")
        return decoded

    def _send_json(
        self,
        status: int,
        payload: JsonPayload,
    ) -> None:
        body = b"" if status == 204 else json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", self.server.allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Atlas-Copilot-Token",
        )
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _serve_report_download(self, path: str) -> None:
        filename = unquote(path.rsplit("/", 1)[-1])
        if not _is_allowed_report_filename(filename):
            self._send_json(
                403,
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_report_file",
                        "message": "Arquivo de relatório não permitido.",
                    },
                },
            )
            return

        report_dir = _report_download_dir()
        target = (report_dir / filename).resolve()
        if target.parent != report_dir or not target.exists() or not target.is_file():
            self._send_json(
                404,
                {
                    "ok": False,
                    "error": {
                        "code": "report_not_found",
                        "message": "Relatório não encontrado no Atlas.",
                    },
                },
            )
            return

        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type_for_report(target))
        self.send_header("Access-Control-Allow-Origin", self.server.allowed_origin)
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{target.name}"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_copilot_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    copilot_handler: CopilotHandler | None = None,
    allowed_origin: str | None = None,
    api_token: str | None = None,
) -> AtlasCopilotHttpServer:
    bridge = BusinessLabCopilotBridge()
    handler = copilot_handler or bridge.handle
    return AtlasCopilotHttpServer(
        (host, port),
        AtlasCopilotRequestHandler,
        copilot_handler=handler,
        allowed_origin=(
            allowed_origin
            or os.getenv("ATLAS_COPILOT_ALLOWED_ORIGIN")
            or DEFAULT_ALLOWED_ORIGIN
        ),
        api_token=api_token or os.getenv("ATLAS_COPILOT_TOKEN", ""),
    )


def run_copilot_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    server = create_copilot_server(
        host=host,
        port=port,
    )
    print(
        "Atlas Copilot Bridge ativo em "
        f"http://{server.server_address[0]}:{server.server_address[1]}"
    )
    print("Endpoint: POST /api/copilot/message")
    print("Use Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando Atlas Copilot Bridge...")
    finally:
        server.server_close()


def _report_download_dir() -> Path:
    return Path(
        os.getenv(
            "ATLAS_SMART_REPORT_OUTPUT_DIR",
            str(Path("data") / "business_lab_benchmark"),
        )
    ).resolve()


def _is_allowed_report_filename(filename: str) -> bool:
    path = Path(filename)
    return (
        filename == path.name
        and filename.startswith(REPORT_DOWNLOAD_PREFIX)
        and path.suffix.lower() in REPORT_DOWNLOAD_EXTENSIONS
    )


def _content_type_for_report(path: Path) -> str:
    content_types = {
        ".csv": "text/csv; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".xlsx": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    }
    return content_types.get(path.suffix.lower(), "application/octet-stream")

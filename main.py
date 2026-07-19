from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from src.reposcout import build_graph

load_dotenv()

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
GRAPH = build_graph()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            self.send_json({"status": "ok", "graph": "reposcout-mvp"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/search":
            self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        try:
            requirement = str(self.read_json().get("requirement", "")).strip()
            result = GRAPH.invoke({"raw_requirement": requirement})
            self.send_json(
                {
                    "requirement": result.get("requirement", {}),
                    "query": result.get("query", ""),
                    "report": result.get("report", ""),
                    "recommendations": result.get("recommendations", []),
                    "error": result.get("error", ""),
                },
                HTTPStatus.BAD_REQUEST
                if result.get("error") and not result.get("query")
                else HTTPStatus.OK,
            )
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "请求格式无效"}, HTTPStatus.BAD_REQUEST)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"RepoScout 已启动：http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()

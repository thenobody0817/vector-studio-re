#!/usr/bin/env python3
"""Protocol tests for the Vector Studio client.

A fake broker reproduces the wire behaviour observed in the shipped Electron
bundle: bearer auth on 127.0.0.1, POST /api/v1/automation/rpc, version-1
request envelope, `{ok:true,result}` / `{ok:false,error}` responses.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client"))

from vector_client import VectorStudio, VectorStudioError  # noqa: E402

SECRET = "a" * 64
INTEGRATION_SECRET = "b" * 64


class FakeBroker:
    """Records the last request and replies with a canned body."""

    def __init__(self, response: dict, status: int = 200):
        self.response = response
        self.status = status
        self.last: dict = {}
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence the default stderr log
                pass

            def do_POST(self):  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                broker.last = {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(body.decode("utf-8")) if body else None,
                }
                payload = json.dumps(broker.response).encode("utf-8")
                self.send_response(broker.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class ClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "credential").write_text(SECRET, encoding="utf-8")
        (self.home / "credentials").mkdir()
        (self.home / "credentials" / "opencode").write_text(INTEGRATION_SECRET, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("VECTOR_STUDIO_INTEGRATION_ID", None)

    def client(self, broker: FakeBroker) -> VectorStudio:
        (self.home / "runtime.json").write_text(
            json.dumps({"version": 1, "product": "vector", "port": broker.port, "pid": 1}),
            encoding="utf-8",
        )
        return VectorStudio(home=self.home)

    def test_request_envelope_and_headers(self) -> None:
        broker = FakeBroker({"version": 1, "id": "x", "ok": True, "result": {"done": True}})
        try:
            result = self.client(broker).rpc(
                "shape.create",
                {"kind": "rectangle"},
                document_id="doc-1",
                expected_revision=7,
                request_id="req-1",
            )
        finally:
            broker.close()

        self.assertEqual(result, {"done": True})
        self.assertEqual(broker.last["path"], "/api/v1/automation/rpc")
        self.assertEqual(broker.last["headers"]["Authorization"], f"Bearer {SECRET}")
        self.assertEqual(broker.last["headers"]["Content-Type"], "application/json")
        body = broker.last["body"]
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["id"], "req-1")
        self.assertEqual(body["operation"], "shape.create")
        self.assertEqual(body["documentId"], "doc-1")
        self.assertEqual(body["expectedRevision"], 7)
        self.assertEqual(body["params"], {"kind": "rectangle"})

    def test_integration_credential_is_scoped(self) -> None:
        broker = FakeBroker({"version": 1, "id": "x", "ok": True, "result": {}})
        os.environ["VECTOR_STUDIO_INTEGRATION_ID"] = "opencode"
        try:
            self.client(broker).rpc("capabilities")
        finally:
            broker.close()
        self.assertEqual(
            broker.last["headers"]["Authorization"], f"Bearer opencode.{INTEGRATION_SECRET}"
        )

    def test_error_object_raises_with_code(self) -> None:
        broker = FakeBroker(
            {
                "version": 1,
                "id": "x",
                "ok": False,
                "error": {"code": "UNKNOWN_OPERATION", "message": "Use capabilities."},
            }
        )
        try:
            with self.assertRaises(VectorStudioError) as ctx:
                self.client(broker).rpc("nope")
        finally:
            broker.close()
        self.assertEqual(ctx.exception.code, "UNKNOWN_OPERATION")

    def test_http_error_raises(self) -> None:
        broker = FakeBroker({"error": "Unauthorized"}, status=401)
        try:
            with self.assertRaises(VectorStudioError):
                self.client(broker).rpc("capabilities")
        finally:
            broker.close()

    def test_missing_runtime_is_reported(self) -> None:
        client = VectorStudio(home=self.home)
        with self.assertRaises(VectorStudioError) as ctx:
            client.rpc("capabilities")
        self.assertIn("not running", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()

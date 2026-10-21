#!/usr/bin/env python3
"""Clean-room client for the Vector Studio automation protocol (version 1).

Recovered by reading the shipped Electron bundle (see ../docs/protocol.md).
Standard library only - no third-party dependencies.

The app exposes a loopback HTTP broker:

    POST http://127.0.0.1:<port>/api/v1/automation/rpc
    GET  http://127.0.0.1:<port>/api/v1/automation/events

`<port>` and the bearer credential live in the automation home directory
(default ~/.vector-studio/automation):

    runtime.json   {"version":1,"product":"vector","port":…,"pid":…,"instanceId":…}
    credential     64 hex chars - the shared secret
    credentials/<id>  64 hex chars - a per-integration secret (sent as "<id>.<secret>")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator

PROTOCOL_VERSION = 1
RPC_PATH = "/api/v1/automation/rpc"
EVENTS_PATH = "/api/v1/automation/events"
DEFAULT_HOME = Path.home() / ".vector-studio" / "automation"


class VectorStudioError(RuntimeError):
    """Raised when the broker is unreachable or answers with an error object."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message if not code else f"{code}: {message}")
        self.code = code
        self.message = message


def automation_home() -> Path:
    """Resolve the automation home the same way the app does."""
    explicit = os.environ.get("VECTOR_STUDIO_AUTOMATION_HOME")
    if explicit:
        return Path(explicit)
    user_data = os.environ.get("VECTOR_STUDIO_USER_DATA")
    if user_data:
        return Path(user_data) / "automation"
    return DEFAULT_HOME


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


class VectorStudio:
    """Thin client for one running Vector Studio instance."""

    def __init__(self, home: Path | None = None, timeout: float = 30.0):
        self.home = Path(home) if home else automation_home()
        self.timeout = timeout

    # ------------------------------------------------------------------ state

    def runtime(self) -> dict[str, Any]:
        raw = _read(self.home / "runtime.json")
        if not raw:
            raise VectorStudioError(
                "Vector Studio automation is not running. Enable it in Settings -> Integrations."
            )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VectorStudioError(f"runtime.json is not valid JSON: {exc}") from exc

    def port(self) -> int:
        return int(self.runtime()["port"])

    def credential(self) -> str:
        """Shared secret, or "<integration-id>.<secret>" for a scoped token."""
        integration_id = os.environ.get("VECTOR_STUDIO_INTEGRATION_ID")
        if integration_id:
            secret = _read(self.home / "credentials" / integration_id)
            if secret:
                return f"{integration_id}.{secret}"
        shared = _read(self.home / "credential")
        if not shared:
            raise VectorStudioError(
                "No automation credential found. Open Vector Studio once to set up automation."
            )
        return shared

    # -------------------------------------------------------------- transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credential()}",
            "Content-Type": "application/json",
        }

    def rpc(
        self,
        operation: str,
        params: dict[str, Any] | None = None,
        *,
        document_id: str | None = None,
        session_id: str | None = None,
        expected_revision: int | None = None,
        request_id: str | None = None,
    ) -> Any:
        """Send one version-1 request and return its `result` payload."""
        body: dict[str, Any] = {
            "version": PROTOCOL_VERSION,
            "id": request_id or uuid.uuid4().hex,
            "operation": operation,
        }
        if params is not None:
            body["params"] = params
        if document_id is not None:
            body["documentId"] = document_id
        if session_id is not None:
            body["sessionId"] = session_id
        if expected_revision is not None:
            body["expectedRevision"] = expected_revision

        url = f"http://127.0.0.1:{self.port()}{RPC_PATH}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise VectorStudioError(f"HTTP {exc.code}", f"HTTP_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VectorStudioError(f"connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise VectorStudioError(f"invalid JSON from broker: {exc}") from exc

        if not payload.get("ok"):
            error = payload.get("error") or {}
            raise VectorStudioError(
                error.get("message", "operation failed"), error.get("code")
            )
        return payload.get("result")

    def events(self) -> Iterator[dict[str, Any]]:
        """Stream broker events.

        Vector Studio 0.1.11 does not implement the event route (it answers
        404), so this raises a clear error instead of hanging. Poll `inspect`
        or `session.list` for the current revision on those builds.
        """
        url = f"http://127.0.0.1:{self.port()}{EVENTS_PATH}"
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise VectorStudioError(
                    "this Vector Studio build does not expose an event stream; "
                    "poll inspect or session.list for the revision",
                    "EVENTS_UNSUPPORTED",
                ) from exc
            raise VectorStudioError(f"HTTP {exc.code}", f"HTTP_{exc.code}") from exc
        with response:
            for line in response:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

    # ------------------------------------------------------------- operations

    def capabilities(self, query: str | None = None) -> list[dict[str, Any]]:
        params = {"query": query} if query else {}
        return list(self.rpc("capabilities", params)["operations"])

    def describe(self, operation: str) -> dict[str, Any]:
        return self.rpc("describe", {"operation": operation})

    def session_list(self) -> dict[str, Any]:
        """Return the broker's session view: {sessions, activeId, busy}."""
        result = self.rpc("session.list")
        return result if isinstance(result, dict) else {"sessions": result}

    def session_show(self) -> dict[str, Any]:
        return self.rpc("session.show")

    def inspect(self, document_id: str | None = None) -> dict[str, Any]:
        return self.rpc("inspect", document_id=document_id)

    def render(
        self, document_id: str, revision: int, edge: int | None = None
    ) -> dict[str, Any]:
        params = {"edge": edge} if edge else {}
        return self.rpc(
            "render",
            params,
            document_id=document_id,
            expected_revision=revision,
        )

    def shape_create(
        self,
        document_id: str,
        revision: int,
        kind: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return self.rpc(
            "shape.create",
            {"kind": kind, "arguments": arguments},
            document_id=document_id,
            expected_revision=revision,
            request_id=request_id,
        )

    def undo(self, document_id: str, revision: int) -> dict[str, Any]:
        return self.rpc("undo", document_id=document_id, expected_revision=revision)

    def redo(self, document_id: str, revision: int) -> dict[str, Any]:
        return self.rpc("redo", document_id=document_id, expected_revision=revision)

    def selection_set(self, document_id: str, revision: int, ids: list[str]) -> dict[str, Any]:
        return self.rpc(
            "selection.set",
            {"ids": ids},
            document_id=document_id,
            expected_revision=revision,
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Vector Studio automation client")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cap = sub.add_parser("capabilities", help="list supported operations")
    p_cap.add_argument("--query", default=None)

    p_desc = sub.add_parser("describe", help="describe one operation")
    p_desc.add_argument("operation")

    sub.add_parser("session-list", help="list open documents")
    sub.add_parser("doctor", help="show broker status")

    p_render = sub.add_parser("render", help="render a document revision to PNG")
    p_render.add_argument("--document", required=True)
    p_render.add_argument("--revision", required=True, type=int)
    p_render.add_argument("--edge", type=int, default=None)
    p_render.add_argument("--out", default=None)

    p_exec = sub.add_parser("execute", help="run any operation")
    p_exec.add_argument("operation")
    p_exec.add_argument("--params", default=None)
    p_exec.add_argument("--document", default=None)
    p_exec.add_argument("--revision", type=int, default=None)
    p_exec.add_argument("--id", dest="request_id", default=None)

    args = parser.parse_args(argv)
    client = VectorStudio()

    if args.command == "doctor":
        try:
            runtime = client.runtime()
        except VectorStudioError as exc:
            print(json.dumps({"ok": False, "error": exc.message}))
            return 1
        print(json.dumps({"ok": True, **runtime}))
        return 0

    if args.command == "capabilities":
        print(json.dumps(client.capabilities(args.query), indent=2))
        return 0

    if args.command == "describe":
        print(json.dumps(client.describe(args.operation), indent=2))
        return 0

    if args.command == "session-list":
        print(json.dumps(client.session_list(), indent=2))
        return 0

    if args.command == "render":
        result = client.render(args.document, args.revision, args.edge)
        if args.out and result.get("base64"):
            import base64

            Path(args.out).write_bytes(base64.b64decode(result["base64"]))
            print(json.dumps({"ok": True, "written": args.out}))
        else:
            print(json.dumps(result))
        return 0

    if args.command == "execute":
        params = json.loads(args.params) if args.params else None
        result = client.rpc(
            args.operation,
            params,
            document_id=args.document,
            expected_revision=args.revision,
            request_id=args.request_id,
        )
        print(json.dumps(result, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

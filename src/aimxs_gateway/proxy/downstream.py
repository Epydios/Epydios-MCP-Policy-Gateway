from __future__ import annotations

import json
import threading
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple


class DownstreamError(RuntimeError):
    pass


@dataclass
class DownstreamServer:
    name: str
    command: List[str]
    env: Optional[Dict[str, str]] = None
    process: Optional[subprocess.Popen] = None

    def __post_init__(self):
        self._lock = threading.Lock()
        self._pending: Dict[str, Tuple[threading.Event, Dict[str, Any]]] = {}
        self._alive = False
        self._reader_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.process is not None:
            return
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=self.env,
            bufsize=1,
        )
        self._alive = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def stop(self) -> None:
        self._alive = False
        if self.process is not None:
            try:
                self.process.terminate()
            except Exception:
                pass

    def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            if not self._alive:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id")
            if msg_id is None:
                continue
            key = str(msg_id)
            with self._lock:
                entry = self._pending.get(key)
            if not entry:
                continue
            ev, holder = entry
            holder["response"] = msg
            ev.set()

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout_seconds: float = 30.0) -> Dict[str, Any]:
        if self.process is None:
            self.start()
        assert self.process is not None and self.process.stdin is not None

        req_id = uuid.uuid4().hex[:12]
        ev = threading.Event()
        holder: Dict[str, Any] = {}
        with self._lock:
            self._pending[req_id] = (ev, holder)

        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        try:
            self.process.stdin.write(json.dumps(msg) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            with self._lock:
                self._pending.pop(req_id, None)
            raise DownstreamError(f"Failed to write to downstream {self.name}: {e}")

        ok = ev.wait(timeout=timeout_seconds)
        with self._lock:
            self._pending.pop(req_id, None)
        if not ok:
            raise DownstreamError(f"Timeout waiting for downstream {self.name} response to {method}")
        resp = holder.get("response")
        if not isinstance(resp, dict):
            raise DownstreamError(f"Malformed downstream response from {self.name}")
        return resp

    def initialize(self) -> Dict[str, Any]:
        resp = self.request("initialize", {}, timeout_seconds=30.0)
        if "error" in resp:
            raise DownstreamError(f"Downstream {self.name} initialize error: {resp['error']}")
        return resp.get("result") or {}

    def tools_list(self) -> Dict[str, Any]:
        resp = self.request("tools/list", {}, timeout_seconds=30.0)
        if "error" in resp:
            raise DownstreamError(f"Downstream {self.name} tools/list error: {resp['error']}")
        return resp.get("result") or {}

    def tools_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.request("tools/call", {"name": tool_name, "arguments": arguments or {}}, timeout_seconds=120.0)
        if "error" in resp:
            raise DownstreamError(f"Downstream {self.name} tools/call error: {resp['error']}")
        return resp.get("result") or {}

from __future__ import annotations

import sys
import json
import uuid
from typing import Any, Dict, Optional

from aimxs_gateway.schemas import (
    DecisionRequest,
    DecisionAction,
    mcp_text_content,
    mcp_error,
)
from aimxs_gateway.policy.base import PolicyPlugin
from aimxs_gateway.approval.store import ApprovalStore
from aimxs_gateway.executor.sandbox import SandboxExecutor, SandboxError
from aimxs_gateway.evidence.sink_jsonl import EvidenceSinkJSONL
from aimxs_gateway.proxy.router import ProxyRouter
from aimxs_gateway.proxy.downstream import DownstreamError


class StdioMCPServer:
    def __init__(
        self,
        *,
        mode: str,
        policy: PolicyPlugin,
        approvals: ApprovalStore,
        executor: SandboxExecutor,
        evidence: EvidenceSinkJSONL,
        approval_ttl_seconds: int,
        proxy_router: Optional[ProxyRouter] = None,
    ):
        self.mode = (mode or "demo").lower()
        self.policy = policy
        self.approvals = approvals
        self.executor = executor
        self.evidence = evidence
        self.approval_ttl_seconds = approval_ttl_seconds
        self.proxy_router = proxy_router

        self.session_id = uuid.uuid4().hex
        self._server_name = "aimxs-mcp-gateway"
        self._server_version = "0.2.1"

    def run_forever(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if not isinstance(msg, dict) or "method" not in msg:
                continue

            req_id = msg.get("id", None)
            method = msg.get("method")
            params = msg.get("params") or {}

            try:
                if method == "initialize":
                    self._send_result(req_id, self._handle_initialize(params))
                elif method == "tools/list":
                    self._send_result(req_id, self._handle_tools_list())
                elif method == "tools/call":
                    self._send_result(req_id, self._handle_tools_call(params))
                else:
                    self._send_error(req_id, -32601, f"Method not found: {method}")
            except Exception as e:
                self._send_error(req_id, -32000, "Internal error", {"exception": str(e)})

    def _send_result(self, req_id: Any, result: Dict[str, Any]) -> None:
        if req_id is None:
            return
        out = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()

    def _send_error(self, req_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        if req_id is None:
            return
        out = {"jsonrpc": "2.0", "id": req_id, "error": mcp_error(code, message, data)}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()

    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.evidence.emit("initialize", {"session_id": self.session_id, "mode": self.mode})
        return {
            "serverInfo": {"name": self._server_name, "version": self._server_version},
            "capabilities": {"tools": True},
            "session_id": self.session_id,
        }

    def _handle_tools_list(self) -> Dict[str, Any]:
        if self.mode == "proxy" and self.proxy_router is not None:
            tools = self.proxy_router.build_tools_catalog()
            return {"tools": tools}

        # demo tools (built-in)
        tools = [
            {
                "name": "shell.exec",
                "description": "Execute a sandboxed command (argv list) with an allowlist policy.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"argv": {"type": "array", "items": {"type": "string"}}},
                    "required": ["argv"],
                },
            },
            {
                "name": "fs.list",
                "description": "List files under the sandbox directory.",
                "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
            {
                "name": "fs.read",
                "description": "Read a file under the sandbox directory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "fs.write",
                "description": "Write a file under the sandbox directory (default requires approval).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "mode": {"type": "string", "enum": ["overwrite", "append"]},
                    },
                    "required": ["path", "content"],
                },
            },
        ]
        return {"tools": tools}

    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}
        if not isinstance(tool_name, str):
            return mcp_text_content("Invalid tool name.")

        request_id = uuid.uuid4().hex[:12]
        requestor_principal = "agent:default"
        meta = params.get("meta") or {}
        if isinstance(meta, dict) and isinstance(meta.get("requestor_principal"), str):
            requestor_principal = meta["requestor_principal"]

        nonce = uuid.uuid4().hex

        dr = DecisionRequest(
            session_id=self.session_id,
            request_id=request_id,
            requestor_principal=requestor_principal,
            tool_name=tool_name,
            tool_args=tool_args if isinstance(tool_args, dict) else {},
            posture="normal",
            nonce=nonce,
        )
        fp = dr.fingerprint()

        self.evidence.emit("tool_call_proposed", {
            "session_id": self.session_id,
            "request_id": request_id,
            "requestor_principal": requestor_principal,
            "tool_name": tool_name,
            "fingerprint": fp,
        })

        decision = self.policy.evaluate(dr)
        self.evidence.emit("decision_made", {
            "session_id": self.session_id,
            "request_id": request_id,
            "fingerprint": fp,
            "action": decision.action.value,
            "risk_tier": decision.risk_tier.value,
            "reason_code": decision.reason_code,
        })

        if decision.action == DecisionAction.DENY:
            self.evidence.emit("tool_call_blocked", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "reason_code": decision.reason_code,
            })
            return mcp_text_content(f"DENIED: {decision.reason_code}")

        if decision.action == DecisionAction.REQUIRE_APPROVAL:
            pa = self.approvals.create(
                fingerprint=fp,
                request_snapshot_json=dr.canonical_json(),
                requestor_principal=requestor_principal,
                tool_name=tool_name,
                risk_tier=decision.risk_tier.value,
                ttl_seconds=self.approval_ttl_seconds,
            )
            self.evidence.emit("approval_required", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "approval_request_id": pa.approval_request_id,
                "expires_at": pa.expires_at,
            })

            outcome = self.approvals.wait_for_decision(pa.approval_request_id, timeout_seconds=self.approval_ttl_seconds)
            if outcome != "approved":
                self.evidence.emit("tool_call_blocked", {
                    "session_id": self.session_id,
                    "request_id": request_id,
                    "fingerprint": fp,
                    "approval_request_id": pa.approval_request_id,
                    "status": outcome,
                })
                return mcp_text_content(f"BLOCKED ({outcome}). approval_request_id={pa.approval_request_id}")

            self.approvals.mark_executed(pa.approval_request_id)

        # ALLOW (or approved) -> execute
        try:
            if self.mode == "proxy" and self.proxy_router is not None:
                result = self.proxy_router.route_call(tool_name, dr.tool_args)
            else:
                result = self._execute_demo_tool(tool_name, dr.tool_args)

            self.evidence.emit("tool_call_executed", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "tool_name": tool_name,
            })
            if self.mode == "proxy" and isinstance(result, dict) and "content" in result:
                return result
            return mcp_text_content(json.dumps(result, indent=2))
        except DownstreamError as de:
            self.evidence.emit("tool_call_failed", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "tool_name": tool_name,
                "error": str(de),
            })
            return mcp_text_content(f"ERROR: {de}")
        except SandboxError as se:
            self.evidence.emit("tool_call_failed", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "tool_name": tool_name,
                "error": str(se),
            })
            return mcp_text_content(f"ERROR: {se}")
        except Exception as e:
            self.evidence.emit("tool_call_failed", {
                "session_id": self.session_id,
                "request_id": request_id,
                "fingerprint": fp,
                "tool_name": tool_name,
                "error": str(e),
            })
            return mcp_text_content(f"ERROR: {e}")

    def _execute_demo_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "shell.exec":
            argv = args.get("argv") or []
            return self.executor.shell_exec(argv=argv)
        if tool_name == "fs.list":
            path = args.get("path") or "."
            return self.executor.fs_list(path=path)
        if tool_name == "fs.read":
            return self.executor.fs_read(path=str(args.get("path")))
        if tool_name == "fs.write":
            return self.executor.fs_write(
                path=str(args.get("path")),
                content=str(args.get("content")),
                mode=str(args.get("mode") or "overwrite"),
            )
        raise SandboxError("Unknown tool.")

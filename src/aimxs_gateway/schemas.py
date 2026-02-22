from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import hashlib


class DecisionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class DecisionRequest:
    session_id: str
    request_id: str
    requestor_principal: str
    tool_name: str
    tool_args: Dict[str, Any]
    posture: str
    nonce: str

    def canonical_dict(self) -> Dict[str, Any]:
        # Deterministic ordering for hashing.
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "requestor_principal": self.requestor_principal,
            "tool_name": self.tool_name,
            "tool_args": self._canonicalize(self.tool_args),
            "posture": self.posture,
            "nonce": self.nonce,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), separators=(",", ":"), sort_keys=True)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @staticmethod
    def _canonicalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: DecisionRequest._canonicalize(obj[k]) for k in sorted(obj.keys())}
        if isinstance(obj, list):
            return [DecisionRequest._canonicalize(x) for x in obj]
        return obj


@dataclass(frozen=True)
class Decision:
    action: DecisionAction
    risk_tier: RiskTier
    reason_code: str
    details: Optional[Dict[str, Any]] = None


def mcp_text_content(text: str) -> Dict[str, Any]:
    # Common MCP-ish response style: a list of content blocks.
    return {"content": [{"type": "text", "text": text}]}


def mcp_error(code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err

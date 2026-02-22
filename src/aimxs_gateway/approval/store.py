from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import time
import threading
import uuid


@dataclass
class PendingApproval:
    approval_request_id: str
    fingerprint: str
    request_snapshot_json: str
    requestor_principal: str
    tool_name: str
    risk_tier: str
    created_at: float
    expires_at: float
    status: str = "pending"  # pending|approved|denied|expired|executed
    approver_principal: Optional[str] = None
    decision_at: Optional[float] = None

    def time_remaining(self) -> float:
        return max(0.0, self.expires_at - time.time())


class ApprovalStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending: Dict[str, PendingApproval] = {}
        self._events: Dict[str, threading.Event] = {}
        self._decisions: Dict[str, str] = {}  # id -> approved|denied|expired

    def create(self, *, fingerprint: str, request_snapshot_json: str, requestor_principal: str,
               tool_name: str, risk_tier: str, ttl_seconds: int) -> PendingApproval:
        approval_id = uuid.uuid4().hex[:12]
        now = time.time()
        pa = PendingApproval(
            approval_request_id=approval_id,
            fingerprint=fingerprint,
            request_snapshot_json=request_snapshot_json,
            requestor_principal=requestor_principal,
            tool_name=tool_name,
            risk_tier=risk_tier,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        ev = threading.Event()
        with self._lock:
            self._pending[approval_id] = pa
            self._events[approval_id] = ev
            self._decisions.pop(approval_id, None)
        return pa

    def list_pending(self) -> List[PendingApproval]:
        now = time.time()
        out: List[PendingApproval] = []
        with self._lock:
            for pa in self._pending.values():
                if pa.status == "pending" and pa.expires_at > now:
                    out.append(pa)
        out.sort(key=lambda x: x.created_at)
        return out

    def get(self, approval_id: str) -> Optional[PendingApproval]:
        with self._lock:
            return self._pending.get(approval_id)

    def approve(self, approval_id: str, approver_principal: str) -> bool:
        with self._lock:
            pa = self._pending.get(approval_id)
            if not pa:
                return False
            now = time.time()
            if pa.status != "pending":
                return False
            if pa.expires_at <= now:
                pa.status = "expired"
                pa.decision_at = now
                self._decisions[approval_id] = "expired"
                self._events[approval_id].set()
                return False
            pa.status = "approved"
            pa.approver_principal = approver_principal
            pa.decision_at = now
            self._decisions[approval_id] = "approved"
            self._events[approval_id].set()
            return True

    def deny(self, approval_id: str, approver_principal: str) -> bool:
        with self._lock:
            pa = self._pending.get(approval_id)
            if not pa:
                return False
            now = time.time()
            if pa.status != "pending":
                return False
            if pa.expires_at <= now:
                pa.status = "expired"
                pa.decision_at = now
                self._decisions[approval_id] = "expired"
                self._events[approval_id].set()
                return False
            pa.status = "denied"
            pa.approver_principal = approver_principal
            pa.decision_at = now
            self._decisions[approval_id] = "denied"
            self._events[approval_id].set()
            return True

    def wait_for_decision(self, approval_id: str, timeout_seconds: float) -> str:
        # Returns: approved|denied|expired|timeout
        ev = None
        with self._lock:
            ev = self._events.get(approval_id)
        if ev is None:
            return "timeout"
        signaled = ev.wait(timeout=timeout_seconds)
        if not signaled:
            return "timeout"
        with self._lock:
            return self._decisions.get(approval_id, "timeout")

    def mark_executed(self, approval_id: str) -> None:
        with self._lock:
            pa = self._pending.get(approval_id)
            if pa:
                pa.status = "executed"

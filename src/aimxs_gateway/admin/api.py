from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import time

from aimxs_gateway.approval.store import ApprovalStore
from aimxs_gateway.evidence.sink_jsonl import EvidenceSinkJSONL


class ApproveResponse(BaseModel):
    ok: bool
    status: str
    approval_request_id: str


def build_admin_app(
    *,
    store: ApprovalStore,
    evidence: EvidenceSinkJSONL,
    admin_token: str,
    admin_principal: str,
    approver_token: str,
    approver_principal: str,
    capability_check,  # callable(approver_principal, pending_approval) -> (bool, reason)
    separation_of_duties_check,  # callable(approver_principal, pending_approval) -> (bool, reason)
) -> FastAPI:
    app = FastAPI(title="AIMXS Admin API", version="v1")

    def auth_principal(x_aimxs_admin_token: Optional[str]) -> Optional[str]:
        if x_aimxs_admin_token == admin_token:
            return admin_principal
        if x_aimxs_admin_token == approver_token:
            return approver_principal
        return None

    @app.get("/v1/approvals/pending")
    def list_pending(x_aimxs_admin_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        principal = auth_principal(x_aimxs_admin_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        pending = store.list_pending()
        items = []
        for pa in pending:
            items.append({
                "approval_request_id": pa.approval_request_id,
                "tool_name": pa.tool_name,
                "risk_tier": pa.risk_tier,
                "requestor_principal": pa.requestor_principal,
                "time_remaining_seconds": pa.time_remaining(),
                "created_at": pa.created_at,
                "expires_at": pa.expires_at,
            })
        return {"count": len(items), "items": items}

    @app.post("/v1/approvals/{approval_id}/approve")
    def approve(approval_id: str, x_aimxs_admin_token: Optional[str] = Header(default=None)) -> ApproveResponse:
        principal = auth_principal(x_aimxs_admin_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        pa = store.get(approval_id)
        if not pa:
            raise HTTPException(status_code=404, detail="Not found")

        ok_sod, sod_reason = separation_of_duties_check(principal, pa)
        if not ok_sod:
            evidence.emit("approval_rejected", {
                "approval_request_id": pa.approval_request_id,
                "reason": sod_reason,
                "approver_principal": principal,
                "fingerprint": pa.fingerprint,
            })
            raise HTTPException(status_code=403, detail=f"Separation-of-duties: {sod_reason}")

        ok_cap, cap_reason = capability_check(principal, pa)
        if not ok_cap:
            evidence.emit("approval_rejected", {
                "approval_request_id": pa.approval_request_id,
                "reason": cap_reason,
                "approver_principal": principal,
                "fingerprint": pa.fingerprint,
            })
            raise HTTPException(status_code=403, detail=f"Capability: {cap_reason}")

        ok = store.approve(approval_id, principal)
        status = "approved" if ok else (store.get(approval_id).status if store.get(approval_id) else "unknown")
        evidence.emit("approval_granted" if ok else "approval_failed", {
            "approval_request_id": approval_id,
            "approver_principal": principal,
            "status": status,
            "fingerprint": pa.fingerprint,
        })
        return ApproveResponse(ok=ok, status=status, approval_request_id=approval_id)

    @app.post("/v1/approvals/{approval_id}/deny")
    def deny(approval_id: str, x_aimxs_admin_token: Optional[str] = Header(default=None)) -> ApproveResponse:
        principal = auth_principal(x_aimxs_admin_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        pa = store.get(approval_id)
        if not pa:
            raise HTTPException(status_code=404, detail="Not found")

        ok_sod, sod_reason = separation_of_duties_check(principal, pa)
        if not ok_sod:
            evidence.emit("deny_rejected", {
                "approval_request_id": pa.approval_request_id,
                "reason": sod_reason,
                "approver_principal": principal,
                "fingerprint": pa.fingerprint,
            })
            raise HTTPException(status_code=403, detail=f"Separation-of-duties: {sod_reason}")

        ok_cap, cap_reason = capability_check(principal, pa)
        if not ok_cap:
            evidence.emit("deny_rejected", {
                "approval_request_id": pa.approval_request_id,
                "reason": cap_reason,
                "approver_principal": principal,
                "fingerprint": pa.fingerprint,
            })
            raise HTTPException(status_code=403, detail=f"Capability: {cap_reason}")

        ok = store.deny(approval_id, principal)
        status = "denied" if ok else (store.get(approval_id).status if store.get(approval_id) else "unknown")
        evidence.emit("approval_denied" if ok else "deny_failed", {
            "approval_request_id": approval_id,
            "approver_principal": principal,
            "status": status,
            "fingerprint": pa.fingerprint,
        })
        return ApproveResponse(ok=ok, status=status, approval_request_id=approval_id)

    return app

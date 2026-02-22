from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import uvicorn

from aimxs_gateway.config import AppConfig
from aimxs_gateway.evidence.sink_jsonl import EvidenceSinkJSONL
from aimxs_gateway.approval.store import ApprovalStore, PendingApproval
from aimxs_gateway.policy.reference import ReferencePolicyPlugin
from aimxs_gateway.policy.rules import RulePolicyPlugin
from aimxs_gateway.executor.sandbox import SandboxExecutor
from aimxs_gateway.admin.api import build_admin_app
from aimxs_gateway.mcp.stdio_server import StdioMCPServer
from aimxs_gateway.proxy.downstream import DownstreamServer
from aimxs_gateway.proxy.router import ProxyRouter

import threading


_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "forbidden": 4}


def _resolve_command_paths(allowed_cmds):
    common = ["/bin", "/usr/bin"]
    out = {}
    for cmd in allowed_cmds:
        p = shutil.which(cmd)
        if not p:
            for d in common:
                cand = os.path.join(d, cmd)
                if os.path.exists(cand) and os.access(cand, os.X_OK):
                    p = cand
                    break
        if p:
            out[cmd] = p
    return out


def capability_check_factory(cfg: AppConfig):
    allowed_tools = set(cfg.approver_stub.allowed_tools or [])
    max_risk = str(cfg.approver_stub.max_risk_tier or "high").lower()
    max_risk_val = _RISK_ORDER.get(max_risk, 3)

    def capability_check(approver_principal: str, pa: PendingApproval):
        if approver_principal == cfg.admin.admin_principal:
            return True, "OK_ADMIN"

        if approver_principal == cfg.admin.approver_principal:
            if pa.tool_name not in allowed_tools:
                return False, "TOOL_NOT_ALLOWED"
            risk_val = _RISK_ORDER.get(pa.risk_tier, 99)
            if risk_val > max_risk_val:
                return False, "RISK_TOO_HIGH"
            return True, "OK_APPROVER"
        return False, "UNKNOWN_PRINCIPAL"

    return capability_check


def separation_of_duties_check_factory(cfg: AppConfig):
    def sod_check(approver_principal: str, pa: PendingApproval):
        if approver_principal == pa.requestor_principal:
            return False, "NO_SELF_APPROVAL"
        return True, "OK"
    return sod_check


def start_admin_server(cfg: AppConfig, store: ApprovalStore, evidence: EvidenceSinkJSONL) -> threading.Thread:
    capability_check = capability_check_factory(cfg)
    sod_check = separation_of_duties_check_factory(cfg)

    app = build_admin_app(
        store=store,
        evidence=evidence,
        admin_token=cfg.admin.admin_token,
        admin_principal=cfg.admin.admin_principal,
        approver_token=cfg.admin.approver_token,
        approver_principal=cfg.admin.approver_principal,
        capability_check=capability_check,
        separation_of_duties_check=sod_check,
    )

    def run():
        uvicorn.run(app, host=cfg.admin.host, port=cfg.admin.port, log_level="warning")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/prototype.local.yaml", help="Path to YAML config.")
    args = ap.parse_args()

    cfg = AppConfig.load(args.config)

    evidence = EvidenceSinkJSONL(path=Path(cfg.evidence.path))
    approvals = ApprovalStore()

    # Executor only used in demo mode
    resolved = _resolve_command_paths(set(cfg.sandbox.shell_allow) | set(cfg.sandbox.shell_require_approval))
    resolved.update(cfg.sandbox.command_paths or {})
    executor = SandboxExecutor(
        sandbox_dir=Path(cfg.sandbox.dir),
        command_paths=resolved,
        timeout_seconds=float(cfg.sandbox.subprocess_timeout_seconds),
        max_stdout_chars=int(cfg.sandbox.max_stdout_chars),
        max_stderr_chars=int(cfg.sandbox.max_stderr_chars),
        rlimit_cpu_seconds=int(cfg.sandbox.rlimit_cpu_seconds),
        rlimit_fsize_bytes=int(cfg.sandbox.rlimit_fsize_bytes),
        rlimit_as_bytes=int(cfg.sandbox.rlimit_as_bytes),
        rlimit_nproc=int(cfg.sandbox.rlimit_nproc),
        rlimit_nofile=int(cfg.sandbox.rlimit_nofile),
    )

    start_admin_server(cfg, approvals, evidence)

    proxy_router = None
    if cfg.mode == "proxy":
        servers = []
        for ds in cfg.downstream_servers:
            env = None
            if ds.env is not None:
                env = dict(os.environ)
                env.update(ds.env)
            servers.append(DownstreamServer(name=ds.name, command=ds.command, env=env))
        proxy_router = ProxyRouter(servers)
        proxy_router.initialize_all()

        policy = RulePolicyPlugin(
            rules=cfg.rule_policy.rules,
            default_action=cfg.rule_policy.default_action,
            default_risk_tier=cfg.rule_policy.default_risk_tier,
            default_reason_code=cfg.rule_policy.default_reason_code,
        )
    else:
        policy = ReferencePolicyPlugin(
            fs_write_requires_approval=cfg.policy.fs_write_requires_approval,
            shell_allow=cfg.sandbox.shell_allow,
            shell_require_approval=cfg.sandbox.shell_require_approval,
            shell_deny=cfg.sandbox.shell_deny,
        )

    server = StdioMCPServer(
        mode=cfg.mode,
        policy=policy,
        approvals=approvals,
        executor=executor,
        evidence=evidence,
        approval_ttl_seconds=cfg.approval_ttl_seconds,
        proxy_router=proxy_router,
    )
    server.run_forever()


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import yaml


@dataclass
class AdminConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    admin_token: str = "dev_admin_token"
    admin_principal: str = "human_cli"
    approver_token: str = "dev_approver_token"
    approver_principal: str = "approver_stub"


@dataclass
class SandboxConfig:
    dir: str = "./demo_sandbox"
    shell_allow: List[str] = None
    shell_require_approval: List[str] = None
    shell_deny: List[str] = None

    # Optional explicit absolute paths for allowed commands.
    command_paths: Dict[str, str] = None

    # Safety limits for subprocess execution (best effort, POSIX only for rlimits)
    max_stdout_chars: int = 20000
    max_stderr_chars: int = 20000
    subprocess_timeout_seconds: float = 5.0
    rlimit_cpu_seconds: int = 2
    rlimit_fsize_bytes: int = 1_000_000  # 1 MB
    rlimit_as_bytes: int = 512_000_000   # 512 MB
    rlimit_nproc: int = 64
    rlimit_nofile: int = 128

    def __post_init__(self):
        if self.shell_allow is None:
            self.shell_allow = ["ls", "pwd", "echo"]
        if self.shell_require_approval is None:
            self.shell_require_approval = ["cat"]
        if self.shell_deny is None:
            self.shell_deny = ["rm", "sudo", "chmod", "chown", "curl", "wget", "ssh", "scp"]
        if self.command_paths is None:
            self.command_paths = {}


@dataclass
class PolicyConfig:
    # Demo-mode built-in fs.write rule
    fs_write_requires_approval: bool = True


@dataclass
class RulePolicyConfig:
    # Proxy-mode policy rules, matched by glob against *namespaced* tool names:
    #   "<server>:<tool>" e.g., "fs:*", "gh:issues.create"
    rules: List[Dict[str, str]] = None
    default_action: str = "allow"
    default_risk_tier: str = "low"
    default_reason_code: str = "DEFAULT_ALLOW"

    def __post_init__(self):
        if self.rules is None:
            self.rules = []


@dataclass
class EvidenceConfig:
    path: str = "./evidence/evidence.jsonl"


@dataclass
class ApproverStubConfig:
    enabled: bool = False
    poll_interval_seconds: float = 0.5
    allowed_tools: List[str] = None
    max_risk_tier: str = "high"

    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = ["fs.write"]


@dataclass
class DownstreamServerConfig:
    name: str
    command: List[str]
    env: Optional[Dict[str, str]] = None


@dataclass
class AppConfig:
    # demo = built-in sandbox tools; proxy = route to downstream MCP servers
    mode: str = "demo"
    admin: AdminConfig = field(default_factory=AdminConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    rule_policy: RulePolicyConfig = field(default_factory=RulePolicyConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    approver_stub: ApproverStubConfig = field(default_factory=ApproverStubConfig)
    downstream_servers: List[DownstreamServerConfig] = field(default_factory=list)
    approval_ttl_seconds: int = 120

    @staticmethod
    def load(path: str) -> "AppConfig":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        raw = raw or {}

        mode = str(raw.get("mode", "demo")).strip().lower()

        admin = AdminConfig(**(raw.get("admin") or {}))
        sandbox = SandboxConfig(**(raw.get("sandbox") or {}))
        policy = PolicyConfig(**(raw.get("policy") or {}))
        rule_policy = RulePolicyConfig(**(raw.get("rule_policy") or {}))
        evidence = EvidenceConfig(**(raw.get("evidence") or {}))
        approver_stub = ApproverStubConfig(**(raw.get("approver_stub") or {}))
        ttl = int(raw.get("approval_ttl_seconds", 120))

        ds_raw = raw.get("downstream_servers") or []
        downstream_servers: List[DownstreamServerConfig] = []
        for item in ds_raw:
            if not item:
                continue
            downstream_servers.append(
                DownstreamServerConfig(
                    name=str(item.get("name")),
                    command=list(item.get("command") or []),
                    env=dict(item.get("env") or {}) if item.get("env") is not None else None,
                )
            )

        return AppConfig(
            mode=mode,
            admin=admin,
            sandbox=sandbox,
            policy=policy,
            rule_policy=rule_policy,
            evidence=evidence,
            approver_stub=approver_stub,
            downstream_servers=downstream_servers,
            approval_ttl_seconds=ttl,
        )

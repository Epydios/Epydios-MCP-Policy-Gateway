from __future__ import annotations

from typing import Any, Dict, List, Optional
from aimxs_gateway.schemas import DecisionRequest, Decision, DecisionAction, RiskTier
from aimxs_gateway.policy.base import PolicyPlugin


class ReferencePolicyPlugin(PolicyPlugin):
    def __init__(
        self,
        *,
        fs_write_requires_approval: bool,
        shell_allow: List[str],
        shell_require_approval: List[str],
        shell_deny: List[str],
    ):
        self.fs_write_requires_approval = fs_write_requires_approval
        self.shell_allow = set(shell_allow)
        self.shell_require_approval = set(shell_require_approval)
        self.shell_deny = set(shell_deny)

    def evaluate(self, req: DecisionRequest) -> Decision:
        # Basic sandbox escape checks are enforced at executor too,
        # but we also pre-filter here for clarity.
        tool = req.tool_name

        if tool == "fs.write":
            if self.fs_write_requires_approval:
                return Decision(
                    action=DecisionAction.REQUIRE_APPROVAL,
                    risk_tier=RiskTier.HIGH,
                    reason_code="FS_WRITE_REQUIRES_APPROVAL",
                )
            return Decision(
                action=DecisionAction.ALLOW,
                risk_tier=RiskTier.MEDIUM,
                reason_code="FS_WRITE_ALLOWED",
            )

        if tool in ("fs.read", "fs.list"):
            return Decision(
                action=DecisionAction.ALLOW,
                risk_tier=RiskTier.LOW,
                reason_code="FS_READONLY_ALLOWED",
            )

        if tool == "shell.exec":
            argv = req.tool_args.get("argv") or []
            if not isinstance(argv, list) or not argv:
                return Decision(
                    action=DecisionAction.DENY,
                    risk_tier=RiskTier.FORBIDDEN,
                    reason_code="SHELL_INVALID_ARGV",
                )
            cmd = str(argv[0])

            if cmd in self.shell_deny:
                return Decision(
                    action=DecisionAction.DENY,
                    risk_tier=RiskTier.FORBIDDEN,
                    reason_code="SHELL_CMD_DENYLIST",
                    details={"cmd": cmd},
                )

            if cmd in self.shell_allow:
                return Decision(
                    action=DecisionAction.ALLOW,
                    risk_tier=RiskTier.LOW,
                    reason_code="SHELL_CMD_ALLOWLIST",
                    details={"cmd": cmd},
                )

            if cmd in self.shell_require_approval:
                return Decision(
                    action=DecisionAction.REQUIRE_APPROVAL,
                    risk_tier=RiskTier.MEDIUM,
                    reason_code="SHELL_CMD_REQUIRES_APPROVAL",
                    details={"cmd": cmd},
                )

            # Default: deny unknown commands in this reference policy.
            return Decision(
                action=DecisionAction.DENY,
                risk_tier=RiskTier.FORBIDDEN,
                reason_code="SHELL_CMD_NOT_ALLOWED_V1",
                details={"cmd": cmd},
            )

        return Decision(
            action=DecisionAction.DENY,
            risk_tier=RiskTier.FORBIDDEN,
            reason_code="UNKNOWN_TOOL",
            details={"tool": tool},
        )

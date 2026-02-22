from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Dict, List

from aimxs_gateway.schemas import DecisionRequest, Decision, DecisionAction, RiskTier
from aimxs_gateway.policy.base import PolicyPlugin

_ACTION = {
    "allow": DecisionAction.ALLOW,
    "deny": DecisionAction.DENY,
    "require_approval": DecisionAction.REQUIRE_APPROVAL,
}

_TIER = {
    "low": RiskTier.LOW,
    "medium": RiskTier.MEDIUM,
    "high": RiskTier.HIGH,
    "forbidden": RiskTier.FORBIDDEN,
}


@dataclass
class RulePolicyPlugin(PolicyPlugin):
    rules: List[Dict[str, str]]
    default_action: str = "allow"
    default_risk_tier: str = "low"
    default_reason_code: str = "DEFAULT_ALLOW"

    def evaluate(self, req: DecisionRequest) -> Decision:
        tool = req.tool_name
        for r in self.rules or []:
            pat = str(r.get("match", "")).strip()
            if not pat:
                continue
            if fnmatch(tool, pat):
                action = _ACTION.get(str(r.get("action", "allow")).lower(), DecisionAction.ALLOW)
                tier = _TIER.get(str(r.get("risk_tier", "low")).lower(), RiskTier.LOW)
                reason = str(r.get("reason_code") or f"RULE_{pat}")
                return Decision(action=action, risk_tier=tier, reason_code=reason, details={"match": pat})
        action = _ACTION.get(str(self.default_action).lower(), DecisionAction.ALLOW)
        tier = _TIER.get(str(self.default_risk_tier).lower(), RiskTier.LOW)
        return Decision(action=action, risk_tier=tier, reason_code=str(self.default_reason_code))

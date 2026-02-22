from __future__ import annotations

import unittest
from pathlib import Path

from aimxs_gateway.config import AppConfig
from aimxs_gateway.policy.reference import ReferencePolicyPlugin
from aimxs_gateway.policy.rules import RulePolicyPlugin
from aimxs_gateway.schemas import DecisionAction, DecisionRequest


ROOT = Path(__file__).resolve().parents[1]


def _req(tool_name: str, tool_args: dict) -> DecisionRequest:
    return DecisionRequest(
        session_id="s1",
        request_id="r1",
        requestor_principal="user",
        tool_name=tool_name,
        tool_args=tool_args,
        posture="interactive",
        nonce="n1",
    )


class TestConfigLoad(unittest.TestCase):
    def test_load_prototype_config(self):
        cfg = AppConfig.load(str(ROOT / "config" / "prototype.local.yaml"))
        self.assertEqual(cfg.mode, "demo")
        self.assertEqual(cfg.admin.admin_token, "dev_admin_token")
        self.assertTrue(cfg.policy.fs_write_requires_approval)
        self.assertEqual(cfg.evidence.path, "./evidence/evidence.jsonl")

    def test_load_proxy_config(self):
        cfg = AppConfig.load(str(ROOT / "config" / "proxy.yaml"))
        self.assertEqual(cfg.mode, "proxy")
        self.assertGreaterEqual(len(cfg.downstream_servers), 1)
        self.assertEqual(cfg.downstream_servers[0].name, "echo")


class TestReferencePolicySmoke(unittest.TestCase):
    def setUp(self):
        self.p = ReferencePolicyPlugin(
            fs_write_requires_approval=True,
            shell_allow=["ls", "pwd", "echo"],
            shell_require_approval=["cat"],
            shell_deny=["rm", "sudo"],
        )

    def test_fs_write_requires_approval(self):
        d = self.p.evaluate(_req("fs.write", {"path": "x.txt", "content": "hi"}))
        self.assertEqual(d.action, DecisionAction.REQUIRE_APPROVAL)

    def test_shell_allow(self):
        d = self.p.evaluate(_req("shell.exec", {"argv": ["echo", "hi"]}))
        self.assertEqual(d.action, DecisionAction.ALLOW)

    def test_shell_deny(self):
        d = self.p.evaluate(_req("shell.exec", {"argv": ["rm", "-rf", "/"]}))
        self.assertEqual(d.action, DecisionAction.DENY)


class TestRulePolicySmoke(unittest.TestCase):
    def test_rule_match(self):
        p = RulePolicyPlugin(
            rules=[{"match": "echo:*", "action": "require_approval", "risk_tier": "high", "reason_code": "ECHO_STEPUP"}],
            default_action="allow",
            default_risk_tier="low",
            default_reason_code="DEFAULT_ALLOW",
        )
        d = p.evaluate(_req("echo:echo.upper", {"text": "abc"}))
        self.assertEqual(d.action, DecisionAction.REQUIRE_APPROVAL)
        self.assertEqual(d.reason_code, "ECHO_STEPUP")

    def test_rule_default(self):
        p = RulePolicyPlugin(rules=[])
        d = p.evaluate(_req("other:tool", {}))
        self.assertEqual(d.action, DecisionAction.ALLOW)


if __name__ == "__main__":
    unittest.main()

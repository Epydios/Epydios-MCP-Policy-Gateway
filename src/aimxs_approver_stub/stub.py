from __future__ import annotations

import argparse
import time
import requests
from aimxs_gateway.config import AppConfig

_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "forbidden": 4}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/prototype.local.yaml", help="Path to YAML config.")
    ap.add_argument("--admin-url", default=None, help="Override admin url, e.g. http://127.0.0.1:8787")
    args = ap.parse_args()

    cfg = AppConfig.load(args.config)
    if not cfg.approver_stub.enabled:
        print("Approver stub is disabled by default. Set approver_stub.enabled: true in config to run.")
        return

    admin_url = args.admin_url or f"http://{cfg.admin.host}:{cfg.admin.port}"
    token = cfg.admin.approver_token
    headers = {"X-AIMXS-ADMIN-TOKEN": token}

    allowed_tools = set(cfg.approver_stub.allowed_tools or [])
    max_risk = str(cfg.approver_stub.max_risk_tier or "high").lower()
    max_risk_val = _RISK_ORDER.get(max_risk, 3)

    while True:
        try:
            r = requests.get(f"{admin_url}/v1/approvals/pending", headers=headers, timeout=5)
            if r.status_code == 401:
                print("Unauthorized to poll approvals. Check approver token.")
                time.sleep(2)
                continue
            r.raise_for_status()
            items = r.json().get("items", [])
            for item in items:
                aid = item["approval_request_id"]
                tool = item["tool_name"]
                risk = item["risk_tier"]
                risk_val = _RISK_ORDER.get(risk, 99)

                if tool not in allowed_tools or risk_val > max_risk_val:
                    # deterministic deny
                    requests.post(f"{admin_url}/v1/approvals/{aid}/deny", headers=headers, timeout=5)
                    print(f"Denied {aid} tool={tool} risk={risk}")
                else:
                    requests.post(f"{admin_url}/v1/approvals/{aid}/approve", headers=headers, timeout=5)
                    print(f"Approved {aid} tool={tool} risk={risk}")

            time.sleep(float(cfg.approver_stub.poll_interval_seconds))
        except Exception as e:
            print(f"Approver stub error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()

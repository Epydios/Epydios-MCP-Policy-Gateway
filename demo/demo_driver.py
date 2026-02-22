from __future__ import annotations

import subprocess
import json
import time
import requests
import os
import sys
from pathlib import Path

ADMIN_URL = "http://127.0.0.1:8787"
ADMIN_TOKEN = "dev_admin_token"

def send(proc, obj):
    proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
    proc.stdin.flush()
    line = proc.stdout.readline().decode("utf-8").strip()
    if not line:
        return None
    return json.loads(line)

def main():
    # Launch gateway as a subprocess
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    proc = subprocess.Popen(
        [sys.executable, "-m", "aimxs_gateway.main", "--config", "config/prototype.local.yaml"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=False,
        env=env,
    )

    try:
        # Initialize
        resp = send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        print("initialize:", resp)

        # List tools
        resp = send(proc, {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        print("tools/list:", [t["name"] for t in resp["result"]["tools"]])

        # 1) Deny example: rm -rf /
        resp = send(proc, {
            "jsonrpc":"2.0","id":3,"method":"tools/call",
            "params":{"name":"shell.exec","arguments":{"argv":["rm","-rf","/"]}}
        })
        print("deny rm:", resp["result"]["content"][0]["text"])

        # 2) Approval-required: fs.write
        # This call will block until approved (or TTL).
        # Run it in a non-blocking way by spawning another thread-like pattern:
        # We'll just approve quickly before reading its output by polling pending approvals first.
        # In practice, the gateway is blocked waiting, so we need to approve in parallel.
        # We'll do it by launching the request, then in another process, approve.
        # For simplicity in this script, we launch a second gateway call after creating approval.
        # NOTE: This driver is "best effort" and meant as a guide.
        print("Triggering approval-required fs.write ...")
        proc.stdin.write((json.dumps({
            "jsonrpc":"2.0","id":4,"method":"tools/call",
            "params":{"name":"fs.write","arguments":{"path":"hello.txt","content":"Hello from AIMXS v1\n","mode":"overwrite"}}
        }) + "\n").encode("utf-8"))
        proc.stdin.flush()

        # Wait for approval to appear
        time.sleep(0.4)
        r = requests.get(f"{ADMIN_URL}/v1/approvals/pending", headers={"X-AIMXS-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=5)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            print("No pending approvals found (unexpected).")
        else:
            aid = items[0]["approval_request_id"]
            print("Approving:", aid)
            requests.post(f"{ADMIN_URL}/v1/approvals/{aid}/approve", headers={"X-AIMXS-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=5)

        # Read the result for id=4
        line = proc.stdout.readline().decode("utf-8").strip()
        resp = json.loads(line)
        print("fs.write result:", resp["result"]["content"][0]["text"])

        # 3) Allow example: fs.list
        resp = send(proc, {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"fs.list","arguments":{"path":"."}}})
        print("fs.list:", resp["result"]["content"][0]["text"])

        print("\nEvidence written to ./evidence/evidence.jsonl")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    main()

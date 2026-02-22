from __future__ import annotations

import subprocess
import json
import os
import sys
from pathlib import Path

def send(proc, obj):
    proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
    proc.stdin.flush()
    line = proc.stdout.readline().decode("utf-8").strip()
    if not line:
        return None
    return json.loads(line)

def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    proc = subprocess.Popen(
        [sys.executable, "-m", "aimxs_gateway.main", "--config", "config/proxy.yaml"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=False,
        env=env,
    )

    try:
        resp = send(proc, {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        print("initialize:", resp)

        resp = send(proc, {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        tools = [t["name"] for t in resp["result"]["tools"]]
        print("tools/list:", tools)

        resp = send(proc, {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo:echo.upper","arguments":{"text":"hello proxy"}}})
        print("echo.upper:", resp["result"]["content"][0]["text"])
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    main()

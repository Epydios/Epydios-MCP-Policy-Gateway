from __future__ import annotations

import sys
import json

SERVER_NAME = "downstream-echo"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "echo.upper",
        "description": "Uppercase a string.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "echo.lower",
        "description": "Lowercase a string.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict) or "method" not in msg:
            continue

        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        if method == "initialize":
            send({"jsonrpc":"2.0","id":mid,"result":{"serverInfo":{"name":SERVER_NAME,"version":SERVER_VERSION},"capabilities":{"tools":True}}})
        elif method == "tools/list":
            send({"jsonrpc":"2.0","id":mid,"result":{"tools":TOOLS}})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "echo.upper":
                out = str(args.get("text","")).upper()
                send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":out}]}})
            elif name == "echo.lower":
                out = str(args.get("text","")).lower()
                send({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":out}]}})
            else:
                send({"jsonrpc":"2.0","id":mid,"error":{"code":-32602,"message":"Unknown tool"}})
        else:
            send({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"Method not found"}})

if __name__ == "__main__":
    main()

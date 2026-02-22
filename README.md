# Epydios MCP Policy Gateway (AIMXS, Python)

A runnable MCP (stdio) gateway/server for boundary-enforced tool execution with:
- Allow / Deny
- Step-up approval (2-minute TTL) via local CLI
- Append-only evidence logging (JSONL audit trail)
- Optional deterministic AgentApprover stub (disabled by default)
- Separation of duties (no self-approval, capability-limited approver token)

## Quickstart

### Option A (no packaging, fastest)
```bash
pip install -r requirements.txt
export PYTHONPATH=src
python -m aimxs_gateway.main --config config/prototype.local.yaml
```

CLI (in another terminal):
```bash
export PYTHONPATH=src
python -m aimxs_cli.cli approvals --admin-url http://127.0.0.1:8787 --admin-token dev_admin_token
python -m aimxs_cli.cli approve <approval_id> --admin-url http://127.0.0.1:8787 --admin-token dev_admin_token
```

### Option B (editable install)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
aimxs-gateway --config config/prototype.local.yaml
```

## Local validation driver (optional)

A simple local JSON-RPC driver is provided for validation and walkthroughs:
```bash
python demo/demo_driver.py
```

It launches the gateway as a subprocess, proposes tool calls, triggers step-up, then approves via the admin API. This is a validation harness, not a production deployment path.

## Tools exposed (MCP)
- `shell.exec`  (sandboxed, allowlist-based)
- `fs.list`     (sandboxed)
- `fs.read`     (sandboxed)
- `fs.write`    (sandboxed; default requires approval)

Append-only evidence (audit trail) logs are written to the path configured in `config/prototype.local.yaml` (default: `./evidence/evidence.jsonl`). This is an operational audit trail format (JSONL), not a cryptographically immutable log.

## Operational notes
- Not production-ready: this repository is a working prototype / reference implementation for evaluation and integration design.
- Sample config tokens are local development placeholders and must be changed before any non-local or shared use.

## Sandboxing

### Built-in sandbox (default local mode)
- Forced sandbox working directory (`demo_sandbox/`)
- Explicit command allowlist with resolved absolute paths
- No `shell=True`
- Timeout per tool call
- Best-effort POSIX rlimits (CPU, file size, memory, processes, open files)
- Blocks absolute paths, `~`, and `..` in argv arguments

### Docker sandbox (optional)
If you have Docker installed, you can run the gateway inside a locked-down container:
```bash
./scripts/run_docker_sandbox.sh
```
This runs with `--network none`, a read-only root filesystem, dropped capabilities, and only binds `evidence/` and `demo_sandbox/` as writable.

## Tests and CI

This repo includes lightweight smoke tests and a GitHub Actions CI workflow (`.github/workflows/ci.yml`) that:
- installs dependencies
- installs the package in editable mode
- compiles `src/` and `demo/`
- runs `unittest` smoke tests

Run locally:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
```

## Proxy mode (gateway between client and one or more MCP servers)

In `mode: proxy`, the gateway is an MCP server to the client and an MCP client to one or more downstream MCP servers:

Client ⇄ (AIMXS Gateway) ⇄ Downstream MCP Server(s)

- `tools/list` is merged across downstream servers with namespaced tool names: `<server>:<tool>`
- `tools/call` is intercepted, evaluated by policy, then routed to the correct downstream server
- allow/deny/step-up decisions and proxied execution outcomes are recorded in the append-only evidence log (audit trail)

### Run the proxy demo
This repo includes a tiny downstream MCP server (`demo/downstream_echo_server.py`) so you can test proxy routing without any external dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

python3 demo/proxy_demo_driver.py
```

To use real MCP servers, edit `config/proxy.yaml` and replace `downstream_servers`.

from __future__ import annotations

import typer
import requests
from typing import Optional

app = typer.Typer(add_completion=False, help="AIMXS CLI approver (v1).")


def _headers(token: str):
    return {"X-AIMXS-ADMIN-TOKEN": token}


@app.command("approvals")
def approvals(admin_url: str = typer.Option("http://127.0.0.1:8787", help="Admin API base URL"),
              admin_token: str = typer.Option(..., help="Admin token")):
    r = requests.get(f"{admin_url}/v1/approvals/pending", headers=_headers(admin_token), timeout=5)
    r.raise_for_status()
    data = r.json()
    typer.echo(f"Pending approvals: {data.get('count', 0)}")
    for item in data.get("items", []):
        typer.echo(f"- {item['approval_request_id']} tool={item['tool_name']} risk={item['risk_tier']} "
                   f"requestor={item['requestor_principal']} ttl={item['time_remaining_seconds']:.1f}s")


@app.command("approve")
def approve(approval_id: str,
            admin_url: str = typer.Option("http://127.0.0.1:8787", help="Admin API base URL"),
            admin_token: str = typer.Option(..., help="Admin token")):
    r = requests.post(f"{admin_url}/v1/approvals/{approval_id}/approve", headers=_headers(admin_token), timeout=5)
    if r.status_code >= 400:
        typer.echo(f"ERROR {r.status_code}: {r.text}")
        raise typer.Exit(code=1)
    data = r.json()
    typer.echo(f"Approved: {data}")


@app.command("deny")
def deny(approval_id: str,
         admin_url: str = typer.Option("http://127.0.0.1:8787", help="Admin API base URL"),
         admin_token: str = typer.Option(..., help="Admin token")):
    r = requests.post(f"{admin_url}/v1/approvals/{approval_id}/deny", headers=_headers(admin_token), timeout=5)
    if r.status_code >= 400:
        typer.echo(f"ERROR {r.status_code}: {r.text}")
        raise typer.Exit(code=1)
    data = r.json()
    typer.echo(f"Denied: {data}")

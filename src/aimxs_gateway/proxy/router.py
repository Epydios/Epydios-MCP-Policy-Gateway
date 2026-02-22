from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from aimxs_gateway.proxy.downstream import DownstreamServer, DownstreamError


@dataclass
class ToolRoute:
    server_name: str
    downstream_tool_name: str


class ProxyRouter:
    def __init__(self, servers: List[DownstreamServer]):
        self.servers = {s.name: s for s in servers}
        self.tool_map: Dict[str, ToolRoute] = {}  # namespaced -> route

    def initialize_all(self) -> None:
        for s in self.servers.values():
            s.start()
            s.initialize()

    def build_tools_catalog(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        self.tool_map.clear()

        for server_name, s in self.servers.items():
            result = s.tools_list()
            for t in result.get("tools", []) or []:
                dn = t.get("name")
                if not isinstance(dn, str):
                    continue
                namespaced = f"{server_name}:{dn}"
                self.tool_map[namespaced] = ToolRoute(server_name=server_name, downstream_tool_name=dn)

                tt = dict(t)
                tt["name"] = namespaced
                tt["description"] = f"[{server_name}] " + str(tt.get("description") or "")
                tools.append(tt)

        tools.sort(key=lambda x: x.get("name", ""))
        return tools

    def route_call(self, namespaced_tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        route = self.tool_map.get(namespaced_tool_name)
        if not route:
            # fallback: parse server:tool if not in cache
            if ":" in namespaced_tool_name:
                server_name, dn = namespaced_tool_name.split(":", 1)
                s = self.servers.get(server_name)
                if not s:
                    raise DownstreamError("Unknown server")
                return s.tools_call(dn, arguments or {})
            raise DownstreamError("Unknown tool")
        s = self.servers.get(route.server_name)
        if not s:
            raise DownstreamError("Server not available")
        return s.tools_call(route.downstream_tool_name, arguments or {})

"""MCP 业务逻辑层。

直接调用 ModelScope MCP REST API，使用 httpx 异步客户端。
"""
import logging
from typing import Any, Dict

import httpx

from src.common.config import settings
from .models import (
    MCPSearchRequest,
    MCPSearchResponse,
    MCPServerDetail,
    MCPServerInfo,
)

logger = logging.getLogger(__name__)

MCP_API_BASE = "https://modelscope.cn/openapi/v1/mcp/servers"


class MCPService:
    """MCP 搜索服务类。"""

    def __init__(self) -> None:
        self._token = settings.modelscope_api_token

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def search(self, req: MCPSearchRequest) -> MCPSearchResponse:
        """搜索 MCP 服务。"""
        body = {
            "filter": {},
            "page_number": 1,
            "page_size": req.total_count,
            "search": req.query or "",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.put(
                    MCP_API_BASE, headers=self._headers(), json=body
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error("MCP 搜索失败: %s", e)
            raise RuntimeError(f"MCP 搜索失败: {e}") from e

        if not data.get("success"):
            raise RuntimeError("MCP API 返回失败状态")

        payload = data.get("data", {})
        servers = [
            MCPServerInfo(
                id=s.get("id", ""),
                name=s.get("name", "未命名"),
                description=s.get("description", ""),
                url=f"https://www.modelscope.cn/mcp/{s.get('id', '')}",
            )
            for s in payload.get("mcp_server_list", [])
        ]

        return MCPSearchResponse(servers=servers, total=payload.get("total_count", 0))

    async def get_server(self, server_id: str) -> MCPServerDetail:
        """获取单个 MCP 服务详情。"""
        url = f"{MCP_API_BASE}/{server_id}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers=self._headers(),
                    params={"get_operational_url": "true"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error("MCP 获取详情失败: %s", e)
            raise RuntimeError(f"MCP 获取详情失败: {e}") from e

        if not data.get("success"):
            raise RuntimeError("MCP API 返回失败状态")

        payload = data.get("data", {})
        servers = [
            {"type": (u.get("url") or "").split("/")[-1] or "unknown", "url": u.get("url", "")}
            for u in payload.get("operational_urls", [])
        ]

        return MCPServerDetail(
            id=payload.get("id", server_id),
            name=payload.get("name", "未命名"),
            description=payload.get("description", ""),
            url=f"https://www.modelscope.cn/mcp/{payload.get('id', server_id)}",
            servers=servers,
        )

    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "module": "mcp", "token_set": bool(self._token)}

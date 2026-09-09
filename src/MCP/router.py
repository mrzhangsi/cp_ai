"""MCP API 路由模块。

定义 MCP 市场相关接口，前缀为 /mcp。
所有接口需要 JWT 认证（健康检查除外）。
"""
from fastapi import APIRouter, Depends, Query

from .dependencies import check_token_blacklist, get_current_user
from .models import MCPHealthResponse, MCPSearchRequest, MCPSearchResponse, MCPServerDetail
from .service import MCPService

router = APIRouter(prefix="/mcp", tags=["MCP"])

_service: MCPService = None


def init_service(service: MCPService) -> None:
    """初始化服务实例，注入到路由模块。

    Args:
        service: MCPService 业务逻辑实例。
    """
    global _service
    _service = service


@router.post("/search", response_model=MCPSearchResponse)
async def search_mcp_servers(
    req: MCPSearchRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """搜索 ModelScope MCP 服务。

    Args:
        req: 搜索请求体。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        搜索结果。
    """
    return await _service.search(req)


@router.get("/server", response_model=MCPServerDetail)
async def get_mcp_server(
    server_id: str = Query(..., description="服务唯一标识（@group/name）"),
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """获取单个 MCP 服务详情。

    Args:
        server_id: 服务唯一标识（@group/name）。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        服务详情。
    """
    return await _service.get_server(server_id)


@router.get("/health", response_model=MCPHealthResponse)
def health_check_api():
    """健康检查接口。"""
    return _service.health_check()

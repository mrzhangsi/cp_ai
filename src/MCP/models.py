"""MCP 模块 Pydantic 请求/响应模型。"""
from typing import List, Optional

from pydantic import BaseModel, Field


class MCPServerEndpoint(BaseModel):
    """MCP 服务端点模型。

    Attributes:
        type: 端点类型（sse / streamable_http）。
        url: 端点地址。
    """

    type: str = Field(..., description="端点类型")
    url: str = Field(..., description="端点地址")


class MCPServerInfo(BaseModel):
    """MCP 服务信息模型（列表用）。

    Attributes:
        id: 服务唯一标识（@group/name）。
        name: 服务名称。
        description: 服务描述。
        url: ModelScope 平台页面地址。
    """

    id: str = Field(..., description="服务唯一标识")
    name: str = Field(..., description="服务名称")
    description: str = Field("", description="服务描述")
    url: str = Field("", description="平台页面地址")


class MCPServerDetail(BaseModel):
    """MCP 服务详情模型。

    Attributes:
        id: 服务唯一标识。
        name: 服务名称。
        description: 服务描述。
        url: ModelScope 平台页面地址。
        servers: 可调用端点列表。
    """

    id: str = Field(..., description="服务唯一标识")
    name: str = Field(..., description="服务名称")
    description: str = Field("", description="服务描述")
    url: str = Field("", description="平台页面地址")
    servers: List[MCPServerEndpoint] = Field(default_factory=list, description="可调用端点列表")


class MCPSearchRequest(BaseModel):
    """MCP 搜索请求模型。

    Attributes:
        query: 搜索关键词，可选。
        total_count: 返回数量，1-100，默认 20。
    """

    query: Optional[str] = Field(None, description="搜索关键词")
    total_count: int = Field(20, ge=1, le=100, description="返回数量")


class MCPSearchResponse(BaseModel):
    """MCP 搜索响应模型。

    Attributes:
        servers: MCP 服务列表。
        total: 总数。
    """

    servers: List[MCPServerInfo] = Field(default_factory=list, description="MCP 服务列表")
    total: int = Field(0, description="总数")


class MCPHealthResponse(BaseModel):
    """MCP 模块健康检查响应模型。

    Attributes:
        status: 服务状态。
        module: 模块名称。
        token_set: 是否已配置 Token。
    """

    status: str = Field(..., description="服务状态")
    module: str = Field(..., description="模块名称")
    token_set: bool = Field(False, description="是否已配置 Token")

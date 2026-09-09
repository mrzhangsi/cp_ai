"""RAG 模块依赖注入层。

包装 common 模块提供的公共依赖，确保模块内其它文件
不需要直接导入 src.common，统一通过本文件获取所有依赖。

使用方式:
    from .dependencies import Settings, get_current_user, QueryRequest, ...
"""
from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from src.common.redis.token_blacklist import TokenBlacklist

# ==================== 类型/类 ====================

from src.common.config import Settings
from src.common.models import (
    QueryRequest,
    QueryResponse,
    SourceNode,
    RAGASResult,
    HealthResponse,
)

# ==================== DI 函数 ====================

from src.common.dependencies import (
    get_settings as _get_settings,
    get_current_user as _get_current_user,
    get_token_blacklist as _get_token_blacklist,
    check_token_blacklist as _check_token_blacklist,
    get_db as _get_db,
    get_auth_tools as _get_auth_tools,
    oauth2_scheme,
)

from src.common.auth_tools import AuthTools


def get_settings() -> Settings:
    """获取全局配置实例。"""
    return _get_settings()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(_get_db),
    auth_tools: AuthTools = Depends(_get_auth_tools),
    settings: Settings = Depends(_get_settings),
):
    """从 Bearer Token 解析当前登录用户。"""
    return _get_current_user(token, db, auth_tools, settings)


def get_token_blacklist() -> TokenBlacklist:
    """获取 Token 黑名单操作实例。"""
    return _get_token_blacklist()


def check_token_blacklist(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
):
    """独立的 Token 黑名单检查。"""
    return _check_token_blacklist(token, settings)

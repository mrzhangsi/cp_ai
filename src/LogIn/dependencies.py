"""登录模块依赖注入层。

包装 common 模块提供的公共依赖，确保模块内其它文件
不需要直接导入 src.common，统一通过本文件获取所有依赖。

使用方式:
    from .dependencies import get_db, get_current_user, Settings, ...
"""
from typing import Any, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

# ==================== 类型/类 ====================

from src.common.config import Settings
from src.common.models import Token, UserCreate
from src.common.database.mysql.models import User
from src.common.auth_tools import AuthTools
from src.common.redis.token_blacklist import TokenBlacklist
from src.common.redis.user_cache import UserCache
from src.common.utils import check_rate_limit

# ==================== DI 函数 ====================

from src.common.dependencies import (
    get_settings as _get_settings,
    get_auth_tools as _get_auth_tools,
    get_client_ip as _get_client_ip,
    get_pwd_context as _get_pwd_context,
    get_db as _get_db,
    get_current_user as _get_current_user,
    get_current_token as _get_current_token,
    get_token_blacklist as _get_token_blacklist,
    get_user_cache as _get_user_cache,
    get_redis_client as _get_redis_client,
    check_token_blacklist as _check_token_blacklist,
    oauth2_scheme,
)


def get_settings() -> Settings:
    """获取全局配置实例。"""
    return _get_settings()


def get_auth_tools() -> AuthTools:
    """获取认证工具实例。"""
    return _get_auth_tools()


def get_client_ip(request: Request) -> str:
    """从请求中提取客户端 IP 地址。"""
    return _get_client_ip(request)


def get_pwd_context(settings: Settings = Depends(get_settings)) -> Any:
    """创建密码加密上下文。"""
    return _get_pwd_context(settings)


def get_db(
    settings: Settings = Depends(get_settings),
) -> Generator[Session, None, None]:
    """创建并 yield 数据库 Session，用完自动关闭。"""
    yield from _get_db(settings)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    auth_tools: AuthTools = Depends(get_auth_tools),
    settings: Settings = Depends(get_settings),
) -> User:
    """从 Bearer Token 解析当前登录用户。"""
    return _get_current_user(token, db, auth_tools, settings)


def get_current_token(request: Request) -> str:
    """从 Authorization header 提取原始 Token 字符串。"""
    return _get_current_token(request)


def get_token_blacklist() -> TokenBlacklist:
    """获取 Token 黑名单操作实例。"""
    return _get_token_blacklist()


def get_user_cache() -> UserCache:
    """获取用户信息缓存操作实例。"""
    return _get_user_cache()


def get_redis_client() -> Any:
    """获取全局 Redis 客户端实例（用于限流等场景）。"""
    return _get_redis_client()


def check_token_blacklist(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """独立的 Token 黑名单检查。"""
    return _check_token_blacklist(token, settings)

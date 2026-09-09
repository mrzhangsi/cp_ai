"""API 路由模块。

定义所有认证相关接口，前缀为 /auth。
路由层只负责接收请求、注入依赖、调用 Service 方法并返回响应。
"""
from typing import List

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .dependencies import (
    Token,
    UserCreate,
    get_auth_tools,
    get_client_ip,
    get_current_token,
    get_current_user,
    get_db,
    get_pwd_context,
    get_settings,
    get_token_blacklist,
    get_user_cache,
    get_redis_client,
)
from .service import Service

router = APIRouter(prefix="/auth", tags=["authentication"])

# 全局服务实例（由 main.py 注入）
_service: Service = None


def init_service(service: Service) -> None:
    """初始化服务实例，注入到路由模块。

    Args:
        service: Service 业务逻辑实例。
    """
    global _service
    _service = service


@router.post("/register", response_model=List[Token])
def register_api(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    auth_tools=Depends(get_auth_tools),
    pwd_context=Depends(get_pwd_context),
    settings=Depends(get_settings),
) -> List[Token]:
    """用户注册接口。

    创建新用户账号并返回 access_token 和 refresh_token。

    Args:
        user_data: 注册请求体（username, password, email）。
        db: 数据库 Session。
        auth_tools: 认证工具。
        pwd_context: 密码加密上下文。
        settings: 全局配置。

    Returns:
        Token 列表。
    """
    return _service.register(user_data, db, auth_tools, pwd_context, settings)


@router.post("/login", response_model=List[Token])
def login_api(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    ip: str = Depends(get_client_ip),
    auth_tools=Depends(get_auth_tools),
    pwd_context=Depends(get_pwd_context),
    settings=Depends(get_settings),
    user_cache=Depends(get_user_cache),
    redis_client=Depends(get_redis_client),
) -> List[Token]:
    """用户登录接口。

    支持用户名或邮箱登录，返回 access_token 和 refresh_token。
    Swagger UI 中可直接使用此接口进行 Bearer Token 认证。

    Args:
        form_data: OAuth2 表单数据（username, password）。
        db: 数据库 Session。
        ip: 客户端 IP。
        auth_tools: 认证工具。
        pwd_context: 密码加密上下文。
        settings: 全局配置。
        user_cache: 用户信息缓存实例。
        redis_client: Redis 客户端实例（用于限流）。

    Returns:
        Token 列表。
    """
    return _service.login(form_data, db, ip, auth_tools, pwd_context, settings, user_cache, redis_client)


@router.post("/refresh", response_model=List[Token])
def refresh_token_api(
    refresh_data: Token,
    auth_tools=Depends(get_auth_tools),
    settings=Depends(get_settings),
) -> List[Token]:
    """刷新 Token 接口。

    使用 refresh_token 获取新的 access_token 和 refresh_token。

    Args:
        refresh_data: 包含 refresh_token 的请求体。
        auth_tools: 认证工具。
        settings: 全局配置。

    Returns:
        新的 Token 列表。
    """
    return _service.refresh_token(refresh_data, auth_tools, settings)


@router.post("/logout", response_model=dict)
def logout_api(
    current_user=Depends(get_current_user),
    token: str = Depends(get_current_token),
    blacklist=Depends(get_token_blacklist),
    settings=Depends(get_settings),
    user_cache=Depends(get_user_cache),
) -> dict:
    """退出登录接口。

    需要 Bearer Token 认证。将当前 Token 加入黑名单使其立即失效。

    Args:
        current_user: 当前登录用户（自动注入）。
        token: 当前 Token 字符串（自动提取）。
        blacklist: Token 黑名单操作实例（自动注入）。
        settings: 全局配置（自动注入）。
        user_cache: 用户信息缓存实例（自动注入）。

    Returns:
        退出成功提示。
    """
    return _service.logout(current_user, token, blacklist, settings, user_cache)


@router.get("/me", response_model=dict)
def get_me_api(current_user=Depends(get_current_user)) -> dict:
    """获取当前用户信息接口。

    需要 Bearer Token 认证，返回用户基本信息。

    Args:
        current_user: 当前登录用户（自动注入）。

    Returns:
        用户信息字典。
    """
    return _service.get_me(current_user)


@router.get("/health", response_model=dict)
def health_check_api() -> dict:
    """健康检查接口。

    无需认证，用于监控服务存活状态。

    Returns:
        服务状态信息。
    """
    return _service.health_check()

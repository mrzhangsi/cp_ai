"""公共依赖注入模块。

集中管理所有路由依赖项，包括数据库 Session、认证工具、
配置管理、密码上下文、Redis、Token 黑名单等。通过 Depends 注入到路由函数中。
"""
from typing import Any, Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .auth_tools import AuthTools
from .config import Settings, settings
from .database.mysql.engine import MySQLDatabase
from .database.mysql.models import User
from .redis.client import RedisClient
from .redis.token_blacklist import TokenBlacklist
from .redis.user_cache import UserCache


# ==================== Redis 全局实例 ====================

_redis_client: Optional[RedisClient] = None


def _get_redis_client() -> RedisClient:
    """获取全局 Redis 客户端实例（懒加载单例）。

    Returns:
        RedisClient 实例。
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(settings.redis_url)
        _redis_client.connect()
    return _redis_client


# ==================== DI 函数 ====================


def get_settings() -> Settings:
    """获取全局配置实例（模块级单例）。

    Returns:
        Settings 配置实例。
    """
    return settings


def get_auth_tools() -> AuthTools:
    """获取认证工具实例。

    Returns:
        AuthTools 实例。
    """
    return AuthTools()


def get_client_ip(request: Request) -> str:
    """从请求中提取客户端 IP 地址。

    Args:
        request: FastAPI Request 对象。

    Returns:
        客户端 IP 地址字符串，无法获取时返回 "unknown"。
    """
    if request.client is None:
        return "unknown"
    return request.client.host


def get_pwd_context(settings: Settings = Depends(get_settings)) -> Any:
    """创建密码加密上下文。

    Args:
        settings: 全局配置实例。

    Returns:
        passlib CryptContext 实例。
    """
    from passlib.context import CryptContext
    return CryptContext(schemes=settings.schemes, deprecated="auto")


# OAuth2 密码流（自动生成 Swagger UI 认证入口）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db(
    settings: Settings = Depends(get_settings),
) -> Generator[Session, None, None]:
    """创建并 yield MySQL 数据库 Session，用完自动关闭。

    Args:
        settings: 全局配置实例。

    Yields:
        SQLAlchemy 数据库 Session。
    """
    mysql_db = MySQLDatabase()
    if mysql_db.engine is None:
        mysql_db.connect(settings.database_url)
    yield from mysql_db.get_session()


def get_current_token(request: Request) -> str:
    """从 Authorization header 提取原始 Token 字符串。

    不做任何验证，仅提取 Bearer Token 原文。
    用于 logout 等需要操作原始 Token 的场景。

    Args:
        request: FastAPI Request 对象。

    Returns:
        Token 字符串。

    Raises:
        HTTPException: Authorization header 缺失或格式错误时抛出 401。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的Authorization头",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_header[7:]


def get_token_blacklist() -> TokenBlacklist:
    """获取 Token 黑名单操作实例。

    Returns:
        TokenBlacklist 实例。
    """
    return TokenBlacklist(_get_redis_client())


def get_user_cache() -> UserCache:
    """获取用户信息缓存操作实例。

    Returns:
        UserCache 实例。
    """
    return UserCache(_get_redis_client())


def get_redis_client() -> Any:
    """获取全局 Redis 客户端实例（用于限流等场景）。

    Returns:
        RedisClient 实例。
    """
    return _get_redis_client()


def check_token_blacklist(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """独立的 Token 黑名单检查依赖。

    验证当前 Token 是否已被注销（在黑名单中）。
    可作为独立 Depends 使用，也可与 get_current_user 组合。

    Args:
        token: OAuth2 Bearer Token。
        settings: 全局配置实例。

    Returns:
        通过检查的 Token 字符串。

    Raises:
        HTTPException: Token 在黑名单中时抛出 401。
    """
    blacklist = get_token_blacklist()
    if blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token已被注销",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    auth_tools: AuthTools = Depends(get_auth_tools),
    settings: Settings = Depends(get_settings),
) -> Any:
    """从 Bearer Token 解析当前登录用户。

    流程：解码 Token → 查 Redis 缓存 → 未命中则查 DB 并缓存 → 检查状态。
    黑名单检查由路由层通过 check_token_blacklist 独立控制。

    Args:
        token: OAuth2 Bearer Token。
        db: 数据库 Session。
        auth_tools: 认证工具实例。
        settings: 全局配置实例。

    Returns:
        当前认证用户对象。

    Raises:
        HTTPException: Token 无效或用户异常时抛出。
    """
    from jose import JWTError, jwt

    # 1. 解码 Token 获取 user_id
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )

    user_id_int = int(user_id)

    # 2. 优先查 Redis 缓存
    user_cache = get_user_cache()
    cached = user_cache.get_user(user_id_int)
    if cached is not None:
        # 检查缓存中的状态
        if cached.get("status") == "locked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被锁定",
            )
        # 构造一个轻量级用户对象供上层使用
        return _UserFromCache(cached)

    # 3. 缓存未命中，查数据库
    user = db.query(User).filter(User.id == user_id_int).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if user.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被锁定",
        )

    # 4. 写入缓存（TTL = access_token 有效期）
    last_login_str = str(user.last_login) if user.last_login else None
    user_cache.set_user(
        user_id=user.id,
        username=user.username,
        email=user.email,
        status=user.status,
        last_login=last_login_str,
        ttl=settings.access_token_expire_minutes * 60,
    )

    return user


class _UserFromCache:
    """从 Redis 缓存构造的轻量级用户对象。

    提供与 ORM User 对象相同的属性接口，避免缓存命中时查询数据库。
    """

    def __init__(self, data: dict) -> None:
        self.id = data.get("id")
        self.username = data.get("username", "")
        self.email = data.get("email")
        self.status = data.get("status", "active")
        self.last_login = data.get("last_login")

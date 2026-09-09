"""业务逻辑层模块。

封装注册、登录、Token 刷新、退出登录等核心业务逻辑，
路由层调用 Service 方法完成具体操作。
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .dependencies import (
    AuthTools,
    Settings,
    Token,
    TokenBlacklist,
    User,
    UserCache,
    UserCreate,
    check_rate_limit,
)


class Service:
    """业务逻辑服务类。

    提供用户认证相关的所有业务方法，包括注册、登录、
    Token 管理、用户信息查询等。
    """

    def __init__(self, **kwargs: Any) -> None:
        """初始化服务。

        Args:
            **kwargs: 预留扩展参数。
        """
        pass

    def register(
        self,
        user_create: UserCreate,
        db: Session,
        auth_tools: AuthTools,
        pwd_context: CryptContext,
        settings: Settings,
        **kwargs: Any,
    ) -> List[Token]:
        """用户注册，创建账号并返回 Token。

        流程: 检查用户名唯一性 → 创建用户 → 生成双 Token 返回。

        Args:
            user_create: 注册请求数据。
            db: 数据库 Session。
            auth_tools: 认证工具实例。
            pwd_context: 密码加密上下文。
            settings: 全局配置。

        Returns:
            包含 access_token 和 refresh_token 的列表。

        Raises:
            HTTPException: 用户名已存在时抛出 400。
        """
        existing = db.query(User).filter(User.username == user_create.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已被占用",
            )

        new_user = User(
            username=user_create.username,
            email=user_create.email,
            password_hash=auth_tools.get_password_hash(pwd_context, user_create.password),
            status="active",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return self._generate_tokens(new_user.id, auth_tools, settings)

    def login(
        self,
        form_data: OAuth2PasswordRequestForm,
        db: Session,
        ip: str,
        auth_tools: AuthTools,
        pwd_context: CryptContext,
        settings: Settings,
        user_cache: UserCache = None,
        redis_client=None,
        **kwargs: Any,
    ) -> List[Token]:
        """用户登录，支持用户名或邮箱。

        流程: IP 限流 → 查询用户 → 验证密码 → 检查状态
              → 更新 last_login → 缓存用户信息 → 生成双 Token 返回。

        Args:
            form_data: OAuth2 表单登录数据。
            db: 数据库 Session。
            ip: 客户端 IP 地址。
            auth_tools: 认证工具实例。
            pwd_context: 密码加密上下文。
            settings: 全局配置。
            user_cache: 用户信息缓存实例。
            redis_client: Redis 客户端实例（用于限流）。

        Returns:
            包含 access_token 和 refresh_token 的列表。

        Raises:
            HTTPException: 用户名或密码错误（401）、
                账号被锁定（403）时抛出。
        """
        if redis_client:
            check_rate_limit(redis_client, ip)

        user = db.query(User).filter(
            (User.username == form_data.username) | (User.email == form_data.username)
        ).first()

        if not user or not auth_tools.verify_password(
            pwd_context, form_data.password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if user.status == "locked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被锁定，请联系管理员",
            )

        user.last_login = datetime.now(timezone.utc)
        db.commit()

        # 缓存用户信息到 Redis
        if user_cache:
            last_login_str = str(user.last_login) if user.last_login else None
            user_cache.set_user(
                user_id=user.id,
                username=user.username,
                email=user.email,
                status=user.status,
                last_login=last_login_str,
                ttl=settings.access_token_expire_minutes * 60,
            )

        return self._generate_tokens(user.id, auth_tools, settings)

    def refresh_token(
        self,
        refresh_data: Token,
        auth_tools: AuthTools,
        settings: Settings,
        **kwargs: Any,
    ) -> List[Token]:
        """使用 Refresh Token 获取新的 Token 对。

        验证 Refresh Token 类型后生成新的 access_token 和 refresh_token。

        Args:
            refresh_data: 包含 refresh_token 的请求数据。
            auth_tools: 认证工具实例。
            settings: 全局配置。

        Returns:
            新的 Token 列表。

        Raises:
            HTTPException: Token 类型无效或凭据无效时抛出 401。
        """
        payload = auth_tools.decode_token(
            refresh_data.token, settings.secret_key, [settings.algorithm]
        )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的Refresh Token",
            )

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭据",
            )

        return self._generate_tokens(user_id, auth_tools, settings)

    def logout(
        self,
        current_user: User,
        token: str,
        blacklist: TokenBlacklist,
        settings: Settings,
        user_cache: UserCache = None,
        **kwargs: Any,
    ) -> Dict[str, str]:
        """退出登录。

        将当前 Token 加入黑名单，并清除用户信息缓存。

        Args:
            current_user: 当前登录用户。
            token: 当前 Token 字符串。
            blacklist: Token 黑名单操作实例。
            settings: 全局配置。
            user_cache: 用户信息缓存实例。

        Returns:
            退出成功的提示信息。
        """
        blacklist.blacklist(token, settings.secret_key, settings.algorithm)
        if user_cache:
            user_cache.remove_user(current_user.id)
        return {"message": f"用户 {current_user.username} 已退出"}

    def get_me(self, current_user: User, **kwargs: Any) -> Dict[str, Any]:
        """获取当前用户信息。

        Args:
            current_user: 当前登录用户。

        Returns:
            包含用户基本信息的字典。
        """
        return {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "status": current_user.status,
            "last_login": current_user.last_login,
        }

    def health_check(self, **kwargs: Any) -> Dict[str, str]:
        """健康检查接口。

        Returns:
            包含服务状态的字典。
        """
        return {"status": "ok"}

    def _generate_tokens(
        self,
        user_id: Any,
        auth_tools: AuthTools,
        settings: Settings,
        **kwargs: Any,
    ) -> List[Token]:
        """为指定用户生成 access_token 和 refresh_token。

        Args:
            user_id: 用户 ID。
            auth_tools: 认证工具实例。
            settings: 全局配置。

        Returns:
            包含 access_token 和 refresh_token 的列表。
        """
        data = {"user_id": str(user_id)}
        access_token = auth_tools.create_access_token(
            data=data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
            secret_key=settings.secret_key,
            algorithm=settings.algorithm,
        )
        refresh_token = auth_tools.create_refresh_token(
            data=data,
            expires_delta=timedelta(days=settings.refresh_token_expire_days),
            secret_key=settings.secret_key,
            algorithm=settings.algorithm,
        )
        return [
            Token(token=access_token, user_id=user_id),
            Token(token=refresh_token, user_id=user_id),
        ]

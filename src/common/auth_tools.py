"""认证工具模块。

提供密码哈希、JWT Token 生成与解码、用户身份验证等核心认证功能。
所有方法均为无状态工具方法，通过参数传入所需依赖。
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database.mysql.models import User


class AuthTools:
    """认证工具类。

    封装密码加密、JWT Token 操作和用户身份验证逻辑，
    所有方法通过参数接收依赖，便于测试和复用。
    """

    def __init__(self, **kwargs: Any) -> None:
        """初始化认证工具。

        Args:
            **kwargs: 预留扩展参数。
        """
        pass

    def verify_password(
        self,
        pwd_context: CryptContext,
        plain_password: str,
        hashed_password: str,
        **kwargs: Any,
    ) -> bool:
        """验证明文密码与哈希值是否匹配。

        Args:
            pwd_context: passlib 密码加密上下文。
            plain_password: 用户输入的明文密码。
            hashed_password: 数据库中存储的密码哈希。

        Returns:
            密码匹配返回 True，否则返回 False。
        """
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(
        self,
        pwd_context: CryptContext,
        password: str,
        **kwargs: Any,
    ) -> str:
        """生成密码的哈希值。

        Args:
            pwd_context: passlib 密码加密上下文。
            password: 需要加密的明文密码。

        Returns:
            生成的密码哈希字符串。
        """
        return pwd_context.hash(password)

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: timedelta,
        secret_key: str,
        algorithm: str,
        **kwargs: Any,
    ) -> str:
        """生成短期 Access Token。

        Args:
            data: Token payload 数据，至少包含 user_id。
            expires_delta: Token 有效期时间差。
            secret_key: JWT 签名密钥。
            algorithm: JWT 签名算法。

        Returns:
            编码后的 JWT Token 字符串。
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, secret_key, algorithm=algorithm)

    def create_refresh_token(
        self,
        data: Dict[str, Any],
        expires_delta: timedelta,
        secret_key: str,
        algorithm: str,
        **kwargs: Any,
    ) -> str:
        """生成长期 Refresh Token。

        Args:
            data: Token payload 数据，至少包含 user_id。
            expires_delta: Token 有效期时间差。
            secret_key: JWT 签名密钥。
            algorithm: JWT 签名算法。

        Returns:
            编码后的 JWT Token 字符串。
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, secret_key, algorithm=algorithm)

    def decode_token(
        self,
        token: str,
        secret_key: str,
        algorithms: List[str],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """解码并验证 JWT Token。

        Args:
            token: JWT Token 字符串。
            secret_key: JWT 签名密钥。
            algorithms: 允许的签名算法列表。

        Returns:
            解码后的 payload 字典。

        Raises:
            HTTPException: Token 无效或已过期时抛出 401。
        """
        try:
            payload = jwt.decode(token, secret_key, algorithms=algorithms)
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效或过期的Token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_current_user(
        self,
        token: str,
        db: Session,
        secret_key: Optional[str] = None,
        algorithms: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> User:
        """从 Token 中解析并返回当前用户。

        Args:
            token: JWT Token 字符串。
            db: 数据库 Session。
            secret_key: JWT 签名密钥。
            algorithms: 允许的签名算法列表。

        Returns:
            当前认证用户对象。

        Raises:
            HTTPException: Token 无效（401）、用户不存在（401）
                或账号被锁定（403）时抛出。
        """
        payload = self.decode_token(token, secret_key, algorithms)

        token_type = payload.get("type")
        if token_type not in ("access", "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的Token类型",
            )

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭据",
            )

        user = db.query(User).filter(User.id == int(user_id)).first()
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

        return user

"""Token 黑名单模块。

提供基于 Redis 的 Token 黑名单操作，用于在用户退出登录后
使泄露的 Token 失效，防止未授权访问。
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt

logger = logging.getLogger(__name__)


class TokenBlacklist:
    """Token 黑名单操作类。

    通过 Redis 管理已注销的 Token，支持拉黑、检查和移除操作。
    每个 Token 的黑名单条目自动设置 TTL，与 Token 有效期同步过期。

    Attributes:
        _redis: Redis 客户端实例。
        _prefix: Redis Key 前缀。
    """

    def __init__(self, redis_client: Any, prefix: str = "bl:", **kwargs: Any) -> None:
        """初始化 Token 黑名单。

        Args:
            redis_client: RedisClient 实例。
            prefix: Redis Key 前缀，默认 "bl:"。
            **kwargs: 预留扩展参数。
        """
        self._redis = redis_client.get_client()
        self._prefix = prefix

    def _key(self, token: str) -> str:
        """生成 Redis Key。"""
        return f"{self._prefix}{token}"

    def blacklist(
        self,
        token: str,
        secret_key: str,
        algorithm: str,
        **kwargs: Any,
    ) -> None:
        """将 Token 加入黑名单。

        解析 Token 获取过期时间，以 Token 剩余有效期作为 Redis TTL。

        Args:
            token: JWT Token 字符串。
            secret_key: JWT 签名密钥。
            algorithm: JWT 签名算法。

        Raises:
            HTTPException: Token 无效时抛出 401。
        """
        try:
            payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的Token",
            )

        exp = payload.get("exp")
        if exp is None:
            ttl = 86400
        else:
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(int(exp - now), 0)

        if ttl <= 0:
            logger.debug("Token 已过期，跳过黑名单写入")
            return

        self._redis.set(self._key(token), "1", ex=ttl)
        logger.info("Token 已加入黑名单，TTL=%ds", ttl)

    def is_blacklisted(self, token: str, **kwargs: Any) -> bool:
        """检查 Token 是否在黑名单中。

        Args:
            token: JWT Token 字符串。

        Returns:
            Token 在黑名单中返回 True，否则返回 False。
        """
        return self._redis.exists(self._key(token)) > 0

    def remove(self, token: str, **kwargs: Any) -> bool:
        """从黑名单中移除 Token。

        Args:
            token: JWT Token 字符串。

        Returns:
            成功移除返回 True，Token 不在黑名单中返回 False。
        """
        result = self._redis.delete(self._key(token))
        if result > 0:
            logger.info("Token 已从黑名单中移除")
            return True
        return False

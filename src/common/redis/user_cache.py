"""用户信息缓存模块。

提供基于 Redis 的用户信息缓存，减少数据库查询次数。
登录时写入缓存，查询用户时优先读取缓存，退出登录时清除缓存。
"""
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class UserCache:
    """用户信息缓存类。

    通过 Redis 缓存用户基本信息，避免每次请求都查询数据库。
    缓存 TTL 与 access_token 有效期同步。

    Attributes:
        _redis: Redis 客户端实例。
        _prefix: Redis Key 前缀。
    """

    def __init__(self, redis_client: Any, prefix: str = "user:", **kwargs: Any) -> None:
        """初始化用户缓存。

        Args:
            redis_client: RedisClient 实例。
            prefix: Redis Key 前缀，默认 "user:"。
            **kwargs: 预留扩展参数。
        """
        self._redis = redis_client.get_client()
        self._prefix = prefix

    def _key(self, user_id: int) -> str:
        """生成 Redis Key。"""
        return f"{self._prefix}{user_id}"

    def set_user(
        self,
        user_id: int,
        username: str,
        email: Optional[str] = None,
        status: str = "active",
        last_login: Optional[str] = None,
        ttl: int = 1800,
        **kwargs: Any,
    ) -> None:
        """将用户信息写入缓存。

        Args:
            user_id: 用户 ID。
            username: 用户名。
            email: 邮箱。
            status: 账号状态。
            last_login: 最后登录时间（字符串）。
            ttl: 缓存过期时间（秒），默认 30 分钟。
        """
        data = {
            "id": user_id,
            "username": username,
            "email": email,
            "status": status,
            "last_login": last_login,
        }
        self._redis.set(
            self._key(user_id),
            json.dumps(data, ensure_ascii=False, default=str),
            ex=ttl,
        )
        logger.debug("用户信息已缓存: user_id=%d, ttl=%ds", user_id, ttl)

    def get_user(self, user_id: int, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """从缓存获取用户信息。

        Args:
            user_id: 用户 ID。

        Returns:
            用户信息字典，缓存未命中返回 None。
        """
        raw = self._redis.get(self._key(user_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def remove_user(self, user_id: int, **kwargs: Any) -> None:
        """清除用户缓存。

        Args:
            user_id: 用户 ID。
        """
        self._redis.delete(self._key(user_id))
        logger.debug("用户缓存已清除: user_id=%d", user_id)

    def update_last_login(
        self,
        user_id: int,
        last_login: str,
        ttl: int = 1800,
        **kwargs: Any,
    ) -> None:
        """更新缓存中的 last_login 字段。

        Args:
            user_id: 用户 ID。
            last_login: 最后登录时间字符串。
            ttl: 更新后的 TTL。
        """
        data = self.get_user(user_id)
        if data is not None:
            data["last_login"] = last_login
            self._redis.set(
                self._key(user_id),
                json.dumps(data, ensure_ascii=False, default=str),
                ex=ttl,
            )

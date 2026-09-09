"""Agent 会话缓存模块。

提供基于 Redis 的会话缓存，减少数据库查询次数。
包括会话消息缓存和用户会话列表缓存。
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionCache:
    """Agent 会话缓存类。

    通过 Redis 缓存两类数据：
    1. 会话消息列表 — 避免每次对话都查询 PostgreSQL
    2. 用户会话列表 — 避免每次加载会话列表都查询 PostgreSQL

    Attributes:
        _redis: Redis 客户端实例。
        _msg_prefix: 消息缓存 Key 前缀。
        _list_prefix: 会话列表缓存 Key 前缀。
    """

    def __init__(
        self,
        redis_client: Any,
        msg_prefix: str = "agent:session:",
        list_prefix: str = "agent:sessions:",
        **kwargs: Any,
    ) -> None:
        """初始化会话缓存。

        Args:
            redis_client: RedisClient 实例。
            msg_prefix: 消息缓存 Key 前缀。
            list_prefix: 会话列表缓存 Key 前缀。
            **kwargs: 预留扩展参数。
        """
        self._redis = redis_client.get_client()
        self._msg_prefix = msg_prefix
        self._list_prefix = list_prefix

    def _msg_key(self, session_id: str) -> str:
        """生成消息缓存 Key。"""
        return f"{self._msg_prefix}{session_id}"

    def _list_key(self, user_id: int) -> str:
        """生成会话列表缓存 Key。"""
        return f"{self._list_prefix}{user_id}"

    # ==================== 会话消息缓存 ====================

    def get_messages(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """从缓存获取会话消息列表。

        Args:
            session_id: 会话 ID。

        Returns:
            消息字典列表，缓存未命中返回 None。
        """
        raw = self._redis.get(self._msg_key(session_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_messages(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        ttl: int = 86400,
        **kwargs: Any,
    ) -> None:
        """将会话消息列表写入缓存。

        Args:
            session_id: 会话 ID。
            messages: 消息字典列表。
            ttl: 缓存过期时间（秒），默认 24 小时。
        """
        self._redis.set(
            self._msg_key(session_id),
            json.dumps(messages, ensure_ascii=False, default=str),
            ex=ttl,
        )

    def append_message(
        self,
        session_id: str,
        message: Dict[str, Any],
        ttl: int = 86400,
        **kwargs: Any,
    ) -> None:
        """向缓存追加一条消息。

        如果缓存存在，追加到末尾；如果不存在，不做操作（下次读 DB 时会加载）。

        Args:
            session_id: 会话 ID。
            message: 消息字典。
            ttl: 缓存过期时间（秒）。
        """
        raw = self._redis.get(self._msg_key(session_id))
        if raw is None:
            return

        try:
            messages = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        messages.append(message)
        self._redis.set(
            self._msg_key(session_id),
            json.dumps(messages, ensure_ascii=False, default=str),
            ex=ttl,
        )

    def invalidate_messages(self, session_id: str, **kwargs: Any) -> None:
        """清除会话消息缓存。

        Args:
            session_id: 会话 ID。
        """
        self._redis.delete(self._msg_key(session_id))
        logger.debug("会话消息缓存已清除: session_id=%s", session_id)

    # ==================== 用户会话列表缓存 ====================

    def get_session_list(self, user_id: int) -> Optional[List[Dict[str, Any]]]:
        """从缓存获取用户的会话列表。

        Args:
            user_id: 用户 ID。

        Returns:
            会话信息字典列表，缓存未命中返回 None。
        """
        raw = self._redis.get(self._list_key(user_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_session_list(
        self,
        user_id: int,
        sessions: List[Dict[str, Any]],
        ttl: int = 86400,
        **kwargs: Any,
    ) -> None:
        """将用户会话列表写入缓存。

        Args:
            user_id: 用户 ID。
            sessions: 会话信息字典列表。
            ttl: 缓存过期时间（秒），默认 24 小时。
        """
        self._redis.set(
            self._list_key(user_id),
            json.dumps(sessions, ensure_ascii=False, default=str),
            ex=ttl,
        )

    def invalidate_session_list(self, user_id: int, **kwargs: Any) -> None:
        """清除用户会话列表缓存。

        Args:
            user_id: 用户 ID。
        """
        self._redis.delete(self._list_key(user_id))
        logger.debug("用户会话列表缓存已清除: user_id=%d", user_id)

    def invalidate(self, session_id: str, user_id: Optional[int] = None, **kwargs: Any) -> None:
        """清除会话相关的所有缓存。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID，提供时同时清除会话列表缓存。
        """
        self.invalidate_messages(session_id)
        if user_id is not None:
            self.invalidate_session_list(user_id)

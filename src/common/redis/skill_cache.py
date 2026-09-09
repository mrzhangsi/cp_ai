"""Skill 用户技能缓存模块。

提供基于 Redis 的用户技能列表缓存，减少数据库查询次数。
仅缓存列表（不含文件内容），具体技能内容不缓存。
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SkillCache:
    """用户技能列表缓存类。

    通过 Redis 缓存用户的技能列表，避免每次加载列表都查询 PostgreSQL。
    技能详情（文件内容）不缓存，每次从文件系统读取。

    Attributes:
        _redis: Redis 客户端实例。
        _prefix: Redis Key 前缀。
    """

    def __init__(
        self,
        redis_client: Any,
        prefix: str = "skill:user:",
        **kwargs: Any,
    ) -> None:
        """初始化技能缓存。

        Args:
            redis_client: RedisClient 实例。
            prefix: Redis Key 前缀。
            **kwargs: 预留扩展参数。
        """
        self._redis = redis_client.get_client()
        self._prefix = prefix

    def _key(self, user_id: int) -> str:
        """生成 Redis Key。"""
        return f"{self._prefix}{user_id}"

    def get_skill_list(self, user_id: int) -> Optional[List[Dict[str, Any]]]:
        """从缓存获取用户的技能列表。

        Args:
            user_id: 用户 ID。

        Returns:
            技能信息字典列表，缓存未命中返回 None。
        """
        raw = self._redis.get(self._key(user_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_skill_list(
        self,
        user_id: int,
        skills: List[Dict[str, Any]],
        ttl: int = 86400,
        **kwargs: Any,
    ) -> None:
        """将用户技能列表写入缓存。

        Args:
            user_id: 用户 ID。
            skills: 技能信息字典列表。
            ttl: 缓存过期时间（秒），默认 24 小时。
        """
        self._redis.set(
            self._key(user_id),
            json.dumps(skills, ensure_ascii=False, default=str),
            ex=ttl,
        )

    def invalidate(self, user_id: int, **kwargs: Any) -> None:
        """清除用户技能列表缓存。

        Args:
            user_id: 用户 ID。
        """
        self._redis.delete(self._key(user_id))
        logger.debug("用户技能列表缓存已清除: user_id=%d", user_id)

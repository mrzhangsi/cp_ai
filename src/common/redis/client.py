"""Redis 连接管理模块。

提供 Redis 客户端的单例管理，供 Token 黑名单、缓存等功能使用。
"""
import logging
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis 连接管理类。

    封装 Redis 连接的创建与健康检查，采用单例模式确保全局唯一连接。

    Attributes:
        _client: Redis 客户端实例。
    """

    def __init__(self, url: str, **kwargs: Any) -> None:
        """初始化 Redis 连接。

        Args:
            url: Redis 连接 URL（如 redis://localhost:6379/0）。
            **kwargs: 预留扩展参数。
        """
        self._url = url
        self._client: Optional[redis.Redis] = None

    def connect(self) -> redis.Redis:
        """建立 Redis 连接。

        Returns:
            Redis 客户端实例。

        Raises:
            redis.ConnectionError: 连接失败时抛出。
        """
        if self._client is None:
            self._client = redis.Redis.from_url(
                self._url,
                decode_responses=True,
            )
            logger.info("Redis 连接已建立: %s", self._url)
        return self._client

    def get_client(self) -> redis.Redis:
        """获取 Redis 客户端实例。

        Returns:
            Redis 客户端实例，未连接时自动建立连接。
        """
        if self._client is None:
            self.connect()
        return self._client

    def ping(self) -> bool:
        """测试 Redis 连接是否正常。

        Returns:
            连接正常返回 True，否则返回 False。
        """
        try:
            client = self.get_client()
            return client.ping()
        except redis.ConnectionError:
            logger.warning("Redis 连接失败: %s", self._url)
            return False

    def close(self) -> None:
        """关闭 Redis 连接。"""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Redis 连接已关闭")

"""公共工具模块。

提供路径工具和限流检查等通用功能。
"""
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


def get_common_dir() -> Path:
    """获取 common 模块所在目录。

    Returns:
        src/common 目录的 Path 对象。
    """
    return Path(__file__).parent


def check_rate_limit(
    redis_client: Any,
    ip: str,
    max_attempts: int = 5,
    window: int = 300,
    **kwargs: Any,
) -> None:
    """基于 Redis 的 IP 登录限流。

    在指定时间窗口内限制同一 IP 的登录尝试次数。

    Args:
        redis_client: Redis 客户端实例。
        ip: 客户端 IP 地址。
        max_attempts: 时间窗口内最大尝试次数，默认 5 次。
        window: 时间窗口（秒），默认 300 秒（5 分钟）。
        **kwargs: 预留扩展参数。

    Raises:
        HTTPException: 超过最大尝试次数时抛出 429。
    """
    key = f"rate_limit:login:{ip}"
    client = redis_client.get_client()
    current = client.get(key)
    count = int(current) if current else 0

    if count >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过多，请稍后再试",
        )

    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()

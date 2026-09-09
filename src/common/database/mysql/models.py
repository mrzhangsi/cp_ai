"""MySQL ORM 模型定义。

定义 MySQL 数据库中的表结构，使用共享 Base。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String

from ..base import Base


class User(Base):
    """用户 ORM 模型，映射 users 表。

    Attributes:
        id: 用户主键 ID。
        username: 用户名，唯一且索引。
        email: 邮箱，唯一且可选。
        password_hash: 密码哈希值。
        status: 账号状态，active 或 locked。
        created_at: 创建时间。
        last_login: 最后登录时间。
    """

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    username: str = Column(String(80), unique=True, index=True, nullable=False)
    email: Optional[str] = Column(String(120), unique=True, index=True, nullable=True)
    password_hash: str = Column(String(128), nullable=False)
    status: str = Column(String(20), default="active")
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = Column(DateTime, nullable=True)

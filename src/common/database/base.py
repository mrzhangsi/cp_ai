"""共享 ORM Base。

MySQL 和 PostgreSQL 的 ORM 模型共用同一个 DeclarativeBase。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承此类。"""
    pass

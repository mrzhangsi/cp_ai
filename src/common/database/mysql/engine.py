"""MySQL 连接管理模块。

封装 SQLAlchemy 引擎创建和 Session 工厂管理，
提供单例模式的 MySQL 连接。
"""
import logging
from typing import Any, Callable, Generator, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class MySQLDatabase:
    """MySQL 数据库连接管理器。

    采用懒加载单例模式，确保全局只有一个引擎实例。

    Attributes:
        engine: SQLAlchemy 数据库引擎。
        session_factory: SQLAlchemy Session 工厂。
    """

    _instance: Optional["MySQLDatabase"] = None

    def __new__(cls) -> "MySQLDatabase":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.engine = None
            cls._instance.session_factory = None
        return cls._instance

    def connect(self, database_url: str, **kwargs: Any) -> Tuple[Engine, Callable[..., Session]]:
        """连接 MySQL，创建引擎和 Session 工厂。

        Args:
            database_url: SQLAlchemy MySQL 连接 URL。
            **kwargs: 传递给 create_engine 的额外参数。

        Returns:
            包含 (engine, sessionmaker) 的元组。

        Raises:
            Exception: 数据库连接失败时抛出。
        """
        if self.engine is not None:
            return self.engine, self.session_factory

        try:
            self.engine = create_engine(database_url, **kwargs)
            self.session_factory = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine
            )
            logger.info("MySQL 连接已建立: %s", database_url.split("@")[-1])
            return self.engine, self.session_factory
        except Exception as e:
            raise Exception(f"MySQL 连接失败: {e}") from e

    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库 Session（用于 FastAPI Depends）。

        Yields:
            SQLAlchemy 数据库 Session。
        """
        if self.session_factory is None:
            raise RuntimeError("MySQL 未连接，请先调用 connect()")
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("MySQL 连接已关闭")


def get_db() -> Generator[Session, None, None]:
    """FastAPI DI 函数：获取 MySQL Session。

    Yields:
        SQLAlchemy 数据库 Session。
    """
    db = MySQLDatabase().get_session()
    yield from db

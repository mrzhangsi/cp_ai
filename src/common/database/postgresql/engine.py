"""PostgreSQL 连接管理模块。

封装 SQLAlchemy 引擎创建和 Session 工厂管理，
提供单例模式的 PostgreSQL 连接，启动时自动建表并补列。
"""
import logging
from typing import Any, Callable, Generator, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..base import Base

logger = logging.getLogger(__name__)

# 各表的新增列定义：{表名: [(列名, 列类型SQL)]}
_TABLE_MIGRATIONS = {
    "rag_documents": [
        ("chunk_ids", "TEXT"),
    ],
}


class PostgreSQLDatabase:
    """PostgreSQL 数据库连接管理器。

    采用懒加载单例模式，确保全局只有一个引擎实例。
    连接时自动创建所有 ORM 模型对应的表，并补全缺失列。

    Attributes:
        engine: SQLAlchemy 数据库引擎。
        session_factory: SQLAlchemy Session 工厂。
    """

    _instance: Optional["PostgreSQLDatabase"] = None

    def __new__(cls) -> "PostgreSQLDatabase":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.engine = None
            cls._instance.session_factory = None
        return cls._instance

    def _migrate_columns(self, engine: Engine) -> None:
        """检查并补全缺失的列（简单迁移）。

        Args:
            engine: SQLAlchemy 数据库引擎。
        """
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        for table_name, columns in _TABLE_MIGRATIONS.items():
            if table_name not in existing_tables:
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            with engine.connect() as conn:
                for col_name, col_type in columns:
                    if col_name not in existing_cols:
                        sql = text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        )
                        conn.execute(sql)
                        logger.info("已补列: %s.%s (%s)", table_name, col_name, col_type)
                conn.commit()

    def connect(self, database_url: str, **kwargs: Any) -> Tuple[Engine, Callable[..., Session]]:
        """连接 PostgreSQL，创建引擎、Session 工厂并自动建表+补列。

        Args:
            database_url: SQLAlchemy PostgreSQL 连接 URL。
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

            from .models import AgentMessage, AgentSession, RAGDocument, UserSkill
            Base.metadata.create_all(bind=self.engine)

            # 启用 pgvector 扩展（mem0 需要）
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()

            self._migrate_columns(self.engine)

            logger.info("PostgreSQL 连接已建立，表已自动创建/补列")

            return self.engine, self.session_factory
        except Exception as e:
            raise Exception(f"PostgreSQL 连接失败: {e}") from e

    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库 Session（用于 FastAPI Depends）。

        Yields:
            SQLAlchemy 数据库 Session。
        """
        if self.session_factory is None:
            raise RuntimeError("PostgreSQL 未连接，请先调用 connect()")
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
            logger.info("PostgreSQL 连接已关闭")


def get_pg_db() -> Generator[Session, None, None]:
    """FastAPI DI 函数：获取 PostgreSQL Session。

    Yields:
        SQLAlchemy 数据库 Session。
    """
    db = PostgreSQLDatabase().get_session()
    yield from db

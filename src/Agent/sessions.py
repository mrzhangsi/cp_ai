"""会话管理模块。

提供会话的创建、存储、消息历史管理。
使用 PostgreSQL 持久化存储，Redis 缓存加速读取，按用户隔离。
"""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.common.config import settings
from src.common.database.postgresql.engine import PostgreSQLDatabase
from src.common.database.postgresql.models import AgentMessage, AgentSession
from src.common.models import ChatMessage, SessionInfo
from src.common.redis.client import RedisClient
from src.common.redis.session_cache import SessionCache


class SessionManager:
    """会话管理器。

    管理多个对话会话，每个会话包含完整的消息历史。
    使用 PostgreSQL 持久化存储，Redis 缓存加速读取，按用户隔离。
    """

    def __init__(self, pg_db: Optional[Session] = None) -> None:
        """初始化会话管理器。

        Args:
            pg_db: PostgreSQL Session，为 None 时自动创建。
        """
        self._cache_ttl = settings.session_cache_ttl

        if pg_db is None:
            db_manager = PostgreSQLDatabase()
            if db_manager.engine is None:
                db_manager.connect(settings.postgres_url)
            self._pg_db = db_manager.session_factory()
            self._owns_session = True
        else:
            self._pg_db = pg_db
            self._owns_session = False

        try:
            redis_client = RedisClient(settings.redis_url)
            redis_client.connect()
            self._cache = SessionCache(redis_client)
        except Exception:
            self._cache = None

    def close(self) -> None:
        """关闭数据库 Session（仅关闭自己创建的）。"""
        if self._owns_session and self._pg_db is not None:
            self._pg_db.close()

    def create_session(self, user_id: int, title: Optional[str] = None, skill_id: Optional[int] = None) -> SessionInfo:
        """创建新会话。

        Args:
            user_id: 用户 ID（隔离标识）。
            title: 会话标题，为 None 时使用默认标题。
            skill_id: 附带的技能 ID。

        Returns:
            新创建的会话信息。
        """
        session_id = uuid.uuid4().hex[:12]
        return self.create_session_with_id(session_id, user_id, title, skill_id)

    def create_session_with_id(
        self,
        session_id: str,
        user_id: int,
        title: Optional[str] = None,
        skill_id: Optional[int] = None,
    ) -> SessionInfo:
        """使用指定 ID 创建新会话。

        Args:
            session_id: 指定的会话 ID。
            user_id: 用户 ID（隔离标识）。
            title: 会话标题，为 None 时使用默认标题。
            skill_id: 附带的技能 ID。

        Returns:
            新创建的会话信息。

        Raises:
            ValueError: 会话 ID 已存在时抛出。
        """
        existing = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if existing:
            raise ValueError(f"会话已存在：{session_id}")

        now = datetime.now(timezone.utc)
        session = AgentSession(
            session_id=session_id,
            user_id=user_id,
            title=title or "新会话",
            skill_id=skill_id,
            created_at=now,
            updated_at=now,
        )
        self._pg_db.add(session)
        self._pg_db.commit()

        if self._cache:
            self._cache.invalidate_session_list(user_id)

        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionInfo:
        """获取会话信息。

        Args:
            session_id: 会话 ID。

        Returns:
            会话信息。

        Raises:
            KeyError: 会话不存在时抛出。
        """
        session = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session:
            raise KeyError(f"会话不存在：{session_id}")

        message_count = (
            self._pg_db.query(AgentMessage)
            .filter(AgentMessage.session_id == session_id)
            .count()
        )

        return SessionInfo(
            session_id=session.session_id,
            title=session.title,
            skill_id=session.skill_id,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            message_count=message_count,
        )

    def list_sessions(self, user_id: Optional[int] = None) -> List[SessionInfo]:
        """列出所有会话。

        优先从 Redis 缓存读取，未命中则查数据库并缓存。

        Args:
            user_id: 用户 ID，为 None 时列出所有会话。

        Returns:
            会话信息列表。
        """
        if user_id is not None and self._cache:
            cached = self._cache.get_session_list(user_id)
            if cached is not None:
                return [
                    SessionInfo(
                        session_id=s["session_id"],
                        title=s["title"],
                        skill_id=s.get("skill_id"),
                        created_at=s["created_at"],
                        updated_at=s["updated_at"],
                        message_count=s["message_count"],
                    )
                    for s in cached
                ]

        query = self._pg_db.query(AgentSession)
        if user_id is not None:
            query = query.filter(AgentSession.user_id == user_id)
        sessions = query.order_by(AgentSession.updated_at.desc()).all()
        result = [self.get_session(s.session_id) for s in sessions]

        if user_id is not None and self._cache:
            cache_data = [
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "skill_id": s.skill_id,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": s.message_count,
                }
                for s in result
            ]
            self._cache.set_session_list(user_id, cache_data, ttl=self._cache_ttl)

        return result

    def delete_session(self, session_id: str) -> None:
        """删除会话及其所有消息。

        Args:
            session_id: 会话 ID。

        Raises:
            KeyError: 会话不存在时抛出。
        """
        session = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session:
            raise KeyError(f"会话不存在：{session_id}")

        user_id = session.user_id

        self._pg_db.query(AgentMessage).filter(
            AgentMessage.session_id == session_id
        ).delete()
        self._pg_db.delete(session)
        self._pg_db.commit()

        if self._cache:
            self._cache.invalidate(session_id, user_id=user_id)

    def add_message(self, session_id: str, message: ChatMessage) -> int:
        """添加消息到会话。

        同时更新 Redis 缓存，写入后使消息缓存失效。

        Args:
            session_id: 会话 ID。
            message: 消息对象。

        Returns:
            新消息的数据库 ID。

        Raises:
            KeyError: 会话不存在时抛出。
        """
        session = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session:
            raise KeyError(f"会话不存在：{session_id}")

        metadata_json = None
        if message.metadata:
            metadata_json = json.dumps(message.metadata, ensure_ascii=False)

        msg = AgentMessage(
            session_id=session_id,
            role=message.role,
            content=message.content,
            metadata_json=metadata_json,
        )
        self._pg_db.add(msg)
        self._pg_db.flush()

        session.updated_at = datetime.now(timezone.utc)
        self._pg_db.commit()

        if self._cache:
            self._cache.invalidate_messages(session_id)
            self._cache.invalidate_session_list(session.user_id)

        return msg.id

    def get_messages(self, session_id: str) -> List[ChatMessage]:
        """获取会话消息历史。

        优先从 Redis 缓存读取，未命中则查数据库并缓存。

        Args:
            session_id: 会话 ID。

        Returns:
            消息列表。

        Raises:
            KeyError: 会话不存在时抛出。
        """
        if self._cache:
            cached = self._cache.get_messages(session_id)
            if cached is not None:
                return [
                    ChatMessage(
                        id=m.get("id"),
                        role=m["role"],
                        content=m["content"],
                        timestamp=m.get("timestamp"),
                        metadata=m.get("metadata"),
                    )
                    for m in cached
                ]

        session = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session:
            raise KeyError(f"会话不存在：{session_id}")

        messages = (
            self._pg_db.query(AgentMessage)
            .filter(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at)
            .all()
        )

        result = []
        cache_data = []
        for msg in messages:
            metadata = None
            if msg.metadata_json:
                try:
                    metadata = json.loads(msg.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            chat_msg = ChatMessage(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at.isoformat() if msg.created_at else None,
                metadata=metadata,
            )
            result.append(chat_msg)
            cache_data.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                "metadata": metadata,
            })

        if self._cache and cache_data:
            self._cache.set_messages(session_id, cache_data, ttl=self._cache_ttl)

        return result

    def set_session_skill(self, session_id: str, skill_id: Optional[int]) -> None:
        """设置或清除会话关联的技能。

        Args:
            session_id: 会话 ID。
            skill_id: 技能 ID，传 None 表示取消选择。

        Raises:
            KeyError: 会话不存在时抛出。
        """
        session = (
            self._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session:
            raise KeyError(f"会话不存在：{session_id}")

        session.skill_id = skill_id
        session.updated_at = datetime.now(timezone.utc)
        self._pg_db.commit()

        if self._cache:
            self._cache.invalidate_session_list(session.user_id)

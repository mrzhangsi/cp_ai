"""PostgreSQL ORM 模型定义。

定义 PostgreSQL 数据库中的表结构，使用共享 Base。
用于 Agent 会话/消息和用户技能的持久化存储。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..base import Base


class AgentSession(Base):
    """Agent 会话 ORM 模型，映射 agent_sessions 表。

    按用户隔离，每个用户只能访问自己的会话。

    Attributes:
        id: 自增主键。
        session_id: 会话唯一标识（UUID hex）。
        user_id: 关联的用户 ID（隔离标识）。
        title: 会话标题。
        skill_id: 关联的 Skill ID（可选）。
        created_at: 创建时间。
        updated_at: 最后更新时间。
    """

    __tablename__ = "agent_sessions"

    id: int = Column(Integer, primary_key=True, index=True)
    session_id: str = Column(String(32), unique=True, index=True, nullable=False)
    user_id: int = Column(Integer, nullable=False, index=True)
    title: str = Column(String(200), default="新会话")
    skill_id: Optional[int] = Column(Integer, nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentMessage(Base):
    """Agent 消息 ORM 模型，映射 agent_messages 表。

    存储会话中的每条消息，支持 user/assistant/system/tool 角色。

    Attributes:
        id: 自增主键。
        session_id: 关联的会话 ID。
        role: 消息角色。
        content: 消息内容。
        metadata_json: 附加元数据（JSON 字符串）。
        created_at: 创建时间。
    """

    __tablename__ = "agent_messages"

    id: int = Column(Integer, primary_key=True, index=True)
    session_id: str = Column(
        String(32),
        ForeignKey("agent_sessions.session_id"),
        index=True,
        nullable=False,
    )
    role: str = Column(String(20), nullable=False)
    content: str = Column(Text, nullable=False)
    metadata_json: Optional[str] = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserSkill(Base):
    """用户技能 ORM 模型，映射 user_skills 表。

    存储用户上传的 Skill MD 文件信息，按用户隔离。

    Attributes:
        id: 自增主键。
        user_id: 所属用户 ID（隔离标识）。
        name: 技能名称。
        summary: 技能摘要（可从 MD 自动提取，用户可覆盖）。
        file_path: MD 文件在文件系统中的路径。
        created_at: 创建时间。
        updated_at: 最后更新时间。
    """

    __tablename__ = "user_skills"

    id: int = Column(Integer, primary_key=True, index=True)
    user_id: int = Column(Integer, nullable=False, index=True)
    name: str = Column(String(100), nullable=False)
    summary: str = Column(Text, default="")
    file_path: str = Column(String(500), nullable=False)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RAGDocument(Base):
    """RAG 文档 ORM 模型，映射 rag_documents 表。

    存储用户上传的原始 MD 文档，按用户隔离。

    Attributes:
        id: 自增主键。
        user_id: 所属用户 ID（隔离标识）。
        filename: 原始文件名。
        content: MD 文件原始内容。
        chunk_count: 切片后写入向量库的 chunk 数量。
        chunk_ids: JSON 字符串，存储该文档对应的所有 ChromaDB chunk ID。
        created_at: 上传时间。
    """

    __tablename__ = "rag_documents"

    id: int = Column(Integer, primary_key=True, index=True)
    user_id: int = Column(Integer, nullable=False, index=True)
    filename: str = Column(String(255), nullable=False)
    content: str = Column(Text, nullable=False)
    chunk_count: int = Column(Integer, default=0)
    chunk_ids: Optional[str] = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))

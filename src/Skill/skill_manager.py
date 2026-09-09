"""用户技能管理模块。

提供用户上传 Skill MD 文件的管理功能，包括文件存储、数据库 CRUD 和 Redis 缓存。
文件存储在本地文件系统，元数据存储在 PostgreSQL，列表缓存在 Redis。
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.common.config import settings
from src.common.database.postgresql.engine import PostgreSQLDatabase
from src.common.database.postgresql.models import UserSkill
from src.common.models import HealthResponse
from src.common.redis.client import RedisClient
from src.common.redis.skill_cache import SkillCache

logger = logging.getLogger(__name__)


def parse_skill_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """解析 MD 文件的 YAML frontmatter，提取 name 和 description。

    支持格式：
    ---
    name: xxx
    description: xxx
    origin: xxx
    ---

    Args:
        content: MD 文件完整内容。

    Returns:
        (frontmatter 字典, 去除 frontmatter 后的正文内容)。
    """
    frontmatter: Dict[str, str] = {}
    body = content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = content[match.end():]
        for line in fm_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()

    return frontmatter, body


def extract_summary_from_md(content: str) -> str:
    """从 MD 文件内容中自动提取摘要。

    优先级：
    1. frontmatter 中的 description 字段
    2. "## Summary" 或 "## 摘要" 部分
    3. 第一个非标题段落

    Args:
        content: MD 文件完整内容。

    Returns:
        提取的摘要文本，最多 500 字符。
    """
    frontmatter, body = parse_skill_frontmatter(content)

    if frontmatter.get("description"):
        return frontmatter["description"][:500]

    lines = body.split("\n")
    in_summary = False
    summary_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+(Summary|摘要)", stripped, re.IGNORECASE):
            in_summary = True
            continue
        if in_summary:
            if stripped.startswith("##"):
                break
            if stripped:
                summary_lines.append(stripped)

    if summary_lines:
        return "\n".join(summary_lines)[:500]

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:500]

    return ""


def extract_name_from_md(content: str) -> str:
    """从 MD 文件内容中自动提取技能名称。

    优先级：
    1. frontmatter 中的 name 字段
    2. 第一个 # 标题

    Args:
        content: MD 文件完整内容。

    Returns:
        提取的名称，最多 100 字符。
    """
    frontmatter, body = parse_skill_frontmatter(content)

    if frontmatter.get("name"):
        return frontmatter["name"][:100]

    for line in body.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#\s+(.+)", stripped)
        if match:
            return match.group(1).strip()[:100]

    return ""


class SkillManager:
    """用户技能管理器。

    管理用户上传的 Skill MD 文件，包括文件存储、数据库 CRUD 和 Redis 缓存。
    按用户隔离，每个用户只能访问自己的技能。

    Attributes:
        _pg_db: PostgreSQL Session。
        _owns_session: 是否由自己创建的 Session（需自行关闭）。
        _storage_dir: 文件存储根目录。
        _cache: Redis 技能列表缓存。
        _cache_ttl: 缓存过期时间（秒）。
    """

    def __init__(self, pg_db: Optional[Session] = None) -> None:
        """初始化技能管理器。

        Args:
            pg_db: PostgreSQL Session，为 None 时自动创建。
        """
        self._storage_dir = settings.skill_storage_dir
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
            self._cache = SkillCache(redis_client)
        except Exception:
            self._cache = None

    def close(self) -> None:
        """关闭数据库 Session（仅关闭自己创建的）。"""
        if self._owns_session and self._pg_db is not None:
            self._pg_db.close()

    def _user_dir(self, user_id: int) -> str:
        """获取用户文件存储目录，不存在则创建。"""
        user_dir = os.path.join(self._storage_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return user_dir

    def upload_skill(
        self,
        user_id: int,
        name: str,
        file_content: bytes,
        filename: str,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """上传 Skill MD 文件。

        Args:
            user_id: 用户 ID。
            name: 技能名称。
            file_content: 文件二进制内容。
            filename: 原始文件名。
            summary: 摘要，为 None 时自动从 MD 内容提取。

        Returns:
            创建的技能信息字典。

        Raises:
            ValueError: 文件名不是 .md 结尾时抛出。
        """
        if not filename.lower().endswith(".md"):
            raise ValueError("仅支持 .md 文件")

        content_text = file_content.decode("utf-8")

        if summary is None:
            summary = extract_summary_from_md(content_text)

        file_id = uuid.uuid4().hex[:12]
        saved_filename = f"{file_id}.md"
        user_dir = self._user_dir(user_id)
        file_path = os.path.join(user_dir, saved_filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content_text)

        now = datetime.now(timezone.utc)
        skill = UserSkill(
            user_id=user_id,
            name=name,
            summary=summary,
            file_path=file_path,
            created_at=now,
            updated_at=now,
        )
        self._pg_db.add(skill)
        self._pg_db.commit()
        self._pg_db.refresh(skill)

        if self._cache:
            self._cache.invalidate(user_id)

        return {
            "id": skill.id,
            "name": skill.name,
            "summary": skill.summary,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
        }

    def list_skills(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户技能列表。

        优先从 Redis 缓存读取，未命中则查数据库并缓存。

        Args:
            user_id: 用户 ID。

        Returns:
            技能信息字典列表（不含文件内容）。
        """
        if self._cache:
            cached = self._cache.get_skill_list(user_id)
            if cached is not None:
                return cached

        skills = (
            self._pg_db.query(UserSkill)
            .filter(UserSkill.user_id == user_id)
            .order_by(UserSkill.updated_at.desc())
            .all()
        )

        result = [
            {
                "id": s.id,
                "name": s.name,
                "summary": s.summary,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in skills
        ]

        if self._cache:
            self._cache.set_skill_list(user_id, result, ttl=self._cache_ttl)

        return result

    def get_skill(self, skill_id: int, user_id: int) -> Dict[str, Any]:
        """获取技能详情（含文件内容）。

        Args:
            skill_id: 技能 ID。
            user_id: 用户 ID（隔离校验）。

        Returns:
            技能详情字典，包含 content 字段。

        Raises:
            KeyError: 技能不存在或不属于该用户时抛出。
        """
        skill = (
            self._pg_db.query(UserSkill)
            .filter(UserSkill.id == skill_id, UserSkill.user_id == user_id)
            .first()
        )
        if not skill:
            raise KeyError(f"技能不存在：{skill_id}")

        content = ""
        if os.path.exists(skill.file_path):
            with open(skill.file_path, "r", encoding="utf-8") as f:
                content = f.read()

        return {
            "id": skill.id,
            "name": skill.name,
            "summary": skill.summary,
            "content": content,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
        }

    def delete_skill(self, skill_id: int, user_id: int) -> None:
        """删除技能（删文件 + 删记录）。

        Args:
            skill_id: 技能 ID。
            user_id: 用户 ID（隔离校验）。

        Raises:
            KeyError: 技能不存在或不属于该用户时抛出。
        """
        skill = (
            self._pg_db.query(UserSkill)
            .filter(UserSkill.id == skill_id, UserSkill.user_id == user_id)
            .first()
        )
        if not skill:
            raise KeyError(f"技能不存在：{skill_id}")

        if os.path.exists(skill.file_path):
            os.remove(skill.file_path)

        self._pg_db.delete(skill)
        self._pg_db.commit()

        if self._cache:
            self._cache.invalidate(user_id)

    def update_skill(
        self,
        skill_id: int,
        user_id: int,
        name: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新技能名称和摘要。

        Args:
            skill_id: 技能 ID。
            user_id: 用户 ID（隔离校验）。
            name: 新名称，为 None 时不更新。
            summary: 新摘要，为 None 时不更新。

        Returns:
            更新后的技能信息。

        Raises:
            KeyError: 技能不存在或不属于该用户时抛出。
        """
        skill = (
            self._pg_db.query(UserSkill)
            .filter(UserSkill.id == skill_id, UserSkill.user_id == user_id)
            .first()
        )
        if not skill:
            raise KeyError(f"技能不存在：{skill_id}")

        if name is not None:
            skill.name = name
        if summary is not None:
            skill.summary = summary
        skill.updated_at = datetime.now(timezone.utc)

        self._pg_db.commit()
        self._pg_db.refresh(skill)

        if self._cache:
            self._cache.invalidate(user_id)

        return {
            "id": skill.id,
            "name": skill.name,
            "summary": skill.summary,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
        }



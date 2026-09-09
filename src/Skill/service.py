"""Skill 业务逻辑层。

包含两个功能：
1. SkillsMP API 搜索（外部技能）
2. 用户技能管理（上传/列表/详情/删除）
"""
import logging
from typing import Any, Dict, Optional

import httpx

from src.common.config import settings
from .models import SkillInfo, SkillSearchRequest, SkillSearchResponse
from .skill_manager import SkillManager

logger = logging.getLogger(__name__)

BASE_URL = "https://skillsmp.com/api/v1/skills"


class SkillService:
    """Skill 搜索服务类。

    封装 SkillsMP API 调用和用户技能管理。
    """

    def __init__(self) -> None:
        """初始化 Skill 服务。"""
        self._api_key = settings.skillsmp_api_key
        self._manager: Optional[SkillManager] = None

    @property
    def manager(self) -> SkillManager:
        """延迟初始化 SkillManager。"""
        if self._manager is None:
            self._manager = SkillManager()
        return self._manager

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头。"""
        headers: Dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @staticmethod
    def _extract_urls(skill: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """从技能数据中提取各种 URL。

        Args:
            skill: API 返回的技能数据字典。

        Returns:
            包含各种 URL 的字典。
        """
        urls: Dict[str, Optional[str]] = {
            "skill_url": skill.get("skillUrl"),
            "github_url": None,
            "raw_content_url": None,
        }

        skill_url = urls["skill_url"]
        if skill_url and "skillsmp.com/creators/" in skill_url:
            parts = skill_url.split("/")
            if len(parts) >= 6:
                owner = parts[4]
                repo = parts[5]
                urls["github_url"] = f"https://github.com/{owner}/{repo}"
                urls["raw_content_url"] = (
                    f"https://raw.githubusercontent.com/{owner}/{repo}/main/SKILL.md"
                )

        if skill.get("github_url"):
            urls["github_url"] = skill["github_url"]

        if skill.get("repo_url"):
            urls["github_url"] = skill["repo_url"]

        return urls

    async def search(self, req: SkillSearchRequest) -> SkillSearchResponse:
        """搜索技能。

        Args:
            req: 搜索请求参数。

        Returns:
            搜索结果。

        Raises:
            RuntimeError: API 请求失败时抛出。
        """
        url = f"{BASE_URL}/search"
        params: Dict[str, Any] = {"q": req.query, "page": req.page, "limit": req.limit}
        if req.sort_by:
            params["sortBy"] = req.sort_by
        if req.category:
            params["category"] = req.category
        if req.occupation:
            params["occupation"] = req.occupation
        if req.language:
            params["language"] = req.language

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    url, params=params, headers=self._build_headers()
                )
                response.raise_for_status()
        except httpx.RequestError as e:
            logger.error("SkillsMP API 请求失败: %s", e)
            raise RuntimeError(f"SkillsMP API 请求失败: {e}") from e

        data = response.json()
        if not data.get("success"):
            raise RuntimeError("SkillsMP API 返回失败状态")

        skills_data = data.get("data", {})
        raw_skills = skills_data.get("skills", [])

        skills = []
        for s in raw_skills:
            urls = self._extract_urls(s)
            skills.append(
                SkillInfo(
                    name=s.get("name", "未命名"),
                    description=s.get("description", ""),
                    category_name=s.get("category_name", "未分类"),
                    stars=s.get("stars", 0),
                    skill_url=urls["skill_url"],
                    github_url=urls["github_url"],
                    raw_content_url=urls["raw_content_url"],
                    install_command=s.get("install_command"),
                )
            )

        return SkillSearchResponse(
            skills=skills,
            total=skills_data.get("total", 0),
            page=req.page,
            limit=req.limit,
        )

    def upload_skill(
        self,
        user_id: int,
        name: str,
        file_content: bytes,
        filename: str,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """上传用户技能。"""
        return self.manager.upload_skill(user_id, name, file_content, filename, summary)

    def list_user_skills(self, user_id: int) -> list:
        """获取用户技能列表。"""
        return self.manager.list_skills(user_id)

    def get_user_skill(self, skill_id: int, user_id: int) -> Dict[str, Any]:
        """获取用户技能详情。"""
        return self.manager.get_skill(skill_id, user_id)

    def delete_user_skill(self, skill_id: int, user_id: int) -> None:
        """删除用户技能。"""
        self.manager.delete_skill(skill_id, user_id)

    def update_user_skill(
        self,
        skill_id: int,
        user_id: int,
        name: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新用户技能名称和摘要。"""
        return self.manager.update_skill(skill_id, user_id, name=name, summary=summary)

    def health_check(self) -> Dict[str, str]:
        """健康检查。"""
        return {"status": "ok", "module": "skill", "api_key_set": bool(self._api_key)}

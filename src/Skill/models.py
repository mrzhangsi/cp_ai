"""Skill 模块 Pydantic 请求/响应模型。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SkillSearchRequest(BaseModel):
    """技能搜索请求模型。

    Attributes:
        query: 搜索关键词。
        page: 页码，默认 1。
        limit: 每页数量，默认 20，最大 50。
        sort_by: 排序方式（relevance/stars/forks/updated）。
        category: 分类筛选。
        occupation: 职业筛选。
        language: 语言筛选。
    """

    query: str = Field(..., min_length=1, description="搜索关键词")
    page: int = Field(1, ge=1, description="页码")
    limit: int = Field(20, ge=1, le=50, description="每页数量")
    sort_by: Optional[str] = Field(None, description="排序方式")
    category: Optional[str] = Field(None, description="分类筛选")
    occupation: Optional[str] = Field(None, description="职业筛选")
    language: Optional[str] = Field(None, description="语言筛选")


class SkillUrls(BaseModel):
    """技能相关 URL 模型。

    Attributes:
        skill_url: SkillsMP 详情页 URL。
        github_url: GitHub 仓库 URL。
        raw_content_url: SKILL.md 原始内容 URL。
    """

    skill_url: Optional[str] = Field(None, description="详情页 URL")
    github_url: Optional[str] = Field(None, description="GitHub 仓库 URL")
    raw_content_url: Optional[str] = Field(None, description="SKILL.md 原始内容 URL")


class SkillInfo(BaseModel):
    """技能信息模型。

    Attributes:
        name: 技能名称。
        description: 技能描述。
        category_name: 分类名称。
        stars: 收藏数。
        skill_url: 详情页 URL。
        github_url: GitHub 仓库 URL。
        raw_content_url: SKILL.md 原始内容 URL。
        install_command: 安装命令。
    """

    name: str = Field(..., description="技能名称")
    description: str = Field("", description="技能描述")
    category_name: str = Field("未分类", description="分类名称")
    stars: int = Field(0, description="收藏数")
    skill_url: Optional[str] = Field(None, description="详情页 URL")
    github_url: Optional[str] = Field(None, description="GitHub 仓库 URL")
    raw_content_url: Optional[str] = Field(None, description="SKILL.md 原始内容 URL")
    install_command: Optional[str] = Field(None, description="安装命令")


class SkillSearchResponse(BaseModel):
    """技能搜索响应模型。

    Attributes:
        skills: 技能列表。
        total: 总数。
        page: 当前页码。
        limit: 每页数量。
    """

    skills: List[SkillInfo] = Field(default_factory=list, description="技能列表")
    total: int = Field(0, description="总数")
    page: int = Field(1, description="当前页码")
    limit: int = Field(20, description="每页数量")


# ==================== 用户技能模型 ====================


class UserSkillInfo(BaseModel):
    """用户技能信息模型（列表用，不含文件内容）。

    Attributes:
        id: 技能 ID。
        name: 技能名称。
        summary: 摘要。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    id: int = Field(..., description="技能 ID")
    name: str = Field(..., description="技能名称")
    summary: str = Field("", description="技能摘要")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class UserSkillDetail(BaseModel):
    """用户技能详情模型（含文件内容）。

    Attributes:
        id: 技能 ID。
        name: 技能名称。
        summary: 摘要。
        content: MD 文件内容。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    id: int = Field(..., description="技能 ID")
    name: str = Field(..., description="技能名称")
    summary: str = Field("", description="技能摘要")
    content: str = Field("", description="MD 文件内容")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class SkillHealthResponse(BaseModel):
    """Skill 模块健康检查响应模型。

    Attributes:
        status: 服务状态。
        module: 模块名称。
        api_key_set: 是否已配置 API Key。
    """

    status: str = Field(..., description="服务状态")
    module: str = Field(..., description="模块名称")
    api_key_set: bool = Field(False, description="是否已配置 API Key")

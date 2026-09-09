"""Skill API 路由模块。

定义技能搜索和用户技能管理接口，前缀为 /skill。
所有接口需要 JWT 认证（健康检查除外）。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from .dependencies import check_token_blacklist, get_current_user
from .models import (
    SkillHealthResponse,
    SkillSearchRequest,
    SkillSearchResponse,
    UserSkillDetail,
    UserSkillInfo,
)
from .service import SkillService

router = APIRouter(prefix="/skill", tags=["Skill"])

_service: SkillService = None


class UpdateSkillRequest(BaseModel):
    """更新技能请求模型。"""
    name: Optional[str] = None
    summary: Optional[str] = None


def init_service(service: SkillService) -> None:
    """初始化服务实例，注入到路由模块。

    Args:
        service: SkillService 业务逻辑实例。
    """
    global _service
    _service = service


@router.post("/search", response_model=SkillSearchResponse)
async def search_skills(
    req: SkillSearchRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """搜索 SkillsMP 平台技能。

    需要 Bearer Token 认证，且 Token 不得在黑名单中。

    Args:
        req: 搜索请求体，包含关键词和筛选条件。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        搜索结果。
    """
    return await _service.search(req)


@router.post("/upload", response_model=UserSkillInfo)
def upload_skill(
    name: str = Form(..., description="技能名称"),
    summary: Optional[str] = Form(None, description="技能摘要（可选，为空时自动提取）"),
    file: UploadFile = File(..., description="MD 文件"),
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """上传用户技能 MD 文件。

    需要 Bearer Token 认证。仅支持 .md 文件。
    摘要为空时自动从文件的 ## Summary / ## 摘要 部分提取。

    Args:
        name: 技能名称。
        summary: 技能摘要（可选）。
        file: 上传的 MD 文件。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        创建的技能信息。
    """
    file_content = file.file.read()
    return _service.upload_skill(
        user_id=current_user.id,
        name=name,
        file_content=file_content,
        filename=file.filename,
        summary=summary if summary else None,
    )


@router.get("/my-skills", response_model=List[UserSkillInfo])
def list_my_skills(
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """获取当前用户的技能列表。

    优先从 Redis 缓存读取。

    Args:
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        技能列表（不含文件内容）。
    """
    return _service.list_user_skills(user_id=current_user.id)


@router.get("/my-skills/{skill_id}", response_model=UserSkillDetail)
def get_my_skill(
    skill_id: int,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """获取用户技能详情（含 MD 文件内容）。

    Args:
        skill_id: 技能 ID。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        技能详情，包含 content 字段。
    """
    return _service.get_user_skill(skill_id=skill_id, user_id=current_user.id)


@router.patch("/my-skills/{skill_id}", response_model=UserSkillInfo)
def update_my_skill(
    skill_id: int,
    req: UpdateSkillRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """更新用户技能名称和摘要。

    Args:
        skill_id: 技能 ID。
        req: 更新请求体，name 和 summary 均可选。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        更新后的技能信息。
    """
    return _service.update_user_skill(
        skill_id=skill_id,
        user_id=current_user.id,
        name=req.name,
        summary=req.summary,
    )


@router.delete("/my-skills/{skill_id}", response_model=dict)
def delete_my_skill(
    skill_id: int,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """删除用户技能（删文件 + 删记录）。

    Args:
        skill_id: 技能 ID。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。
    """
    _service.delete_user_skill(skill_id=skill_id, user_id=current_user.id)
    return {"detail": "删除成功"}


@router.get("/health", response_model=SkillHealthResponse)
def health_check_api():
    """健康检查接口。"""
    return _service.health_check()

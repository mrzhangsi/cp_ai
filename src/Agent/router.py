"""Agent API 路由模块。

定义 Agent 相关接口，前缀为 /agent。
所有接口需要 JWT 认证。
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.common.config import settings
from src.common.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    HealthResponse,
    SessionInfo,
)
from .dependencies import check_token_blacklist, get_current_user
from .service import AgentService

router = APIRouter(prefix="/agent", tags=["Agent"])

_service: AgentService = None


class UpdateSessionSkillRequest(BaseModel):
    """更新会话关联技能请求模型。"""
    skill_id: Optional[int] = None


def init_service(service: AgentService) -> None:
    """初始化服务实例，注入到路由模块。

    Args:
        service: AgentService 业务逻辑实例。
    """
    global _service
    _service = service


async def _validate_files(files: List[UploadFile]) -> None:
    """校验上传文件大小。

    Args:
        files: 上传文件列表。

    Raises:
        HTTPException: 文件超出大小限制时抛出 413。
    """
    from fastapi import HTTPException
    total = 0
    for f in files:
        size = f.size or 0
        if size > settings.agent_max_file_size:
            raise HTTPException(
                status_code=413,
                detail=f"文件 {f.filename} 超出大小限制（最大 {settings.agent_max_file_size // 1024 // 1024}MB）",
            )
        total += size
    if total > settings.agent_max_total_files:
        raise HTTPException(
            status_code=413,
            detail=f"文件总大小超出限制（最大 {settings.agent_max_total_files // 1024 // 1024}MB）",
        )


@router.post("/chat", response_model=ChatResponse)
def chat_api(
    req: ChatRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """对话接口。

    需要 Bearer Token 认证，且 Token 不得在黑名单中。
    支持多轮对话，自动维护会话上下文。

    Args:
        req: 对话请求体，包含 session_id 和 message。
        current_user: 当前登录用户（自动注入）。
        _blacklist_check: 黑名单检查（自动注入）。

    Returns:
        对话响应对象。
    """
    return _service.chat(
        session_id=req.session_id,
        message=req.message,
        user_id=current_user.id,
        skill_id=req.skill_id,
        remember=req.remember,
    )


@router.post("/chat/stream")
async def chat_stream_api(
    message: str = Form(...),
    session_id: str = Form(...),
    skill_id: Optional[str] = Form(None),
    remember: str = Form("true"),
    files: Optional[List[UploadFile]] = File(None),
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
):
    """流式对话接口。

    支持 multipart/form-data 格式，可同时上传文件。
    返回 SSE 事件流，支持 token 级别流式输出和工具调用状态。
    事件类型：token（流式文本）、tool_start（工具调用开始）、
    tool_end（工具调用结束）、done（流结束）。
    """
    skill_id_int = int(skill_id) if skill_id and skill_id.isdigit() else None
    remember_bool = remember.lower() in ("true", "1", "yes")

    file_data = []
    if files:
        valid_files = [f for f in files if f.filename]
        if valid_files:
            await _validate_files(valid_files)
            for f in valid_files:
                content = await f.read()
                file_data.append((content, f.filename))

    return StreamingResponse(
        _service.chat_stream(
            session_id,
            message,
            user_id=current_user.id,
            skill_id=skill_id_int,
            files=file_data if file_data else None,
            remember=remember_bool,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=List[SessionInfo])
def list_sessions(current_user=Depends(get_current_user)):
    """列出当前用户的所有会话。"""
    return _service.list_sessions(user_id=current_user.id)


@router.post("/sessions", response_model=SessionInfo)
def create_session(
    req: CreateSessionRequest,
    current_user=Depends(get_current_user),
):
    """创建新会话。"""
    return _service.create_session(user_id=current_user.id, title=req.title, skill_id=req.skill_id)


@router.get("/sessions/{session_id}", response_model=SessionInfo)
def get_session(session_id: str, current_user=Depends(get_current_user)):
    """获取会话详情。"""
    return _service.get_session(session_id, user_id=current_user.id)


@router.patch("/sessions/{session_id}/skill")
def update_session_skill(
    session_id: str,
    req: UpdateSessionSkillRequest,
    current_user=Depends(get_current_user),
):
    """设置或清除会话关联的技能。skill_id 传 null 表示取消选择。"""
    _service.set_session_skill(session_id, req.skill_id, user_id=current_user.id)
    return {"ok": True, "skill_id": req.skill_id}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, current_user=Depends(get_current_user)):
    """删除会话。"""
    return _service.delete_session(session_id, user_id=current_user.id)


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
def get_messages(session_id: str, current_user=Depends(get_current_user)):
    """获取会话消息历史。"""
    return _service.get_messages(session_id, user_id=current_user.id)


@router.get("/health", response_model=HealthResponse)
def health_check_api():
    """健康检查接口。"""
    return _service.health_check()

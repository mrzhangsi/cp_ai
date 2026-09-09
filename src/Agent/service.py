"""Agent 业务逻辑层。

封装对话、会话管理的核心逻辑。
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage

from src.common.config import settings
from src.common.models import (
    ChatMessage,
    ChatResponse,
    SessionInfo,
)
from .sessions import SessionManager
from .harness import create_agent_graph


class AgentService:
    """Agent 业务逻辑服务。"""

    def __init__(self) -> None:
        """初始化 Agent 服务。"""
        self.session_manager = SessionManager()
        self.agent_graph = create_agent_graph()
        self._settings = settings
        self._skill_manager = None

    def _get_skill_manager(self):
        """延迟加载 SkillManager（避免循环导入）。"""
        if self._skill_manager is None:
            from src.Skill.skill_manager import SkillManager
            self._skill_manager = SkillManager()
        return self._skill_manager

    def _ensure_session(self, session_id: str, user_id: int) -> None:
        """确保会话存在，不存在则自动创建。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID（隔离标识）。
        """
        try:
            self.session_manager.get_session(session_id)
        except KeyError:
            self.session_manager.create_session_with_id(
                session_id, user_id, title="自动创建"
            )

    def _verify_ownership(self, session_id: str, user_id: int) -> None:
        """验证会话是否属于指定用户。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID。

        Raises:
            HTTPException: 会话不存在或不属于该用户时抛出 404。
        """
        from src.common.database.postgresql.models import AgentSession
        session = (
            self.session_manager._pg_db.query(AgentSession)
            .filter(AgentSession.session_id == session_id)
            .first()
        )
        if not session or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"会话不存在：{session_id}",
            )

    def _build_system_prompt(self, skill_id: Optional[int], user_id: int) -> str:
        """构建 system prompt：默认 prompt + 可选 skill 内容。

        Args:
            skill_id: 技能 ID，为 None 时仅使用默认 prompt。
            user_id: 用户 ID（隔离标识）。

        Returns:
            合并后的 system prompt。
        """
        base = self._settings.agent_system_prompt
        if skill_id is None:
            return base

        try:
            mgr = self._get_skill_manager()
            skill = mgr.get_skill(skill_id, user_id)
            skill_content = skill.get("content", "")
            if skill_content.strip():
                return f"{base}\n\n--- 技能指令 ({skill.get('name', '未知')}) ---\n{skill_content}"
        except Exception:
            pass

        return base

    def _to_langchain_messages(self, history: List[ChatMessage]) -> list:
        """将 ChatMessage 列表转换为 LangChain 消息格式。

        System prompt 由 harness.py 统一注入，此处不处理。

        Args:
            history: ChatMessage 消息历史。

        Returns:
            LangChain 消息列表。
        """
        lc_messages = []
        for m in history:
            if m.role == "user":
                lc_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                lc_messages.append(AIMessage(content=m.content))
        return lc_messages

    def chat(
        self, session_id: str, message: str, user_id: int, skill_id: Optional[int] = None, **kwargs: Any
    ) -> ChatResponse:
        """执行对话。

        Args:
            session_id: 会话 ID。
            message: 用户消息。
            user_id: 用户 ID（隔离标识）。
            skill_id: 附带的技能 ID（可选）。

        Returns:
            对话响应。

        Raises:
            HTTPException: 会话创建失败时抛出。
        """
        self._ensure_session(session_id, user_id)

        if skill_id is not None:
            self.session_manager.set_session_skill(session_id, skill_id)

        user_msg = ChatMessage(role="user", content=message)
        self.session_manager.add_message(session_id, user_msg)

        history = self.session_manager.get_messages(session_id)
        lc_messages = self._to_langchain_messages(history)

        system_prompt = self._build_system_prompt(skill_id, user_id)
        result = self.agent_graph.invoke({"messages": lc_messages, "system_prompt": system_prompt})
        response_text = result["messages"][-1].content

        assistant_msg = ChatMessage(role="assistant", content=response_text)
        self.session_manager.add_message(session_id, assistant_msg)

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            messages=self.session_manager.get_messages(session_id),
        )

    async def chat_stream(
        self, session_id: str, message: str, user_id: int, skill_id: Optional[int] = None, **kwargs: Any
    ):
        """流式对话，yield SSE 事件。

        事件类型：
        - token: LLM 流式输出的单个 token
        - tool_start: 开始调用工具
        - tool_end: 工具执行完毕
        - error: 发生错误
        - done: 流结束

        Args:
            session_id: 会话 ID。
            message: 用户消息。
            user_id: 用户 ID（隔离标识）。
            skill_id: 附带的技能 ID（可选）。

        Yields:
            SSE 格式的事件字符串。
        """
        self._ensure_session(session_id, user_id)

        if skill_id is not None:
            self.session_manager.set_session_skill(session_id, skill_id)

        user_msg = ChatMessage(role="user", content=message)
        self.session_manager.add_message(session_id, user_msg)

        history = self.session_manager.get_messages(session_id)
        lc_messages = self._to_langchain_messages(history)

        system_prompt = self._build_system_prompt(skill_id, user_id)
        response_text = ""

        try:
            async for event in self.agent_graph.astream_events(
                {"messages": lc_messages, "system_prompt": system_prompt}, version="v2"
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = chunk.content
                        response_text += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': tool_name, 'args': tool_input}, ensure_ascii=False)}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    if hasattr(tool_output, "content"):
                        tool_output = tool_output.content
                    elif not isinstance(tool_output, str):
                        tool_output = str(tool_output)
                    yield f"data: {json.dumps({'type': 'tool_end', 'name': tool_name, 'result': tool_output}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        if response_text:
            assistant_msg = ChatMessage(role="assistant", content=response_text)
            self.session_manager.add_message(session_id, assistant_msg)

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    def list_sessions(self, user_id: int) -> List[SessionInfo]:
        """列出用户的所有会话。

        Args:
            user_id: 用户 ID（隔离标识）。
        """
        return self.session_manager.list_sessions(user_id)

    def create_session(self, user_id: int, title: Optional[str] = None, skill_id: Optional[int] = None) -> SessionInfo:
        """创建新会话。

        Args:
            user_id: 用户 ID（隔离标识）。
            title: 会话标题。
            skill_id: 附带的技能 ID。
        """
        return self.session_manager.create_session(user_id, title, skill_id)

    def get_session(self, session_id: str, user_id: Optional[int] = None) -> SessionInfo:
        """获取会话详情。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID（隔离校验），为 None 时不校验。

        Raises:
            HTTPException: 会话不存在或无权访问时抛出 404。
        """
        if user_id is not None:
            self._verify_ownership(session_id, user_id)
        try:
            return self.session_manager.get_session(session_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"会话不存在：{session_id}",
            )

    def delete_session(self, session_id: str, user_id: Optional[int] = None) -> Dict[str, str]:
        """删除会话。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID（隔离校验），为 None 时不校验。

        Raises:
            HTTPException: 会话不存在或无权访问时抛出 404。
        """
        if user_id is not None:
            self._verify_ownership(session_id, user_id)
        try:
            self.session_manager.delete_session(session_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"会话不存在：{session_id}",
            )
        return {"ok": True}

    def get_messages(self, session_id: str, user_id: Optional[int] = None) -> List[ChatMessage]:
        """获取会话消息历史。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID（隔离校验），为 None 时不校验。

        Raises:
            HTTPException: 会话不存在或无权访问时抛出 404。
        """
        if user_id is not None:
            self._verify_ownership(session_id, user_id)
        try:
            return self.session_manager.get_messages(session_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"会话不存在：{session_id}",
            )

    def health_check(self) -> Dict[str, str]:
        """健康检查。"""
        return {"status": "ok", "module": "Agent"}

    def set_session_skill(self, session_id: str, skill_id: Optional[int], user_id: Optional[int] = None) -> None:
        """设置或清除会话关联的技能。

        Args:
            session_id: 会话 ID。
            skill_id: 技能 ID，传 None 表示取消选择。
            user_id: 用户 ID（隔离校验），为 None 时不校验。
        """
        if user_id is not None:
            self._verify_ownership(session_id, user_id)
        try:
            self.session_manager.set_session_skill(session_id, skill_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"会话不存在：{session_id}",
            )

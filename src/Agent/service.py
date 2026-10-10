"""Agent 业务逻辑层。

封装对话、会话管理的核心逻辑。
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

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

logger = logging.getLogger(__name__)


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

    def _build_system_prompt(self, skill_id: Optional[int], user_id: int, summary: Optional[str] = None) -> str:
        """构建 system prompt：默认 prompt + 可选 skill 内容 + 可选摘要。

        Args:
            skill_id: 技能 ID，为 None 时仅使用默认 prompt。
            user_id: 用户 ID（隔离标识）。
            summary: 对话历史摘要，为 None 时不注入。

        Returns:
            合并后的 system prompt。
        """
        base = self._settings.agent_system_prompt

        parts = [base]

        if skill_id is not None:
            try:
                mgr = self._get_skill_manager()
                skill = mgr.get_skill(skill_id, user_id)
                skill_content = skill.get("content", "")
                if skill_content.strip():
                    parts.append(f"--- 技能指令 ({skill.get('name', '未知')}) ---\n{skill_content}")
            except Exception:
                pass

        if summary and summary.strip():
            parts.append(f"--- 对话历史摘要 ---\n{summary}")

        return "\n\n".join(parts)

    def _get_context_for_llm(
        self, session_id: str, skill_id: Optional[int], user_id: int, query: str = ""
    ) -> tuple:
        """统一的上下文处理入口，集成 mem0 双层记忆。

        流程：
        1. mem0 摘要检索：获取该会话的压缩摘要 + cursor。
        2. cursor 裁剪：只取 cursor 之后的未压缩消息。
        3. 滑动窗口：判断是否需要压缩未压缩的消息。
        4. mem0 向量检索：用用户输入检索相关长期记忆。
        5. 拼接：system prompt = 默认 + skill + 摘要 + 长期记忆。

        Args:
            session_id: 会话 ID。
            skill_id: 技能 ID（可选）。
            user_id: 用户 ID（隔离标识）。
            query: 用户当前查询。

        Returns:
            (system_prompt, lc_messages) 元组。
        """
        if not settings.agent_memory_enabled:
            history = self.session_manager.get_messages(session_id)
            system_prompt = self._build_system_prompt(skill_id, user_id)
            return system_prompt, self._to_langchain_messages(history)

        from .memory import get_user_memory
        memory = get_user_memory(user_id)

        # 1. 获取摘要 + cursor
        all_messages = self.session_manager.get_messages(session_id)
        existing_summary, cursor = memory.get_session_summary(session_id)

        # 2. cursor 裁剪：只取未压缩的消息
        if cursor is not None:
            uncompressed = [m for m in all_messages if m.id is not None and m.id > cursor]
        else:
            uncompressed = all_messages

        # 3. 滑动窗口：对未压缩的消息判断是否需要再压缩
        new_summary, context_messages = memory.get_context_messages(uncompressed, existing_summary)

        # 4. 如果产生了新摘要，更新到 mem0
        if new_summary != existing_summary:
            new_cursor = all_messages[-1].id if all_messages and all_messages[-1].id is not None else cursor
            memory.update_session_summary(session_id, new_summary, cursor=new_cursor)

        # 5. 长期记忆：向量检索
        memory_context = ""
        if query:
            memory_context = memory.build_memory_context(query)

        # 6. 拼接 system prompt
        system_prompt = self._build_system_prompt(skill_id, user_id, new_summary or existing_summary)
        if memory_context:
            system_prompt += f"\n\n--- 相关记忆 ---\n{memory_context}"

        return system_prompt, self._to_langchain_messages(context_messages)

    def _to_langchain_messages(
        self, history: List[ChatMessage], files_results: Optional[List[Tuple[str, Dict[str, Any]]]] = None
    ) -> list:
        """将 ChatMessage 列表转换为 LangChain 消息格式。

        System prompt 由 harness.py 统一注入，此处不处理。
        如果提供了 files_results，最后一条用户消息会转换为多模态 content 列表。

        Args:
            history: ChatMessage 消息历史。
            files_results: 文件解析结果列表 [(text, info), ...]，为 None 时纯文本。

        Returns:
            LangChain 消息列表。
        """
        from .multimodal import build_multimodal_content

        lc_messages = []
        has_multimodal = files_results is not None and len(files_results) > 0

        # 找到最后一条用户消息的索引
        last_user_idx = -1
        for i in range(len(history) - 1, -1, -1):
            if history[i].role == "user":
                last_user_idx = i
                break

        for i, m in enumerate(history):
            if m.role == "user":
                if has_multimodal and i == last_user_idx:
                    content_blocks = build_multimodal_content(m.content, files_results)
                    if content_blocks:
                        lc_messages.append(HumanMessage(content=content_blocks))
                    else:
                        lc_messages.append(HumanMessage(content=m.content))
                else:
                    lc_messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                lc_messages.append(AIMessage(content=m.content))
        return lc_messages

    def _check_and_compress(self, session_id: str, user_id: int) -> None:
        """对话结束后检查是否需要压缩，需要则更新摘要。

        每次对话完成后调用，判断未压缩消息是否超过阈值或 token 限制，
        如果需要压缩，生成新摘要并存入 mem0。

        只处理 cursor 之后的未压缩消息，避免重复压缩。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID。
        """
        if not settings.agent_memory_enabled:
            return

        try:
            from .memory import get_user_memory
            memory = get_user_memory(user_id)

            all_messages = self.session_manager.get_messages(session_id)
            existing_summary, cursor = memory.get_session_summary(session_id)

            # 只取未压缩的消息
            if cursor is not None:
                uncompressed = [m for m in all_messages if m.id is not None and m.id > cursor]
            else:
                uncompressed = all_messages

            new_summary, _ = memory.get_context_messages(uncompressed, existing_summary)

            if new_summary != existing_summary:
                new_cursor = all_messages[-1].id if all_messages and all_messages[-1].id is not None else cursor
                memory.update_session_summary(session_id, new_summary, cursor=new_cursor)
                logger.info(
                    "会话 %s 压缩完成：摘要长度 %d, cursor=%s",
                    session_id, len(new_summary or ""), new_cursor,
                )
        except Exception:
            logger.exception("会话 %s 压缩失败", session_id)

    def chat(
        self,
        session_id: str,
        message: str,
        user_id: int,
        skill_id: Optional[int] = None,
        files: Optional[List[Tuple[bytes, str]]] = None,
        remember: bool = True,
        **kwargs: Any,
    ) -> ChatResponse:
        """执行对话。

        Args:
            session_id: 会话 ID。
            message: 用户消息。
            user_id: 用户 ID（隔离标识）。
            skill_id: 附带的技能 ID（可选）。
            files: 上传文件列表 [(file_bytes, filename), ...]（可选）。
            remember: 是否将对话存入长期记忆。

        Returns:
            对话响应。

        Raises:
            HTTPException: 会话创建失败时抛出。
        """
        self._ensure_session(session_id, user_id)

        if skill_id is not None:
            self.session_manager.set_session_skill(session_id, skill_id)

        # 处理多模态文件
        files_results = None
        attachments = None
        if files:
            import asyncio
            from .multimodal import process_files
            files_results, attachments = asyncio.run(
                process_files(files, settings.agent_llm_supports_vision)
            )

        # 构建存储的文本内容
        store_content = message
        if files_results:
            text_parts = [message.strip()] if message.strip() else []
            for text, info in files_results:
                if text:
                    text_parts.append(text)
            store_content = "\n\n".join(text_parts)

        metadata = {"attachments": attachments} if attachments else None
        user_msg = ChatMessage(role="user", content=store_content, metadata=metadata)
        self.session_manager.add_message(session_id, user_msg)

        system_prompt, lc_messages = self._get_context_for_llm(session_id, skill_id, user_id, message)

        # 如果有文件，重新构建最后一条消息为多模态
        if files_results:
            lc_messages = self._to_langchain_messages(
                self.session_manager.get_messages(session_id), files_results
            )

        from .trace import TraceCollector
        collector = TraceCollector()
        collector.messages_in_context = len(lc_messages)

        try:
            collector.start_llm()
            result = self.agent_graph.invoke({"messages": lc_messages, "system_prompt": system_prompt})
            last_msg = result["messages"][-1]
            resp_meta = getattr(last_msg, "response_metadata", None) or {}
            usage_meta = getattr(last_msg, "usage_metadata", None)
            logger.debug("chat() response_metadata=%s, usage_metadata=%s", resp_meta, usage_meta)
            collector.end_llm(resp_meta, usage_meta)
            response_text = last_msg.content
        except Exception as e:
            collector.end_llm()
            collector.set_error(str(e))
            raise
        finally:
            if settings.agent_trace_enabled:
                collector.save(
                    session_id=session_id,
                    user_id=user_id,
                    messages_in_context=collector.messages_in_context,
                )

        assistant_msg = ChatMessage(role="assistant", content=response_text)
        self.session_manager.add_message(session_id, assistant_msg)

        # 写入长期记忆
        if remember and settings.agent_memory_enabled:
            from .memory import get_user_memory
            memory = get_user_memory(user_id)
            memory.add([
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text},
            ])

        self._check_and_compress(session_id, user_id)

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            messages=self.session_manager.get_messages(session_id),
        )

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        user_id: int,
        skill_id: Optional[int] = None,
        files: Optional[List[Tuple[bytes, str]]] = None,
        remember: bool = True,
        **kwargs: Any,
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
            files: 上传文件列表 [(file_bytes, filename), ...]（可选）。
            remember: 是否将对话存入长期记忆。

        Yields:
            SSE 格式的事件字符串。
        """
        self._ensure_session(session_id, user_id)

        if skill_id is not None:
            self.session_manager.set_session_skill(session_id, skill_id)

        # 处理多模态文件
        files_results = None
        attachments = None
        if files:
            from .multimodal import process_files
            files_results, attachments = await process_files(
                files, settings.agent_llm_supports_vision
            )

        # 构建存储的文本内容
        store_content = message
        if files_results:
            text_parts = [message.strip()] if message.strip() else []
            for text, info in files_results:
                if text:
                    text_parts.append(text)
            store_content = "\n\n".join(text_parts)

        metadata = {"attachments": attachments} if attachments else None
        user_msg = ChatMessage(role="user", content=store_content, metadata=metadata)
        self.session_manager.add_message(session_id, user_msg)

        system_prompt, lc_messages = self._get_context_for_llm(session_id, skill_id, user_id, message)

        # 如果有文件，重新构建最后一条消息为多模态
        if files_results:
            all_msgs = self.session_manager.get_messages(session_id)
            lc_messages = self._to_langchain_messages(all_msgs, files_results)
        response_text = ""

        from .trace import TraceCollector
        collector = TraceCollector()
        collector.messages_in_context = len(lc_messages)

        try:
            async for event in self.agent_graph.astream_events(
                {"messages": lc_messages, "system_prompt": system_prompt}, version="v2"
            ):
                kind = event["event"]

                if kind == "on_chat_model_start":
                    collector.start_llm()

                elif kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = chunk.content
                        response_text += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                    if chunk:
                        chunk_usage = getattr(chunk, "usage_metadata", None)
                        if chunk_usage and collector.total_tokens == 0:
                            collector.end_llm(usage_metadata=chunk_usage)

                elif kind == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    resp_meta = getattr(output, "response_metadata", None) or {}
                    usage_meta = getattr(output, "usage_metadata", None)
                    logger.debug(
                        "on_chat_model_end: type=%s, response_metadata=%s, usage_metadata=%s",
                        type(output).__name__, resp_meta, usage_meta,
                    )
                    collector.end_llm(resp_meta, usage_meta)

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    collector.start_tool(tool_name)
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': tool_name}, ensure_ascii=False)}\n\n"

                elif kind == "on_tool_end":
                    collector.end_tool()
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    if hasattr(tool_output, "content"):
                        tool_output = tool_output.content
                    elif not isinstance(tool_output, str):
                        tool_output = str(tool_output)
                    yield f"data: {json.dumps({'type': 'tool_end', 'name': tool_name, 'result': tool_output}, ensure_ascii=False)}\n\n"

        except Exception as e:
            collector.set_error(str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        if response_text:
            assistant_msg = ChatMessage(role="assistant", content=response_text)
            self.session_manager.add_message(session_id, assistant_msg)

            # 写入长期记忆
            if remember and settings.agent_memory_enabled:
                from .memory import get_user_memory
                mem = get_user_memory(user_id)
                mem.add([
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": response_text},
                ])

        self._check_and_compress(session_id, user_id)

        if settings.agent_trace_enabled:
            collector.save(
                session_id=session_id,
                user_id=user_id,
                messages_in_context=collector.messages_in_context,
            )

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

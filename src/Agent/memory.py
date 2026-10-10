"""Agent 记忆管理模块。

双层记忆架构，统一由 mem0 管理：

长期记忆（事实提取）：
- mem0 自动从对话中提取用户事实并存储
- 语义搜索检索相关事实，注入 system prompt

短期记忆（会话摘要压缩）：
- 滑动窗口控制上下文长度
- 超过阈值时压缩旧消息为摘要，摘要存储在 mem0 中
- 摘要与近期消息无重叠，通过 mem0 按 session_id 隔离
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common.config import settings

logger = logging.getLogger(__name__)

# 粗略估算：1 token ≈ 2 个中文字符 或 4 个英文字符，取平均 3 字符/token
_CHARS_PER_TOKEN = 3

# 模块级单例，每个 user_id 一个 Memory 实例
_memory_instances: Dict[int, Any] = {}


class AgentMemory:
    """Agent 记忆管理器，封装 mem0。

    职责：
    1. 长期记忆：事实提取 + 语义搜索
    2. 短期记忆：会话摘要压缩（摘要存储在 mem0 中）
    """

    def __init__(self, user_id: int) -> None:
        """初始化 AgentMemory。

        Args:
            user_id: 用户 ID（隔离标识）。
        """
        self._user_id = user_id

    def _get_memory(self):
        """获取或创建 mem0 Memory 实例。"""
        if self._user_id not in _memory_instances:
            try:
                from mem0 import Memory

                config = {
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": settings.agent_llm_model_id,
                            "api_key": settings.modelscope_api_key or settings.agent_llm_api_key,
                            "openai_base_url": settings.agent_llm_base_url,
                        },
                    },
                    "embedder": {
                        "provider": "openai",
                        "config": {
                            "model": settings.embedding_model_name,
                            "embedding_dims": settings.embedding_dimensions,
                            "openai_base_url": settings.embedding_model_api_base,
                            "api_key": settings.embedding_model_api_key,
                        },
                    },
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "host": settings.pgvector_host,
                            "port": settings.pgvector_port,
                            "dbname": settings.pgvector_dbname,
                            "user": settings.pgvector_user,
                            "password": settings.pgvector_password,
                            "embedding_model_dims": settings.embedding_dimensions,
                        },
                    },
                }

                _memory_instances[self._user_id] = Memory.from_config(config)
                logger.info("mem0 Memory 实例已创建 (user_id=%d)", self._user_id)
            except Exception:
                logger.exception("mem0 Memory 实例创建失败 (user_id=%d)", self._user_id)
                raise
        return _memory_instances[self._user_id]

    # ==================== 长期记忆（事实提取） ====================

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相关长期记忆。

        Args:
            query: 搜索查询文本。
            top_k: 返回的最大记忆条数。
            filters: 过滤条件，如 {"user_id": "123"}。

        Returns:
            相关记忆列表。
        """
        top_k = top_k or settings.agent_memory_top_k
        filters = filters or {"user_id": str(self._user_id)}

        try:
            memory = self._get_memory()
            results = memory.search(query, filters=filters, top_k=top_k)
            if results and "results" in results:
                return results["results"]
            return results if isinstance(results, list) else []
        except Exception:
            logger.exception("mem0 search 失败 (user_id=%d)", self._user_id)
            return []

    def add(
        self,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """将对话写入长期记忆。

        mem0 会自动从对话中提取事实并存储。

        Args:
            messages: 消息列表。
            metadata: 附加元数据。

        Returns:
            mem0 返回的 memory_id，失败时返回 None。
        """
        try:
            memory = self._get_memory()
            result = memory.add(messages, user_id=str(self._user_id), metadata=metadata or {})
            if result and isinstance(result, dict):
                memory_id = result.get("id") or result.get("memory_id")
                logger.info("mem0 add 成功 (user_id=%d, id=%s)", self._user_id, memory_id)
                return memory_id
            logger.info("mem0 add 成功 (user_id=%d)", self._user_id)
            return None
        except Exception:
            logger.exception("mem0 add 失败 (user_id=%d)", self._user_id)
            return None

    def get_all(self) -> List[Dict[str, Any]]:
        """获取用户的所有长期记忆。"""
        try:
            memory = self._get_memory()
            results = memory.get_all(filters={"user_id": str(self._user_id)})
            if results and "results" in results:
                return results["results"]
            return results if isinstance(results, list) else []
        except Exception:
            logger.exception("mem0 get_all 失败 (user_id=%d)", self._user_id)
            return []

    def delete(self, memory_id: str) -> bool:
        """删除指定记忆。"""
        try:
            memory = self._get_memory()
            memory.delete(memory_id)
            logger.info("mem0 delete 成功 (user_id=%d, id=%s)", self._user_id, memory_id)
            return True
        except Exception:
            logger.exception("mem0 delete 失败 (user_id=%d, id=%s)", self._user_id, memory_id)
            return False

    def build_memory_context(self, query: str) -> str:
        """为 LLM 构建长期记忆上下文文本。

        Args:
            query: 用户当前查询。

        Returns:
            格式化的记忆上下文文本。
        """
        results = self.search(query)
        if not results:
            return ""

        lines = []
        for r in results:
            memory_text = r.get("memory", "")
            if memory_text:
                lines.append(f"- {memory_text}")

        return "\n".join(lines) if lines else ""

    # ==================== 短期记忆（会话摘要压缩） ====================

    def get_session_summary(self, session_id: str) -> Tuple[Optional[str], Optional[int]]:
        """获取会话摘要和压缩游标（从 mem0 中检索）。

        通过 payload 中的 session_id 字段过滤会话摘要。
        返回的 cursor 表示已压缩到的消息 ID，cursor 之后的消息为未压缩的。

        Args:
            session_id: 会话 ID。

        Returns:
            (摘要文本, cursor) 元组。无摘要时返回 (None, None)。
        """
        try:
            memory = self._get_memory()
            results = memory.get_all(
                filters={"user_id": str(self._user_id), "session_id": session_id},
                top_k=1,
            )
            items = results.get("results", []) if isinstance(results, dict) else results
            if items:
                item = items[0]
                summary_text = item.get("memory", "")
                # 从 payload 中读取 cursor（存在 metadata 中）
                payload = item.get("payload") or {}
                cursor = payload.get("compressed_cursor")
                if summary_text:
                    return summary_text, int(cursor) if cursor is not None else None
            return None, None
        except Exception:
            logger.exception("获取会话摘要失败 (user_id=%d, session=%s)", self._user_id, session_id)
            return None, None

    def update_session_summary(
        self,
        session_id: str,
        summary_text: str,
        cursor: Optional[int] = None,
    ) -> None:
        """更新会话摘要（删除旧的，写入新的）。

        Args:
            session_id: 会话 ID。
            summary_text: 新的摘要文本。
            cursor: 已压缩到的消息 ID，用于追踪压缩边界。
        """
        try:
            memory = self._get_memory()

            # 删除旧摘要
            results = memory.get_all(
                filters={"user_id": str(self._user_id), "session_id": session_id},
                top_k=10,
            )
            items = results.get("results", []) if isinstance(results, dict) else results
            for item in items:
                item_id = item.get("id")
                if item_id:
                    memory.delete(item_id)

            # 写入新摘要（cursor 存在 metadata 中）
            metadata: Dict[str, Any] = {
                "type": "session_summary",
                "session_id": session_id,
            }
            if cursor is not None:
                metadata["compressed_cursor"] = cursor

            memory.add(
                [{"role": "assistant", "content": summary_text}],
                user_id=str(self._user_id),
                metadata=metadata,
            )
            logger.info(
                "会话摘要已更新 (user_id=%d, session=%s, len=%d, cursor=%s)",
                self._user_id, session_id, len(summary_text), cursor,
            )
        except Exception:
            logger.exception("更新会话摘要失败 (user_id=%d, session=%s)", self._user_id, session_id)

    # ==================== 滑动窗口压缩逻辑 ====================

    def get_context_messages(
        self,
        all_messages: List[Any],
        existing_summary: Optional[str] = None,
    ) -> Tuple[Optional[str], List[Any]]:
        """获取发给 LLM 的上下文消息（摘要 + 近期消息，无重叠）。

        策略：
        - 消息数 ≤ window_size → 不压缩，返回全部消息和现有摘要。
        - token 超限 → 压缩所有消息，仅保留最近一轮（2条）。
        - 消息数 > summary_threshold → 压缩旧消息，保留最近 window 条。

        Args:
            all_messages: 从数据库读取的全量消息列表。
            existing_summary: 已有的对话摘要。

        Returns:
            (摘要, 发给 LLM 的消息列表) 元组。
        """
        if len(all_messages) <= settings.agent_memory_window_size:
            return existing_summary, all_messages

        total_tokens = self._estimate_tokens(all_messages)
        if total_tokens > settings.agent_memory_token_limit:
            keep_count = min(2, len(all_messages))
            to_compress = all_messages[:-keep_count]
            recent = all_messages[-keep_count:]
            new_summary = self._merge_summary(existing_summary, to_compress)
            logger.info(
                "Token 超限压缩：%d 条消息 -> 摘要 + %d 条近期消息",
                len(to_compress), keep_count,
            )
            return new_summary, recent

        if len(all_messages) > settings.agent_memory_summary_threshold:
            to_compress = all_messages[:-settings.agent_memory_window_size]
            recent = all_messages[-settings.agent_memory_window_size:]
            new_summary = self._merge_summary(existing_summary, to_compress)
            logger.info(
                "消息超限压缩：%d 条消息 -> 摘要 + %d 条近期消息",
                len(to_compress), settings.agent_memory_window_size,
            )
            return new_summary, recent

        return existing_summary, all_messages

    def _estimate_tokens(self, messages: List[Any]) -> int:
        """粗略估算消息列表的 token 数量。"""
        total_chars = sum(len(m.content) for m in messages)
        return total_chars // _CHARS_PER_TOKEN

    def _merge_summary(
        self,
        existing_summary: Optional[str],
        messages: List[Any],
    ) -> str:
        """将消息合并为摘要（直接拼接，不调用 LLM）。

        摘要文本存储在 mem0 中，由 mem0 管理。
        这里只做简单的文本合并，避免额外的 LLM 调用。

        Args:
            existing_summary: 已有摘要。
            messages: 需要压缩的消息列表。

        Returns:
            合并后的摘要文本。
        """
        lines = []
        if existing_summary:
            lines.append(existing_summary)
            lines.append("---")

        for msg in messages:
            role_label = "用户" if msg.role == "user" else "助手"
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            lines.append(f"{role_label}：{content}")

        return "\n".join(lines)


def get_user_memory(user_id: int) -> AgentMemory:
    """获取用户专属的 AgentMemory 实例。

    Args:
        user_id: 用户 ID。

    Returns:
        AgentMemory 实例。
    """
    return AgentMemory(user_id)

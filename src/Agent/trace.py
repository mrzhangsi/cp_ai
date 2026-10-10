"""Agent Trace 观测模块。

独立于日志系统，每次对话生成一条 trace，以 JSONL 格式追加写入文件。
每次运行生成独立文件：logs/trace_YYYYMMDD_HHMMSS.jsonl
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_trace_file = None


def _get_trace_file():
    """获取当前运行的 trace 文件句柄（懒初始化）。"""
    global _trace_file
    if _trace_file is None:
        os.makedirs("logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join("logs", f"trace_{timestamp}.jsonl")
        _trace_file = open(path, "a+", encoding="utf-8")
    return _trace_file


class TraceCollector:
    """Trace 数据采集器。

    在一次对话过程中收集 LLM 调用、工具执行、Token 消耗等指标。
    """

    def __init__(self) -> None:
        """初始化采集器，记录开始时间。"""
        self._start_time = time.monotonic()
        self._started_at = datetime.now(timezone.utc)

        self.llm_calls: int = 0
        self.llm_total_ms: int = 0
        self._llm_start: Optional[float] = None

        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

        self.tool_calls: int = 0
        self.tool_total_ms: int = 0
        self.tool_names: List[str] = []
        self._tool_start: Optional[float] = None
        self._current_tool_name: Optional[str] = None

        self.messages_in_context: int = 0
        self.memory_compressed: bool = False

        self.status: str = "success"
        self.error_message: Optional[str] = None

    def start_llm(self) -> None:
        """记录 LLM 调用开始。"""
        self.llm_calls += 1
        self._llm_start = time.monotonic()

    def end_llm(self, response_metadata: Optional[Dict[str, Any]] = None, usage_metadata: Optional[Any] = None) -> None:
        """记录 LLM 调用结束，提取 token 使用量。

        Args:
            response_metadata: LLM 响应元数据，可能包含 token_usage。
            usage_metadata: LangChain UsageMetadata 对象，包含 input_tokens/output_tokens/total_tokens。
        """
        if self._llm_start is not None:
            elapsed = int((time.monotonic() - self._llm_start) * 1000)
            self.llm_total_ms += elapsed
            self._llm_start = None

        # 优先从 usage_metadata 提取（可能是 dict 或 LangChain UsageMetadata 对象）
        if usage_metadata is not None:
            if self.total_tokens == 0:
                if isinstance(usage_metadata, dict):
                    self.prompt_tokens = usage_metadata.get("input_tokens", 0)
                    self.completion_tokens = usage_metadata.get("output_tokens", 0)
                    self.total_tokens = usage_metadata.get("total_tokens", 0)
                else:
                    self.prompt_tokens = getattr(usage_metadata, "input_tokens", 0)
                    self.completion_tokens = getattr(usage_metadata, "output_tokens", 0)
                    self.total_tokens = getattr(usage_metadata, "total_tokens", 0)
            return

        # 从 response_metadata 字典提取
        if response_metadata:
            usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
            if usage:
                self.prompt_tokens += usage.get("prompt_tokens", 0)
                self.completion_tokens += usage.get("completion_tokens", 0)
                self.total_tokens += usage.get("total_tokens", 0)

    def start_tool(self, name: str) -> None:
        """记录工具调用开始。

        Args:
            name: 工具名称。
        """
        self.tool_calls += 1
        self._tool_start = time.monotonic()
        self._current_tool_name = name

    def end_tool(self) -> None:
        """记录工具调用结束。"""
        if self._tool_start is not None:
            elapsed = int((time.monotonic() - self._tool_start) * 1000)
            self.tool_total_ms += elapsed
            self._tool_start = None

        if self._current_tool_name:
            self.tool_names.append(self._current_tool_name)
            self._current_tool_name = None

    def set_error(self, message: str) -> None:
        """标记对话为失败状态。

        Args:
            message: 错误信息。
        """
        self.status = "error"
        self.error_message = message

    def save(
        self,
        session_id: str,
        user_id: int,
        messages_in_context: int = 0,
        memory_compressed: bool = False,
    ) -> None:
        """将 trace 追加写入文件。

        Args:
            session_id: 会话 ID。
            user_id: 用户 ID。
            messages_in_context: 发给 LLM 的消息数量。
            memory_compressed: 本轮是否触发记忆压缩。
        """
        finished_at = datetime.now(timezone.utc)
        total_ms = int((time.monotonic() - self._start_time) * 1000)

        trace = {
            "trace_id": uuid.uuid4().hex[:16],
            "session_id": session_id,
            "user_id": user_id,
            "started_at": self._started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_duration_ms": total_ms,
            "llm_calls": self.llm_calls,
            "llm_total_duration_ms": self.llm_total_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "tool_total_duration_ms": self.tool_total_ms,
            "tool_names": self.tool_names if self.tool_names else None,
            "memory_compressed": memory_compressed,
            "messages_in_context": messages_in_context,
            "status": self.status,
            "error_message": self.error_message,
        }

        try:
            f = _get_trace_file()
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
            f.flush()
        except Exception:
            logger.exception("Trace 写入失败")

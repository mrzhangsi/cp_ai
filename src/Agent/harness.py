"""Agent 核心行为模块。

使用 LangGraph 定义 Agent 工作流：消息接收 → LLM 推理 → 工具调用 → 响应生成。
System prompt 统一在此处注入，调用方无需处理。
"""
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .llm import create_llm
from .tools import TOOLS
from src.common.config import settings


class AgentState(TypedDict):
    """Agent 状态。"""
    messages: Annotated[list, add_messages]
    system_prompt: str


def create_agent_graph(tools: Optional[list] = None):
    """创建 Agent 工作流图。

    Args:
        tools: 可用工具列表，为 None 时使用默认工具。

    Returns:
        编译好的 LangGraph 工作流。
    """
    llm = create_llm()
    system_prompt = settings.agent_system_prompt

    if tools is None:
        tools = TOOLS

    llm_with_tools = llm.bind_tools(tools) if tools else llm

    def agent_node(state: AgentState):
        """Agent 节点：注入 system prompt 后调用 LLM。"""
        messages = state["messages"]

        has_system = any(
            isinstance(m, SystemMessage)
            for m in messages
        )
        if not has_system:
            prompt = state.get("system_prompt") or system_prompt
            messages = [SystemMessage(content=prompt)] + list(messages)

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)

    if tools:
        from langgraph.prebuilt import ToolNode

        tool_node = ToolNode(tools)
        workflow.add_node("tools", tool_node)

        def should_continue(state: AgentState):
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"
            return END

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")
    else:
        workflow.set_entry_point("agent")
        workflow.add_edge("agent", END)

    return workflow.compile()

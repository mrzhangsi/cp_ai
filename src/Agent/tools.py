"""Agent 工具模块。

定义 Agent 可调用的工具列表。
当前为空，可通过 MCP 集成或自定义工具扩展。
"""
from typing import List

from langchain_core.tools import tool


TOOLS: List = []

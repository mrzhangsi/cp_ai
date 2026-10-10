"""LLM 工厂模块。

封装 LLM 的创建和配置，从 common/config.py 读取 agent_llm_* 配置。
"""
from typing import Optional

from langchain_openai import ChatOpenAI

from src.common.config import settings


def create_llm(
    model_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> ChatOpenAI:
    """创建 LLM 实例。

    优先使用参数，未提供时从 Settings 读取 agent_llm_* 配置。

    Args:
        model_id: 模型 ID。
        api_key: API 密钥。
        base_url: API 基础 URL。
        **kwargs: 传递给 ChatOpenAI 的额外参数。

    Returns:
        配置好的 ChatOpenAI 实例。

    Raises:
        ValueError: 配置参数不完整时抛出。
    """
    model = model_id or settings.agent_llm_model_id
    key = api_key or settings.agent_llm_api_key
    url = base_url or settings.agent_llm_base_url

    if not all([model, key, url]):
        raise ValueError("Agent LLM 配置不完整，缺少必要参数")

    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=url,
        streaming=True,
        stream_usage=True,
        **kwargs,
    )

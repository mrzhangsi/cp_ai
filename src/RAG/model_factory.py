"""模型工厂模块。

负责加载和配置 LLM 及 Embedding 模型实例。
从 config.py 读取配置，支持通过参数动态覆盖。
"""
from typing import Any, Optional

from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from llama_index.llms.openai_like import OpenAILike

from src.common.config import settings as app_settings


class ModelFactory:
    """模型工厂类。

    根据配置创建 LLM 和 Embedding 模型实例，
    支持通过方法参数动态覆盖默认配置。
    """

    def __init__(self, settings=None, **kwargs: Any) -> None:
        """初始化模型工厂。

        Args:
            settings: RAG 配置实例，为 None 时使用模块级单例。
            **kwargs: 预留扩展参数。
        """
        self.settings = settings or app_settings

    def get_embedding_model(self, **kwargs: Any) -> BaseEmbedding:
        """创建 Embedding 模型实例。

        Args:
            **kwargs: 可选配置参数，覆盖默认值：
                - embedding_model_name: 模型名称
                - embedding_model_api_base: API 基础 URL
                - embedding_model_api_key: API 密钥
                - embed_batch_size: 批处理大小

        Returns:
            配置好的 Embedding 模型实例。

        Raises:
            ValueError: 配置参数不完整时抛出。
            ConnectionError: 创建模型失败时抛出。
        """
        try:
            model_name = kwargs.get("embedding_model_name", self.settings.embedding_model_name)
            api_base = kwargs.get("embedding_model_api_base", self.settings.embedding_model_api_base)
            api_key = kwargs.get("embedding_model_api_key", self.settings.embedding_model_api_key)
            batch_size = kwargs.get("embed_batch_size", self.settings.embedding_batch_size)

            if not all([model_name, api_base, api_key]):
                raise ValueError("Embedding 模型配置不完整，缺少必要参数")

            return OpenAILikeEmbedding(
                model_name=model_name,
                api_base=api_base,
                api_key=api_key,
                embed_batch_size=batch_size,
            )
        except ValueError:
            raise
        except Exception as e:
            raise ConnectionError(f"创建 Embedding 模型失败: {e}") from e

    def get_llm(self, **kwargs: Any) -> LLM:
        """创建 LLM 模型实例。

        Args:
            **kwargs: 可选配置参数，覆盖默认值：
                - llm_model_id: 模型 ID
                - llm_api_key: API 密钥
                - llm_base_url: API 基础 URL
                - is_chat_model: 是否为聊天模型
                - is_function_calling_model: 是否支持函数调用

        Returns:
            配置好的 LLM 模型实例。

        Raises:
            ValueError: 配置参数不完整时抛出。
            ConnectionError: 创建模型失败时抛出。
        """
        try:
            model_id = kwargs.get("llm_model_id", self.settings.rag_llm_model_id)
            api_key = kwargs.get("llm_api_key", self.settings.rag_llm_api_key)
            base_url = kwargs.get("llm_base_url", self.settings.rag_llm_base_url)
            is_chat = kwargs.get("is_chat_model", self.settings.rag_llm_is_chat_model)
            is_function_calling = kwargs.get(
                "is_function_calling_model", self.settings.rag_llm_is_function_calling_model
            )

            if not all([model_id, api_key, base_url]):
                raise ValueError("LLM 模型配置不完整，缺少必要参数")

            return OpenAILike(
                model=model_id,
                api_key=api_key,
                api_base=base_url,
                is_chat_model=is_chat,
                is_function_calling_model=is_function_calling,
            )
        except ValueError:
            raise
        except Exception as e:
            raise ConnectionError(f"创建 LLM 模型失败: {e}") from e

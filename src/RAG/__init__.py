"""RAG 模块。

提供基于 ChromaDB 向量数据库的检索增强生成（RAG）功能，
包括文档加载、向量索引构建、语义检索和 RAGAS 质量评估。
"""
from src.common.config import Settings as RAGSettings
from src.common.models import QueryRequest, QueryResponse, SourceNode, RAGASResult

from .router import init_service
from .service import RAGService

__all__ = [
    "RAGSettings",
    "RAGService",
    "QueryRequest",
    "QueryResponse",
    "SourceNode",
    "RAGASResult",
    "init_service",
]

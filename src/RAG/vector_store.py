"""ChromaDB 向量存储管理器。

提供文档 embedding、存储、检索功能，按用户隔离集合。
使用 ChromaDB 作为向量数据库，LlamaIndex 的 embedding 模型生成向量。
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

import chromadb
from llama_index.core import Document
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeWithScore, TextNode

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """ChromaDB 向量存储管理器（按用户隔离）。

    每个用户拥有独立的 ChromaDB 集合，集合名格式: {prefix}_{user_id}。
    """

    def __init__(
        self,
        persist_dir: str,
        collection_prefix: str,
        embed_model: BaseEmbedding,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        **kwargs: Any,
    ) -> None:
        """初始化向量存储管理器。

        Args:
            persist_dir: ChromaDB 持久化目录。
            collection_prefix: 集合名前缀，实际集合名为 {prefix}_{user_id}。
            embed_model: LlamaIndex Embedding 模型实例。
            chunk_size: 文档切片大小（字符数）。
            chunk_overlap: 切片重叠大小。
            **kwargs: 预留扩展参数。
        """
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection_prefix = collection_prefix
        self._embed_model = embed_model
        self._splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _get_collection_name(self, user_id: int) -> str:
        """获取用户的集合名。"""
        return f"{self._collection_prefix}_{user_id}"

    def _get_or_create_collection(self, user_id: int):
        """获取或创建用户的 ChromaDB 集合。"""
        name = self._get_collection_name(user_id)
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        documents: List[Document],
        user_id: int,
        **kwargs: Any,
    ) -> tuple[int, List[str]]:
        """将文档列表切片、embedding 后存入用户的 ChromaDB 集合。

        Args:
            documents: LlamaIndex Document 对象列表。
            user_id: 用户 ID，用于确定目标集合。
            **kwargs: 预留扩展参数。

        Returns:
            (写入的 chunk 数量, 所有 chunk ID 列表)。

        Raises:
            ValueError: 文档列表为空时抛出。
            RuntimeError: 写入失败时抛出。
        """
        if not documents:
            raise ValueError("文档列表不能为空")

        try:
            collection = self._get_or_create_collection(user_id)
            nodes = self._splitter.get_nodes_from_documents(documents)
            if not nodes:
                raise ValueError("文档切片后为空")

            batch_size = kwargs.get("batch_size", 100)
            total_count = 0
            all_ids: List[str] = []

            for i in range(0, len(nodes), batch_size):
                batch_nodes = nodes[i : i + batch_size]
                texts = [node.text for node in batch_nodes]
                embeddings = self._embed_model.get_text_embedding_batch(texts)
                ids = [
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}:{text}"))
                    for text in texts
                ]
                metadatas = [
                    {
                        "source": node.metadata.get("source", ""),
                        "file_name": node.metadata.get("file_name", ""),
                        "user_id": str(user_id),
                        **{
                            k: str(v)
                            for k, v in node.metadata.items()
                            if k not in ("source", "file_name")
                        },
                    }
                    for node in batch_nodes
                ]

                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                )
                total_count += len(batch_nodes)
                all_ids.extend(ids)

            logger.info("用户 %d: 成功写入 %d 个 chunk", user_id, total_count)
            return total_count, all_ids
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"写入 ChromaDB 失败: {e}") from e

    def delete_by_ids(
        self,
        ids: List[str],
        user_id: int,
        **kwargs: Any,
    ) -> int:
        """根据 chunk ID 列表从用户的集合中删除向量。

        Args:
            ids: 要删除的 chunk ID 列表。
            user_id: 用户 ID，用于确定目标集合。
            **kwargs: 预留扩展参数。

        Returns:
            实际删除的 chunk 数量。
        """
        if not ids:
            return 0

        try:
            collection = self._get_or_create_collection(user_id)
            # ChromaDB delete 支持批量删除，分批处理避免超限
            batch_size = kwargs.get("batch_size", 100)
            deleted = 0
            for i in range(0, len(ids), batch_size):
                batch = ids[i : i + batch_size]
                collection.delete(ids=batch)
                deleted += len(batch)
            logger.info("用户 %d: 从 ChromaDB 删除了 %d 个 chunk", user_id, deleted)
            return deleted
        except Exception as e:
            raise RuntimeError(f"从 ChromaDB 删除失败: {e}") from e

    def delete_by_file_name(
        self,
        file_name: str,
        user_id: int,
        **kwargs: Any,
    ) -> int:
        """根据 file_name 元数据从用户的集合中删除所有匹配的向量。

        用于清理旧文档（没有 chunk_ids 字段的文档）。

        Args:
            file_name: 文件名（metadata 中的 file_name）。
            user_id: 用户 ID，用于确定目标集合。
            **kwargs: 预留扩展参数。

        Returns:
            删除的 chunk 数量（近似值）。
        """
        try:
            collection = self._get_or_create_collection(user_id)
            if collection.count() == 0:
                return 0

            # 先查询获取所有匹配的 ID
            results = collection.get(
                where={"file_name": file_name},
            )
            if not results or not results.get("ids"):
                return 0

            ids_to_delete = results["ids"]
            collection.delete(ids=ids_to_delete)
            logger.info(
                "用户 %d: 通过 file_name='%s' 删除了 %d 个 chunk",
                user_id, file_name, len(ids_to_delete),
            )
            return len(ids_to_delete)
        except Exception as e:
            raise RuntimeError(f"通过 file_name 删除失败: {e}") from e

    def retrieve(
        self,
        query_text: str,
        user_id: int,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[NodeWithScore]:
        """根据查询文本在用户的集合中检索。

        Args:
            query_text: 查询文本。
            user_id: 用户 ID，用于确定检索集合。
            top_k: 返回结果数量。
            **kwargs: 预留扩展参数。

        Returns:
            检索到的 NodeWithScore 列表。

        Raises:
            ValueError: 查询文本为空时抛出。
            RuntimeError: 检索失败时抛出。
        """
        if not query_text or not query_text.strip():
            raise ValueError("查询文本不能为空")

        collection = self._get_or_create_collection(user_id)
        if collection.count() == 0:
            return []

        try:
            query_embedding = self._embed_model.get_text_embedding(query_text)
            actual_k = min(top_k, collection.count())
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_k,
            )

            nodes_with_scores = []
            for i, doc in enumerate(results["documents"][0]):
                score = 1.0 - results["distances"][0][i] if results.get("distances") else None
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                node = TextNode(text=doc, metadata=metadata)
                nodes_with_scores.append(NodeWithScore(node=node, score=score))

            return nodes_with_scores
        except Exception as e:
            raise RuntimeError(f"检索失败: {e}") from e

    def count(self, user_id: int) -> int:
        """返回用户集合中的文档数量。"""
        collection = self._get_or_create_collection(user_id)
        return collection.count()

    def delete_all(self, user_id: int, **kwargs: Any) -> None:
        """清空用户集合中的所有文档。"""
        try:
            name = self._get_collection_name(user_id)
            self._client.delete_collection(name)
            logger.info("已清空用户 %d 的集合: %s", user_id, name)
        except Exception as e:
            raise RuntimeError(f"清空集合失败: {e}") from e

    def health_check(self, user_id: Optional[int] = None, **kwargs: Any) -> Dict[str, Any]:
        """检查 ChromaDB 状态。"""
        result: Dict[str, Any] = {"status": "ok", "persist_dir": "chroma_storage"}
        if user_id is not None:
            result["user_count"] = self.count(user_id)
            result["user_collection"] = self._get_collection_name(user_id)
        return result

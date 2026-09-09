"""RAG 查询业务逻辑层。

封装文档加载、向量存储、检索、生成和评估的核心业务逻辑。
使用 ChromaDB 作为向量数据库（按用户隔离），RAGAS 作为评估框架。
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile, status
from llama_index.core import Document, Settings
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM
from sqlalchemy.orm import Session

from src.common.config import settings as app_settings
from src.common.database.postgresql.models import RAGDocument
from src.common.models import QueryResponse, SourceNode
from .model_factory import ModelFactory
from .ragas_eval import RAGASEvaluator
from .vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 查询服务类。

    提供文档入库、语义检索、LLM 生成和 RAGAS 评估等核心功能。
    每个用户的知识库完全隔离。
    """

    def __init__(
        self,
        settings=None,
        llm: Optional[LLM] = None,
        embed_model: Optional[BaseEmbedding] = None,
        **kwargs: Any,
    ) -> None:
        """初始化 RAG 服务。

        Args:
            settings: 配置实例，为 None 时使用默认配置。
            llm: 自定义 LLM 实例，为 None 时从配置创建。
            embed_model: 自定义 Embedding 实例，为 None 时从配置创建。
            **kwargs: 预留扩展参数。
        """
        self.settings = settings or app_settings
        self.model_factory = ModelFactory(self.settings)

        Settings.llm = llm or self.model_factory.get_llm()
        Settings.embed_model = embed_model or self.model_factory.get_embedding_model()

        self.vector_store = VectorStoreManager(
            persist_dir=self.settings.chroma_persist_dir,
            collection_prefix=self.settings.chroma_collection_name,
            embed_model=Settings.embed_model,
        )

        self.ragas_evaluator = RAGASEvaluator(self.settings)

    def ingest_files(
        self,
        files: List[UploadFile],
        user_id: int,
        pg_db: Session,
        **kwargs: Any,
    ) -> dict:
        """将上传的 MD 文件切片后存入用户的向量数据库，并在 PG 中保存原始文档。

        Args:
            files: 上传的文件列表。
            user_id: 当前用户 ID。
            pg_db: PostgreSQL Session。
            **kwargs: 预留扩展参数。

        Returns:
            入库结果。

        Raises:
            HTTPException: 文件列表为空或全部失败时抛出。
        """
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未选择任何文件",
            )

        documents = []
        errors = []
        saved_files = []

        for file in files:
            filename = file.filename or "unknown.md"

            if not filename.lower().endswith(".md"):
                errors.append(f"{filename}: 仅支持 .md 格式")
                continue

            try:
                content_bytes = file.file.read()
                content = content_bytes.decode("utf-8")

                if not content.strip():
                    errors.append(f"{filename}: 文件内容为空")
                    continue

                documents.append(
                    Document(
                        text=content,
                        metadata={
                            "source": filename,
                            "file_name": filename,
                        },
                    )
                )
                saved_files.append((filename, content))
            except UnicodeDecodeError:
                errors.append(f"{filename}: 文件编码不是 UTF-8")
            except Exception as e:
                errors.append(f"{filename}: 读取失败 - {e}")

        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"没有有效的文件可入库: {'; '.join(errors)}",
            )

        try:
            chunk_count, all_chunk_ids = self.vector_store.add_documents(
                documents, user_id=user_id
            )

            doc_ids = []
            for filename, content in saved_files:
                rag_doc = RAGDocument(
                    user_id=user_id,
                    filename=filename,
                    content=content,
                    chunk_count=0,
                    chunk_ids="[]",
                )
                pg_db.add(rag_doc)
                pg_db.flush()
                doc_ids.append((rag_doc.id, filename))

            files_count = len(saved_files)
            per_file_chunks = chunk_count // files_count if files_count else 0
            remainder = chunk_count % files_count if files_count else 0

            # 按文件均分 chunk_ids（与 chunk_count 对应）
            id_offset = 0
            for i, (doc_id, filename) in enumerate(doc_ids):
                count = per_file_chunks + (1 if i < remainder else 0)
                chunk_ids_slice = all_chunk_ids[id_offset : id_offset + count]
                id_offset += count
                pg_db.query(RAGDocument).filter(RAGDocument.id == doc_id).update(
                    {
                        "chunk_count": count,
                        "chunk_ids": json.dumps(chunk_ids_slice),
                    }
                )
            pg_db.commit()

            result = {
                "status": "ok",
                "files_processed": len(documents),
                "chunks_written": chunk_count,
            }
            if errors:
                result["errors"] = errors
            return result
        except Exception as e:
            pg_db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"文档入库失败: {e}",
            )

    def list_documents(
        self,
        user_id: int,
        pg_db: Session,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """获取用户上传的所有文档列表。

        Args:
            user_id: 用户 ID。
            pg_db: PostgreSQL Session。
            **kwargs: 预留扩展参数。

        Returns:
            文档信息列表。
        """
        docs = (
            pg_db.query(RAGDocument)
            .filter(RAGDocument.user_id == user_id)
            .order_by(RAGDocument.created_at.desc())
            .all()
        )
        return [
            {
                "id": doc.id,
                "filename": doc.filename,
                "chunk_count": doc.chunk_count,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]

    def delete_document(
        self,
        doc_id: int,
        user_id: int,
        pg_db: Session,
        **kwargs: Any,
    ) -> None:
        """删除用户的一个文档及其对应的 ChromaDB 向量。

        如果文档有 chunk_ids 字段，按 ID 精确删除；
        否则通过 file_name 元数据匹配删除（兼容旧数据）。

        Args:
            doc_id: 文档 ID。
            user_id: 用户 ID（隔离验证）。
            pg_db: PostgreSQL Session。
            **kwargs: 预留扩展参数。

        Raises:
            HTTPException: 文档不存在或不属于当前用户时抛出。
        """
        doc = (
            pg_db.query(RAGDocument)
            .filter(RAGDocument.id == doc_id, RAGDocument.user_id == user_id)
            .first()
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在或不属于当前用户",
            )

        # 从 ChromaDB 删除对应的向量
        try:
            chunk_ids = json.loads(doc.chunk_ids) if doc.chunk_ids else []
            if chunk_ids:
                self.vector_store.delete_by_ids(ids=chunk_ids, user_id=user_id)
            else:
                # 兼容旧数据：没有 chunk_ids，通过 file_name 匹配删除
                self.vector_store.delete_by_file_name(
                    file_name=doc.filename, user_id=user_id
                )
        except Exception as e:
            logger.warning("清理 ChromaDB 向量失败（PG 记录仍会删除）: %s", e)

        pg_db.delete(doc)
        pg_db.commit()

    def retrieve(
        self,
        query_text: str,
        user_id: int,
        top_k: Optional[int] = None,
        **kwargs: Any,
    ) -> List[SourceNode]:
        """只检索，不调用 LLM。

        Args:
            query_text: 查询文本。
            user_id: 用户 ID。
            top_k: 返回结果数量。
            **kwargs: 预留扩展参数。

        Returns:
            检索到的来源节点列表。

        Raises:
            HTTPException: 查询文本为空或检索失败时抛出。
        """
        if not query_text or not query_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="查询文本不能为空",
            )

        k = top_k or self.settings.default_top_k

        try:
            nodes = self.vector_store.retrieve(query_text, user_id=user_id, top_k=k)
            return [
                SourceNode(
                    content=node.text,
                    score=float(node.score) if node.score is not None else None,
                    metadata=dict(node.metadata) if node.metadata else {},
                )
                for node in nodes
            ]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"检索失败: {e}",
            )

    def query(
        self,
        query_text: str,
        user_id: int,
        top_k: Optional[int] = None,
        run_eval: bool = False,
        metrics: Optional[List[str]] = None,
        reference: Optional[str] = None,
        **kwargs: Any,
    ) -> QueryResponse:
        """完整 RAG 查询，可选 RAGAS 评估。

        Args:
            query_text: 查询文本。
            user_id: 用户 ID。
            top_k: 返回结果数量。
            run_eval: 是否执行 RAGAS 评估。
            metrics: 要执行的评估指标列表。
            reference: 标准参考答案。
            **kwargs: 预留扩展参数。

        Returns:
            查询响应对象。

        Raises:
            HTTPException: 查询文本为空或查询失败时抛出。
        """
        if not query_text or not query_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="查询文本不能为空",
            )

        k = top_k or self.settings.default_top_k

        try:
            source_nodes = self.retrieve(query_text, user_id=user_id, top_k=k)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"检索失败: {e}",
            )

        contexts = [node.content for node in source_nodes]

        try:
            context_str = "\n\n---\n\n".join(contexts) if contexts else "无相关上下文"
            prompt = (
                f"请基于以下上下文信息回答用户的问题。\n\n"
                f"上下文:\n{context_str}\n\n"
                f"问题: {query_text}\n\n"
                f"回答:"
            )
            response_text = str(Settings.llm.complete(prompt))
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM 生成失败: {e}",
            )

        ragas_result = None
        if run_eval and self.settings.ragas_eval_enabled and contexts:
            try:
                import asyncio

                eval_coro = self.ragas_evaluator.evaluate(
                    query=query_text,
                    response=response_text,
                    contexts=contexts,
                    metrics=metrics or ["faithfulness"],
                    reference=reference,
                )

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        ragas_result = pool.submit(asyncio.run, eval_coro).result()
                elif loop:
                    ragas_result = loop.run_until_complete(eval_coro)
                else:
                    ragas_result = asyncio.run(eval_coro)
            except Exception as e:
                logger.warning("RAGAS 评估失败（不影响查询结果）: %s", e)

        return QueryResponse(
            query=query_text,
            response=response_text,
            source_nodes=source_nodes,
            top_k=k,
            ragas=ragas_result,
        )

    def health_check(self, **kwargs: Any) -> Dict[str, Any]:
        """健康检查。"""
        vs_status = self.vector_store.health_check()
        return {
            "status": "ok",
            "module": "RAG",
            "vector_store": vs_status,
        }

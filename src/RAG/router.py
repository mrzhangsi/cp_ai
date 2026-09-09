"""RAG API 路由模块。

定义 RAG 查询相关接口，前缀为 /rag。
路由层只负责接收请求、注入依赖、调用 Service 方法并返回响应。
所有接口按用户隔离。
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from src.common.database.postgresql.engine import get_pg_db
from src.common.models import HealthResponse, QueryRequest, QueryResponse, SourceNode
from .dependencies import check_token_blacklist, get_current_user
from .service import RAGService

router = APIRouter(prefix="/rag", tags=["RAG"])

# 全局服务实例（由 main.py 注入）
_service: RAGService = None


def init_service(service: RAGService) -> None:
    """初始化服务实例，注入到路由模块。

    Args:
        service: RAGService 业务逻辑实例。
    """
    global _service
    _service = service


@router.post("/ingest")
def ingest_api(
    files: List[UploadFile] = File(..., description="MD 文件（支持多文件）"),
    current_user=Depends(get_current_user),
    pg_db: Session = Depends(get_pg_db),
    _blacklist_check: str = Depends(check_token_blacklist),
) -> dict:
    """文档入库接口。

    上传一个或多个 MD 文件，切片、embedding 后存入用户独立的 ChromaDB 集合。
    原始文件内容保存到 PostgreSQL。
    仅支持 .md 格式，不保存原始文件到磁盘。
    需要 Bearer Token 认证。

    Args:
        files: 上传的文件列表。
        current_user: 当前登录用户。
        pg_db: PostgreSQL Session。
        _blacklist_check: 黑名单检查。

    Returns:
        入库结果，包含处理的文件数和 chunk 数。
    """
    return _service.ingest_files(
        files=files,
        user_id=current_user.id,
        pg_db=pg_db,
    )


@router.get("/documents")
def list_documents_api(
    current_user=Depends(get_current_user),
    pg_db: Session = Depends(get_pg_db),
    _blacklist_check: str = Depends(check_token_blacklist),
) -> List[Dict[str, Any]]:
    """获取当前用户上传的文档列表。

    Args:
        current_user: 当前登录用户。
        pg_db: PostgreSQL Session。
        _blacklist_check: 黑名单检查。

    Returns:
        文档信息列表。
    """
    return _service.list_documents(
        user_id=current_user.id,
        pg_db=pg_db,
    )


@router.delete("/documents/{doc_id}")
def delete_document_api(
    doc_id: int,
    current_user=Depends(get_current_user),
    pg_db: Session = Depends(get_pg_db),
    _blacklist_check: str = Depends(check_token_blacklist),
) -> dict:
    """删除用户的一个文档记录。

    同时删除 PostgreSQL 中的文档记录和 ChromaDB 中的向量。

    Args:
        doc_id: 文档 ID。
        current_user: 当前登录用户。
        pg_db: PostgreSQL Session。
        _blacklist_check: 黑名单检查。

    Returns:
        删除结果。
    """
    _service.delete_document(
        doc_id=doc_id,
        user_id=current_user.id,
        pg_db=pg_db,
    )
    return {"status": "ok"}


@router.post("/retrieve", response_model=List[SourceNode])
def retrieve_api(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
) -> List[SourceNode]:
    """纯检索接口。

    仅在当前用户的向量库中执行语义检索，不调用 LLM，不触发评估。

    Args:
        request: 查询请求体。
        current_user: 当前登录用户。
        _blacklist_check: 黑名单检查。

    Returns:
        检索到的来源节点列表。
    """
    return _service.retrieve(
        query_text=request.query,
        user_id=current_user.id,
        top_k=request.top_k,
    )


@router.post("/query", response_model=QueryResponse)
def query_api(
    request: QueryRequest,
    current_user=Depends(get_current_user),
    _blacklist_check: str = Depends(check_token_blacklist),
) -> QueryResponse:
    """完整 RAG 查询接口。

    在当前用户的向量库中检索 + LLM 生成，可选 RAGAS 评估。

    Args:
        request: 查询请求体。
        current_user: 当前登录用户。
        _blacklist_check: 黑名单检查。

    Returns:
        查询响应，包含回答、来源节点和评估分数（如启用）。
    """
    return _service.query(
        query_text=request.query,
        user_id=current_user.id,
        top_k=request.top_k,
        run_eval=request.run_eval,
        metrics=request.metrics,
        reference=request.reference,
    )


@router.get("/health", response_model=HealthResponse)
def health_check_api() -> HealthResponse:
    """健康检查接口。

    无需认证，用于监控 RAG 模块存活状态。

    Returns:
        服务状态信息。
    """
    return _service.health_check()

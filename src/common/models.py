"""统一 Pydantic 请求/响应模型定义模块。

包含登录、RAG、Agent 模块的请求和响应模型。
ORM 模型已迁移到 database/mysql/models.py 和 database/postgresql/models.py。
"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 登录模块 Pydantic 模型 ====================


class Token(BaseModel):
    """JWT Token 响应模型。

    Attributes:
        token: JWT Token 字符串。
        user_id: 关联的用户 ID。
        token_type: Token 类型，固定为 bearer。
    """

    token: str
    user_id: int
    token_type: str = "bearer"


class UserCreate(BaseModel):
    """用户注册请求模型。

    Attributes:
        username: 用户名，必填。
        password: 密码，必填。
        email: 邮箱，可选。
    """

    username: str
    password: str
    email: Optional[str] = None


# ==================== RAG 模块 Pydantic 模型 ====================


class QueryRequest(BaseModel):
    """RAG 查询请求模型。

    Attributes:
        query: 查询文本内容。
        top_k: 返回最相似结果数量，覆盖默认值。
        run_eval: 是否执行 RAGAS 评估，默认 False。
        metrics: 要执行的评估指标列表，可选值: faithfulness, answer_relevancy, context_precision, context_recall。
        reference: 标准参考答案，context_precision 和 context_recall 需要。
    """

    query: str = Field(..., min_length=1, description="查询文本")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="返回结果数量")
    run_eval: bool = Field(False, description="是否执行 RAGAS 评估")
    metrics: List[str] = Field(default_factory=lambda: ["faithfulness"], description="评估指标列表")
    reference: Optional[str] = Field(None, description="标准参考答案")


class RAGASResult(BaseModel):
    """RAGAS 评估结果模型。

    Attributes:
        faithfulness: 忠实度，回答与检索上下文的一致性 (0-1)。
        answer_relevancy: 答案相关性，回答与查询的相关程度 (0-1)。
        context_precision: 上下文精确度，检索结果的排序质量 (0-1)。
        context_recall: 上下文召回率，检索结果覆盖参考答案的程度 (0-1)。
    """

    faithfulness: Optional[float] = Field(None, ge=0, le=1, description="忠实度 (0-1)")
    answer_relevancy: Optional[float] = Field(None, ge=0, le=1, description="答案相关性 (0-1)")
    context_precision: Optional[float] = Field(None, ge=0, le=1, description="上下文精确度 (0-1)")
    context_recall: Optional[float] = Field(None, ge=0, le=1, description="上下文召回率 (0-1)")


class SourceNode(BaseModel):
    """检索来源节点模型。

    Attributes:
        content: 节点文本内容。
        score: 相似度得分。
        metadata: 节点元数据。
    """

    content: str = Field(..., description="节点文本内容")
    score: Optional[float] = Field(None, description="相似度得分")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class QueryResponse(BaseModel):
    """RAG 查询响应模型。

    Attributes:
        query: 原始查询文本。
        response: 生成的回答文本。
        source_nodes: 检索到的来源节点列表。
        top_k: 实际返回的结果数量。
        ragas: RAGAS 评估结果，仅在完整查询模式下返回。
    """

    query: str = Field(..., description="原始查询文本")
    response: str = Field(..., description="生成的回答文本")
    source_nodes: List[SourceNode] = Field(default_factory=list, description="来源节点列表")
    top_k: int = Field(..., description="返回结果数量")
    ragas: Optional[RAGASResult] = Field(None, description="RAGAS 评估结果")


class HealthResponse(BaseModel):
    """健康检查响应模型。

    Attributes:
        status: 服务状态。
        module: 模块名称。
    """

    status: str = Field(..., description="服务状态")
    module: str = Field(..., description="模块名称")


# ==================== Agent 模块 Pydantic 模型 ====================


class MessageRole(str, Enum):
    """消息角色枚举。"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """Agent 单条消息模型。

    Attributes:
        id: 消息 ID（数据库主键，用于 cursor 追踪）。
        role: 消息角色（user/assistant/system/tool）。
        content: 消息内容。
        timestamp: 消息时间戳。
        metadata: 附加元数据。
    """

    id: Optional[int] = Field(None, description="消息 ID")
    role: str = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(None, description="消息时间戳")
    metadata: Optional[Dict[str, Any]] = Field(None, description="附加元数据")


class ChatRequest(BaseModel):
    """Agent 对话请求模型。

    Attributes:
        session_id: 会话 ID。
        message: 用户消息。
        skill_id: 附带的技能 ID（可选）。
        remember: 是否将对话存入长期记忆（默认 True）。
    """

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., min_length=1, description="用户消息")
    skill_id: Optional[int] = Field(None, description="附带的技能 ID")
    remember: bool = Field(True, description="是否存入长期记忆")


class ChatResponse(BaseModel):
    """Agent 对话响应模型。

    Attributes:
        session_id: 会话 ID。
        response: 助手响应内容。
        messages: 完整消息历史。
    """

    session_id: str = Field(..., description="会话 ID")
    response: str = Field(..., description="助手响应内容")
    messages: List[ChatMessage] = Field(default_factory=list, description="消息历史")


class SessionInfo(BaseModel):
    """Agent 会话信息模型。

    Attributes:
        session_id: 会话 ID。
        title: 会话标题。
        skill_id: 附带的技能 ID。
        created_at: 创建时间。
        updated_at: 更新时间。
        message_count: 消息数量。
    """

    session_id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="会话标题")
    skill_id: Optional[int] = Field(None, description="附带的技能 ID")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    message_count: int = Field(..., description="消息数量")


class CreateSessionRequest(BaseModel):
    """创建会话请求模型。

    Attributes:
        title: 会话标题，可选。
        skill_id: 附带的技能 ID，可选。
    """

    title: Optional[str] = Field(None, description="会话标题")
    skill_id: Optional[int] = Field(None, description="附带的技能 ID")

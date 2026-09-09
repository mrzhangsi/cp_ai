"""统一配置管理模块。

使用 pydantic-settings 的 BaseSettings 管理全局配置，
支持从 .env 文件和环境变量自动加载。模块级单例，只解析一次。
"""
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置类。

    通过 .env 文件或环境变量加载配置项。

    Attributes:
        secret_key: JWT 签名密钥，生产环境务必修改。
        algorithm: JWT 签名算法。
        access_token_expire_minutes: Access Token 有效期（分钟）。
        refresh_token_expire_days: Refresh Token 有效期（天）。
        database_url: SQLAlchemy 数据库连接 URL。
        redis_url: Redis 连接 URL。
        schemes: 密码加密方案列表。
        login_url: 登录接口路径，用于 OAuth2 Swagger 认证。
        rag_llm_model_id: RAG 模型 ID。
        rag_llm_api_key: RAG API 密钥。
        rag_llm_base_url: RAG API 基础 URL。
        rag_llm_is_chat_model: RAG 是否为聊天模型。
        rag_llm_is_function_calling_model: RAG 是否支持函数调用。
        embedding_model_name: Embedding 模型名称。
        embedding_model_api_base: Embedding API 基础 URL。
        embedding_model_api_key: Embedding API 密钥。
        embedding_batch_size: Embedding 批处理大小。
        default_top_k: 默认返回最相似结果数量。
        storage_dir: 索引持久化存储目录。
        agent_llm_model_id: Agent 模型 ID。
        agent_llm_api_key: Agent API 密钥。
        agent_llm_base_url: Agent API 基础 URL。
        agent_llm_supports_vision: Agent 是否支持视觉。
        agent_session_storage: Agent 会话存储目录。
        agent_system_prompt: Agent 系统提示词。
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # JWT 配置
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # MySQL 数据库
    database_url: str = "mysql+pymysql://root:123456@localhost:3306/test"

    # PostgreSQL 数据库（使用 psycopg3 驱动）
    postgres_url: str = "postgresql+psycopg://postgres:123456@localhost:5432/postgres"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # 密码加密
    schemes: List[str] = ["bcrypt"]

    # API
    login_url: str = "/auth/login"

    # RAG 模型配置
    rag_llm_model_id: str = "glm-4.5-air"
    rag_llm_api_key: str = ""
    rag_llm_base_url: str = "https://youzi.today/v1"
    rag_llm_is_chat_model: bool = True
    rag_llm_is_function_calling_model: bool = True

    # Embedding 配置
    embedding_model_name: str = ""
    embedding_model_api_base: str = "https://youzi.today/v1"
    embedding_model_api_key: str = ""
    embedding_batch_size: int = 10

    # 索引与查询配置
    default_top_k: int = 5
    storage_dir: str = "./storage"

    # Agent 模型配置
    agent_llm_model_id: str = "glm-4.5-air"
    agent_llm_api_key: str = ""
    agent_llm_base_url: str = "https://youzi.today/v1"
    agent_llm_supports_vision: bool = False

    # Agent 会话配置
    agent_session_storage: str = "./agent_sessions"
    agent_system_prompt: str = "你是一个有用的AI助手。"
    session_cache_ttl: int = 86400

    # Skill 配置
    skillsmp_api_key: str = ""
    skill_storage_dir: str = "./user_skills"

    # MCP 配置
    modelscope_api_token: str = ""

    # ChromaDB 配置
    chroma_persist_dir: str = "./chroma_storage"
    chroma_collection_name: str = "rag_documents"

    # RAGAS 评估配置
    ragas_llm_model_id: str = ""
    ragas_llm_api_key: str = ""
    ragas_llm_base_url: str = ""
    ragas_llm_is_chat_model: bool = True
    ragas_eval_enabled: bool = True


# 模块级单例，只解析一次 .env
settings = Settings()

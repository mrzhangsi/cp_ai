"""CP_AI 统一服务入口。

合并登录认证系统、RAG 查询系统、Agent 对话系统和 Skill 技能搜索为一个 FastAPI 应用，
挂载前端静态页面并启动 uvicorn 服务器。
"""
import logging
import os
import sys
import types
from datetime import datetime

# ragas 0.4.3 的已知 bug：无条件导入 langchain_community.chat_models.vertexai，
# 而 langchain-community 0.4.2 已移除该模块。注入 mock 模块绕过。
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _ragas_vertexai_mock = types.ModuleType("langchain_community.chat_models.vertexai")
    _ragas_vertexai_mock.ChatVertexAI = type("ChatVertexAI", (object,), {})  # type: ignore[attr-defined]
    sys.modules["langchain_community.chat_models.vertexai"] = _ragas_vertexai_mock

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.common.config import settings

# ========== 日志配置 ==========
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
_log_filename = os.path.join(LOG_DIR, f"cp_ai_{datetime.now():%Y%m%d_%H%M%S}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)
logger.info("日志文件: %s", _log_filename)

# 导入并初始化登录模块
from src.LogIn.router import init_service as init_login_service
from src.LogIn.router import router as login_router
from src.LogIn.service import Service as LoginService

# 导入并初始化 RAG 模块
from src.RAG.router import init_service as init_rag_service
from src.RAG.router import router as rag_router
from src.RAG.service import RAGService

# 导入并初始化 Agent 模块
from src.Agent.router import init_service as init_agent_service
from src.Agent.router import router as agent_router
from src.Agent.service import AgentService

# 导入并初始化 Skill 模块
from src.Skill.router import init_service as init_skill_service
from src.Skill.router import router as skill_router
from src.Skill.service import SkillService

# 导入并初始化 MCP 模块
from src.MCP.router import init_service as init_mcp_service
from src.MCP.router import router as mcp_router
from src.MCP.service import MCPService

# 创建统一的 FastAPI 应用
app = FastAPI(
    title="CP_AI 统一服务",
    description="集成登录认证、RAG 查询、Agent 对话和技能搜索系统",
    version="1.3",
)


def _init_services() -> None:
    """初始化所有服务模块，失败时记录错误但不阻止启动。"""
    services = [
        ("登录", LoginService, init_login_service),
        ("RAG", RAGService, init_rag_service),
        ("Agent", AgentService, init_agent_service),
        ("Skill", SkillService, init_skill_service),
        ("MCP", MCPService, init_mcp_service),
    ]
    for name, service_cls, init_fn in services:
        try:
            svc = service_cls()
            init_fn(svc)
            logger.info("%s 模块初始化成功", name)
        except Exception as e:
            logger.error("%s 模块初始化失败: %s", name, e)


_init_services()

# 注册路由
app.include_router(login_router)
app.include_router(rag_router)
app.include_router(agent_router)
app.include_router(skill_router)
app.include_router(mcp_router)

# 挂载前端静态文件
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
def index():
    """返回前端页面。"""
    return FileResponse("frontend/index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

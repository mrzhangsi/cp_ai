# CP_AI

为内部用户提供开箱即用的 AI 能力的网页端应用。集成 **Agent 对话**、**知识库 RAG**、**技能库**、**MCP Server 搜索**与**登录认证**于一体。

后端 FastAPI + LangChain，前端原生 JS + CSS（无构建步骤），双数据库（MySQL 用户 / PostgreSQL 业务数据）。

---

## 功能概览

| 模块 | 前缀 | 说明 |
| --- | --- | --- |
| 登录认证 | `/auth` | JWT 双 Token（access + refresh）、bcrypt 加密、Redis 黑名单 |
| Agent 对话 | `/agent` | SSE 流式对话、多模态文件解析、mem0 双层记忆、会话管理 |
| 知识库 RAG | `/rag` | ChromaDB 向量库、文档摄取/检索/问答、RAGAS 可选评估 |
| 技能库 | `/skill` | skillsmp 技能搜索、用户自定义技能上传与管理 |
| MCP | `/mcp` | Model Context Protocol Server 搜索 |

每个模块均有 `/health` 健康检查端点。交互式 API 文档：<http://127.0.0.1:8000/docs>

---

## 核心特性

### 多模态输入

`POST /agent/chat/stream` 使用 `multipart/form-data`，可随消息上传文件：

- **文档** → markitdown 解析（PDF / Word / Excel / PPT / HTML / Markdown 等）
- **图片** → 两条路径：LLM 视觉直读（模型支持时）或 easyocr OCR 文字提取
- **音频** → faster-whisper 本地语音转写

上传限制：单文件 20MB、单次总计 50MB，超限返回 413。解析结果与文本一起组装为 LangChain 多模态 content 块。

### mem0 双层记忆

`src/Agent/memory.py` 统一管理两类记忆，均由 mem0 + pgvector 承载：

- **长期记忆**：自动从对话中提取用户事实，按语义检索后注入 system prompt
- **短期记忆**：滑动窗口控制上下文长度，超阈值（默认 20 条消息或 10 万 token）时压缩旧消息为摘要；摘要与近期消息无重叠，用 cursor 游标裁剪已压缩部分

按 `user_id` 隔离，每个用户一个 Memory 实例。可通过 `AGENT_MEMORY_ENABLED=false` 整体关闭，退化为纯滑动窗口模式。

### Trace 观测

独立于日志系统，每次对话生成一条 trace，以 JSONL 追加写入 `logs/trace_YYYYMMDD_HHMMSS.jsonl`，记录各阶段耗时。

---

## 快速开始

### 前置依赖

- Python >= 3.12
- MySQL（用户表）
- PostgreSQL（业务表，需 pgvector 扩展）
- Redis

### 安装

```bash
# 依赖安装（项目使用 uv）
uv sync

# 或用 pip
pip install -e .
```

### 配置

配置项通过 `.env` 加载（pydantic-settings），所有项都有默认值，**最少需要填模型 API Key**：

```bash
# 必填：Agent / RAG 使用的模型
AGENT_LLM_API_KEY=your-key
RAG_LLM_API_KEY=your-key
EMBEDDING_MODEL_API_KEY=your-key

# Embedding 模型名与维度（维度必须与模型实际一致，否则检索全错）
EMBEDDING_MODEL_NAME=bge-m3
EMBEDDING_DIMENSIONS=1024

# PostgreSQL（业务库）
POSTGRES_URL=postgresql+psycopg://postgres:123456@localhost:5432/postgres
PGVECTOR_PASSWORD=123456

# MySQL（用户库）
DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/test

# Redis
REDIS_URL=redis://localhost:6379/0
```

完整配置项见 `src/common/config.py`，每个字段都有中文注释与默认值。

> ⚠️ 生产环境务必修改 `SECRET_KEY`（JWT 签名密钥）与各项默认密码。

### 运行

```bash
python main.py
```

服务启动在 <http://127.0.0.1:8000>，前端页面由同一服务托管。

**启动即自动完成**：PostgreSQL 建表、补列，并执行 `CREATE EXTENSION IF NOT EXISTS vector` 启用 pgvector。无需手动执行 DDL。

各模块初始化失败只记录日志、不阻止启动——便于在依赖服务未就绪时排查。

### 语音模型下载

faster-whisper 模型需单独下载到 `./faster-whisper-tiny`（该目录不入库）：

```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('tiny', download_root='./faster-whisper-tiny')"
```

不上传音频文件时可跳过。

---

## 项目结构

```
├── main.py                  # 统一入口：初始化模块、注册路由、挂载前端
├── src/
│   ├── LogIn/               # 登录认证：JWT 签发/校验、用户 CRUD
│   ├── RAG/                 # 知识库：向量存储、摄取、检索、问答
│   ├── Agent/               # 对话：service 业务层、memory 记忆、
│   │                        #   multimodal 多模态、trace 观测、harness 图编排
│   ├── Skill/               # 技能库：skillsmp 检索、用户技能管理
│   ├── MCP/                 # MCP Server 搜索
│   └── common/              # 配置、模型、认证工具、数据库、Redis 缓存
├── frontend/                # 前端静态资源（无构建，直接由后端托管）
├── tools/index_builder.py   # 离线构建索引
├── data_v.py                # Redis / PostgreSQL 数据查看工具
└── logs/                    # 运行日志与 trace
```

### 分层约定

每个业务模块统一采用 `router → service → 依赖` 三层：

- **router**：HTTP 端点、参数校验、依赖注入
- **service**：业务逻辑，不直接触碰 HTTP
- **dependencies.py**：模块级单例初始化（`init_service` 注入 service 实例）

`main.py` 在启动时依次实例化各模块并注入，模块间通过 `router` 单例调用而非互相 import service，避免循环依赖。

### 数据存储

**MySQL** — 用户

| 表 | 说明 |
| --- | --- |
| `users` | 用户账号（bcrypt 加密密码） |

**PostgreSQL** — 业务数据

| 表 | 说明 |
| --- | --- |
| `agent_sessions` | Agent 会话 |
| `agent_messages` | 消息记录（`id` 字段用于记忆 cursor 追踪） |
| `user_skills` | 用户自定义技能 |
| `rag_documents` | RAG 文档元数据 |

**Redis** — 用户/会话缓存、token 黑名单

**ChromaDB** — 向量库，`./chroma_storage` 持久化，按用户隔离集合（`{prefix}_{user_id}`）

---

## API 速览

所有 `/rag`、`/agent`、`/skill`、`/mcp` 端点均需 JWT 认证，请求头 `Authorization: Bearer <access_token>`。

### 认证

```
POST   /auth/register          注册，返回双 Token
POST   /auth/login             登录（OAuth2 表单）
POST   /auth/refresh           刷新 access token
POST   /auth/logout            登出（token 加入黑名单）
GET    /auth/me                当前用户信息
```

### Agent

```
POST   /agent/chat                    非流式对话
POST   /agent/chat/stream             流式对话（SSE，支持文件上传）
GET    /agent/sessions                会话列表
POST   /agent/sessions                新建会话
GET    /agent/sessions/{id}           会话详情
PATCH  /agent/sessions/{id}/skill     绑定技能
DELETE /agent/sessions/{id}           删除会话
GET    /agent/sessions/{id}/messages  消息历史
```

`/chat/stream` 事件类型：`token`（流式文本）、`tool_start` / `tool_end`（工具调用）、`error`（异常）、`done`（结束）。

表单参数：`message`、`session_id`、`skill_id`（可选）、`remember`（默认 true，控制是否写入长期记忆）、`files`（可选）。

### RAG

```
POST   /rag/ingest             上传摄取文档（仅 .md）
GET    /rag/documents          文档列表
DELETE /rag/documents/{id}     删除文档
POST   /rag/retrieve           纯向量检索
POST   /rag/query              检索增强问答
```

> 摄取接口仅接受 `.md` 文件（切片后 embedding 存入用户独立的 ChromaDB 集合，原始内容存 PostgreSQL）。需要处理 PDF / Word / 图片 / 音频，走上面的 Agent 多模态上传通道。

### Skill / MCP

```
POST   /skill/search           搜索 skillsmp 技能库
POST   /skill/upload           上传自定义技能
GET    /skill/my-skills        我的技能列表
PATCH  /skill/my-skills/{id}   修改技能
DELETE /skill/my-skills/{id}   删除技能

POST   /mcp/search             搜索 MCP Server
GET    /mcp/server             MCP Server 详情
```

---

## 开发备忘

### 已知问题与绕过

`main.py` 开头对 `langchain_community.chat_models.vertexai` 注入了 mock 模块。原因是 ragas 0.4.3 无条件导入该模块，而 langchain-community 0.4.2 已将其移除。升级 ragas 后应删除这段绕过逻辑。

### 换模型时的注意

- `EMBEDDING_DIMENSIONS` 必须与 embedding 模型实际维度一致，否则检索结果无意义
- 模型不支持视觉时，图片会自动降级为 OCR 路径（`AGENT_LLM_SUPPORTS_VISION=false`）
- 记忆功能依赖 pgvector，需确认扩展已启用（启动时会自动尝试创建）

### 数据排查

`data_v.py` 提供 Redis keys 浏览与 PostgreSQL 表数据查看：

```bash
python data_v.py
```

日志在 `logs/cp_ai_*.log`，trace 在 `logs/trace_*.jsonl`。
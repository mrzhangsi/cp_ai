# RAG 模块重构说明

## 概述

RAG 模块从基于文件的存储重构为基于 ChromaDB 向量数据库的架构，支持**用户隔离**（每个用户独立知识库），新增了纯检索模式、RAGAS 自动评估、文档管理和文档删除功能。

## 核心变更

### 1. 用户隔离

每个用户的 RAG 知识库完全独立：

- **ChromaDB**：每个用户一个独立集合 `rag_docs_{user_id}`
- **PostgreSQL**：`rag_documents` 表按 `user_id` 存储原始文档
- **检索/查询**：仅在当前用户的集合中操作

```
用户 A (id=42) → 集合 "rag_docs_42" + PG 表 rag_documents (user_id=42)
用户 B (id=17) → 集合 "rag_docs_17" + PG 表 rag_documents (user_id=17)
```

### 2. 向量数据库：ChromaDB

**之前**：LlamaIndex 的 `StorageContext` 文件持久化（`storage_dir` 目录）

**之后**：ChromaDB 嵌入式向量数据库（`chroma_storage/` 目录），按用户隔离集合

- 零配置，`pip install chromadb` 即用
- 内置持久化（SQLite + parquet）
- 支持 upsert（相同内容自动去重）
- cosine 相似度检索

**依赖**：`chromadb>=1.5.9`、`langchain-chroma>=1.1.0`（已加入 pyproject.toml）

### 3. 文档管理

新增 `rag_documents` 表，存储用户上传的原始 MD 文档：

```python
class RAGDocument(Base):
    __tablename__ = "rag_documents"
    id: int            # 自增主键
    user_id: int       # 所属用户 ID
    filename: str      # 原始文件名
    content: str       # MD 原始内容
    chunk_count: int   # 切片数量
    chunk_ids: str     # JSON 字符串，存储 ChromaDB chunk ID 列表（用于精确删除）
    created_at: datetime
```

### 4. 文档入库

`POST /rag/ingest` 端点：用户上传 MD 文件，切片后存入用户独立的 ChromaDB 集合，原始内容保存到 PostgreSQL。

```python
# 请求（multipart/form-data）
POST /rag/ingest
Content-Type: multipart/form-data
files: [file1.md, file2.md, ...]

# 响应
{
  "status": "ok",
  "files_processed": 2,
  "chunks_written": 64,
  "errors": ["bad_file.txt: 仅支持 .md 格式"]  // 可选
}
```

处理流程：
1. 校验每个文件的 `.md` 后缀
2. 读取文件内容（UTF-8 解码）
3. `SentenceSplitter`（chunk_size=512, overlap=64）切片
4. `OpenAILikeEmbedding` 生成向量
5. ChromaDB `upsert` 到用户集合，生成每个 chunk 的 UUID5 ID
6. 按文件均分 chunk_ids，保存到 PostgreSQL `rag_documents` 表的 `chunk_ids` 字段

### 5. 文档列表

`GET /rag/documents` 端点：返回当前用户上传的所有文档。

```python
# 响应
[
  {"id": 1, "filename": "docs.md", "chunk_count": 32, "created_at": "2025-01-01T00:00:00"},
  {"id": 2, "filename": "guide.md", "chunk_count": 16, "created_at": "2025-01-02T00:00:00"}
]
```

### 6. 文档删除

`DELETE /rag/documents/{doc_id}` 端点：删除用户的一个文档及其对应的 ChromaDB 向量。

```python
# 请求
DELETE /rag/documents/1

# 响应
{"status": "ok"}
```

删除策略：
- 如果文档有 `chunk_ids` 字段 → 按 ID 精确删除 ChromaDB 中的向量
- 如果没有（旧数据兼容）→ 通过 `file_name` 元数据匹配删除
- 删除失败仅记录 warning，不影响 PG 记录删除

前端交互：
- 文档列表每行右侧有删除按钮（垃圾桶图标）
- 点击弹出确认对话框
- 确认后同时删除 PG 记录和 ChromaDB 向量

### 7. 纯检索模式

`POST /rag/retrieve` 端点：仅在当前用户的向量库中执行语义检索，不调用 LLM，不触发评估。

```python
# 请求
POST /rag/retrieve
{ "query": "什么是向量数据库?", "top_k": 5 }

# 响应
[
  { "content": "向量数据库是...", "score": 0.89, "metadata": {...} },
  ...
]
```

### 8. RAGAS 自动评估

`POST /rag/query` 端点：在当前用户的向量库中检索 + LLM 生成 + 自动 RAGAS 评估。

```python
# 请求
POST /rag/query
{
  "query": "什么是向量数据库?",
  "top_k": 5
}

# 响应
{
  "query": "什么是向量数据库?",
  "response": "向量数据库是一种专门用于存储和检索向量化数据的数据库系统...",
  "source_nodes": [...],
  "top_k": 5,
  "ragas": {
    "faithfulness": 0.92,
    "answer_relevancy": 0.88,
    "context_precision": 0.85
  }
}
```

**评估指标**（无需参考答案）：

| 指标 | 说明 | 是否需要 reference |
|------|------|-------------------|
| Faithfulness | 回答与检索上下文的一致性 | 否 |
| Answer Relevancy | 回答与查询的相关程度 | 否 |
| Context Precision | 检索结果的排序质量 | 否 |

### 9. 前端查询结果分窗

查询结果区拆分为三个独立面板：

- **生成回答** — LLM 回答内容
- **检索来源** — 命中文档片段 + 相关度分数，带蓝色左边框
- **RAGAS 评估** — 忠实度 / 答案相关性 / 上下文精确度，带颜色进度条

纯检索模式只显示来源面板；生成+评估模式三个面板全部显示。

## 文件变更

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/RAG/vector_store.py` | ChromaDB 向量存储管理器（按用户隔离） |
| `src/RAG/ragas_eval.py` | RAGAS 评估器 |

### 改造文件

| 文件 | 变更 |
|------|------|
| `src/common/config.py` | 新增 `chroma_persist_dir`、`chroma_collection_name`、`ragas_llm_*`、`ragas_eval_enabled` |
| `src/common/models.py` | 新增 `RAGASResult` 模型；`QueryResponse` 增加 `ragas` |
| `src/common/database/postgresql/models.py` | 新增 `RAGDocument` ORM 模型（含 `chunk_ids` 字段） |
| `src/common/database/postgresql/engine.py` | 注册 `RAGDocument` 到 `create_all` |
| `src/RAG/service.py` | 完全重写：用户隔离 + PG 存储 + `list_documents()` + `delete_document()`（含 ChromaDB 向量清理） |
| `src/RAG/router.py` | 所有端点注入 `get_current_user`；新增 `GET /rag/documents` + `DELETE /rag/documents/{doc_id}` |
| `src/RAG/vector_store.py` | `add_documents()` 返回 `(count, ids)` 元组；新增 `delete_by_ids()` + `delete_by_file_name()` |
| `src/RAG/__init__.py` | 更新导出列表 |
| `src/RAG/dependencies.py` | 新增 `RAGASResult` 导出 |
| `main.py` | 顶部注入 ragas vertexai mock |
| `frontend/index.html` | RAG 视图新增文档列表面板 + 删除按钮 + 查询结果分窗 |
| `frontend/js/rag.js` | 新增 `loadRAGDocuments()` + `deleteRAGDocument()` + 分窗渲染 |
| `frontend/css/rag.css` | 新增文档列表样式 + 分窗面板样式 |
| `frontend/js/init.js` | 进入 RAG 视图时自动加载文档列表 |

### 删除文件

| 文件 | 原因 |
|------|------|
| `src/RAG/storage.py` | 文件存储被 ChromaDB 替代 |
| `src/RAG/embedding_index.py` | 功能合并到 `vector_store.py` |
| `src/RAG/load_data.py` | 功能简化后合并到 `service.py` |

## 架构图

```
用户 (JWT → user_id)
  │
  ├─ POST /rag/ingest (multipart/form-data, 多文件)
  │   → service.ingest_files(user_id, pg_db)
  │   ├─ 校验 .md 后缀 + 读取内容
  │   ├─ SentenceSplitter 切片
  │   ├─ VectorStoreManager.add_documents(docs, user_id)
  │   │   └─ 返回 (chunk_count, [chunk_id_1, chunk_id_2, ...])
  │   ├─ 按文件均分 chunk_ids
  │   └─ RAGDocument → PostgreSQL (user_id, filename, content, chunk_ids)
  │
  ├─ GET /rag/documents
  │   → service.list_documents(user_id, pg_db)
  │   → 查询 PostgreSQL rag_documents WHERE user_id=?
  │   → 返回文档列表
  │
  ├─ DELETE /rag/documents/{doc_id}
  │   → service.delete_document(doc_id, user_id, pg_db)
  │   ├─ 读取 RAGDocument.chunk_ids (JSON)
  │   ├─ VectorStoreManager.delete_by_ids(chunk_ids, user_id)
  │   │   └─ 从 "rag_docs_{user_id}" 删除对应向量
  │   └─ pg_db.delete(doc) → 删除 PG 记录
  │
  ├─ POST /rag/retrieve {query, top_k}
  │   → service.retrieve(query, user_id, top_k)
  │   → VectorStoreManager.retrieve(query, user_id)
  │   → 从 "rag_docs_{user_id}" 检索
  │   → 返回 List[SourceNode]
  │
  └─ POST /rag/query {query, top_k}
      → service.query(query, user_id, top_k)
      ├─ retrieve(user_id) → 从用户集合检索
      ├─ LLM.complete() → 生成回答
      └─ ragas_eval.evaluate() → 自动评估
          → 返回 QueryResponse(ragas=RAGASResult)

组件:
  ├── ModelFactory         创建 LLM + Embedding 模型
  ├── VectorStoreManager   ChromaDB 读写 + 检索 + 删除（按用户隔离）
  └── RAGASEvaluator       RAGAS 质量评估
```

## 配置项

```env
# ChromaDB
chroma_persist_dir = "./chroma_storage"
chroma_collection_name = "rag_documents"  # 集合名前缀，实际为 rag_documents_{user_id}

# RAGAS 评估
ragas_llm_model_id = "stepfun-ai/Step-3.7-Flash"
ragas_llm_api_key = "ms-xxx"
ragas_llm_base_url = "https://api-inference.modelscope.cn/v1"
ragas_llm_is_chat_model = true
ragas_eval_enabled = true
```

## 已知问题

### ragas 0.4.3 导入崩溃

ragas 0.4.3 有已知 bug：`ragas/llms/base.py:12` 无条件导入 `langchain_community.chat_models.vertexai`，而 langchain-community 0.4.2 已移除该模块。

**解决方案**：`main.py` 顶部注入 mock 模块（已实现）。ragas 0.4.4 会修复此问题，届时可移除 mock。

```python
# main.py 顶部
import sys, types
_dummy = types.ModuleType("langchain_community.chat_models.vertexai")
_dummy.ChatVertexAI = type("ChatVertexAI", (object,), {})
sys.modules["langchain_community.chat_models.vertexai"] = _dummy
```

### 旧文档向量清理

旧文档（没有 `chunk_ids` 字段的文档）在删除时通过 `file_name` 元数据匹配删除向量。新入库的文档会存储 `chunk_ids`，支持精确删除。

## API 端点汇总

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/rag/ingest` | 文档入库（多文件上传） | Token + 黑名单 + 用户 |
| GET | `/rag/documents` | 获取用户文档列表 | Token + 黑名单 + 用户 |
| DELETE | `/rag/documents/{doc_id}` | 删除文档（PG + ChromaDB） | Token + 黑名单 + 用户 |
| POST | `/rag/retrieve` | 纯检索（无 LLM） | Token + 黑名单 + 用户 |
| POST | `/rag/query` | 完整查询 + 评估 | Token + 黑名单 + 用户 |
| GET | `/rag/health` | 健康检查 | 无 |

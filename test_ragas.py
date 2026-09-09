"""测试 RAGAS 四个指标 + 新模型。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import types
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _dummy = types.ModuleType("langchain_community.chat_models.vertexai")
    _dummy.ChatVertexAI = type("ChatVertexAI", (object,), {})
    sys.modules["langchain_community.chat_models.vertexai"] = _dummy

from src.common.config import settings

if settings.ragas_llm_api_key:
    os.environ["OPENAI_API_KEY"] = settings.ragas_llm_api_key
if settings.ragas_llm_base_url:
    os.environ["OPENAI_BASE_URL"] = settings.ragas_llm_base_url

import asyncio
import math
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from ragas.evaluation import evaluate
from ragas.dataset_schema import EvaluationDataset


def clean(value):
    if value is None:
        return None
    try:
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def make_evaluator():
    llm = ChatOpenAI(
        model=settings.ragas_llm_model_id,
        api_key=settings.ragas_llm_api_key,
        base_url=settings.ragas_llm_base_url,
        temperature=0,
    )
    wrapped_llm = LangchainLLMWrapper(llm)

    embed = OpenAIEmbeddings(
        model=settings.embedding_model_name,
        api_key=settings.embedding_model_api_key,
        base_url=settings.embedding_model_api_base,
    )
    wrapped_embed = LangchainEmbeddingsWrapper(embed)
    return wrapped_llm, wrapped_embed


def run_eval(metrics, wrapped_llm, wrapped_embed, reference=None):
    sample = {
        "user_input": "什么是向量数据库？",
        "retrieved_contexts": [
            "向量数据库是专门存储高维向量数据的数据库系统，支持相似度搜索。",
            "向量数据库常用于推荐系统、图像检索和自然语言处理等场景。",
        ],
        "response": "向量数据库是一种专门用于存储和检索向量化数据的数据库系统，广泛应用于推荐系统和语义搜索。",
    }
    if reference:
        sample["reference"] = reference

    dataset = EvaluationDataset.from_list([sample])
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=wrapped_llm,
        embeddings=wrapped_embed,
    )
    scores = result.scores[0] if result.scores else {}
    return {k: clean(v) for k, v in scores.items()}


def test_all():
    print(f"模型: {settings.ragas_llm_model_id}")
    print(f"Embedding: {settings.embedding_model_name}")
    print()

    wrapped_llm, wrapped_embed = make_evaluator()

    # 测试1: 只有 Faithfulness
    print("=" * 50)
    print("测试1: Faithfulness")
    print("=" * 50)
    try:
        scores = run_eval([Faithfulness(llm=wrapped_llm)], wrapped_llm, wrapped_embed)
        print(f"  faithfulness = {scores.get('faithfulness')}")
        print("  ✅ 通过" if scores.get('faithfulness') is not None else "  ⚠ 返回 None")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    # 测试2: Faithfulness + AnswerRelevancy
    print()
    print("=" * 50)
    print("测试2: Faithfulness + AnswerRelevancy")
    print("=" * 50)
    try:
        scores = run_eval(
            [Faithfulness(llm=wrapped_llm), AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_embed)],
            wrapped_llm, wrapped_embed,
        )
        print(f"  faithfulness    = {scores.get('faithfulness')}")
        print(f"  answer_relevancy = {scores.get('answer_relevancy')}")
        print("  ✅ 通过")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    # 测试3: ContextPrecision + reference
    print()
    print("=" * 50)
    print("测试3: ContextPrecision (需要 reference)")
    print("=" * 50)
    try:
        scores = run_eval(
            [ContextPrecision(llm=wrapped_llm)],
            wrapped_llm, wrapped_embed,
            reference="向量数据库是专门存储和检索向量数据的数据库系统。",
        )
        print(f"  context_precision = {scores.get('context_precision')}")
        print("  ✅ 通过" if scores.get('context_precision') is not None else "  ⚠ 返回 None")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    # 测试4: ContextRecall + reference
    print()
    print("=" * 50)
    print("测试4: ContextRecall (需要 reference)")
    print("=" * 50)
    try:
        scores = run_eval(
            [ContextRecall(llm=wrapped_llm)],
            wrapped_llm, wrapped_embed,
            reference="向量数据库是专门存储和检索向量数据的数据库系统。",
        )
        print(f"  context_recall = {scores.get('context_recall')}")
        print("  ✅ 通过" if scores.get('context_recall') is not None else "  ⚠ 返回 None")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    # 测试5: 全部四个指标
    print()
    print("=" * 50)
    print("测试5: 全部四个指标")
    print("=" * 50)
    try:
        scores = run_eval(
            [
                Faithfulness(llm=wrapped_llm),
                AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_embed),
                ContextPrecision(llm=wrapped_llm),
                ContextRecall(llm=wrapped_llm),
            ],
            wrapped_llm, wrapped_embed,
            reference="向量数据库是专门存储和检索向量数据的数据库系统。",
        )
        for k, v in scores.items():
            print(f"  {k:25s} = {v}")
        print("  ✅ 通过")
    except Exception as e:
        print(f"  ❌ 失败: {e}")


if __name__ == "__main__":
    test_all()

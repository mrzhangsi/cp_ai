"""RAGAS 评估模块。

提供基于 RAGAS 框架的 RAG 质量评估功能。
使用 LLM-as-Judge 方式评估检索和生成质量。
支持动态选择评估指标和传入标准答案。
"""
import logging
import math
from typing import Any, List, Optional

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.evaluation import evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from ragas.dataset_schema import EvaluationDataset

from src.common.config import settings as app_settings
from src.common.models import RAGASResult

logger = logging.getLogger(__name__)

# 指标名称 → ragas 指标类
_METRIC_REGISTRY = {
    "faithfulness": Faithfulness,
    "answer_relevancy": AnswerRelevancy,
    "context_precision": ContextPrecision,
    "context_recall": ContextRecall,
}

# 需要 reference 的指标
_METRICS_NEED_REF = {"context_precision", "context_recall"}

# 需要 embedding 的指标
_METRICS_NEED_EMBED = {"answer_relevancy"}


def _clean_score(value: Any) -> Optional[float]:
    """清理评分值，将 NaN/inf 转为 None。"""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


class RAGASEvaluator:
    """RAGAS 评估器。

    使用配置的 LLM 作为 Judge，评估 RAG 系统的检索和生成质量。
    支持动态选择评估指标，部分指标需要标准答案（reference）。
    """

    def __init__(self, settings=None, **kwargs: Any) -> None:
        """初始化评估器。

        Args:
            settings: 配置实例，为 None 时使用模块级单例。
            **kwargs: 预留扩展参数。
        """
        self.settings = settings or app_settings

        judge_llm = ChatOpenAI(
            model=self.settings.ragas_llm_model_id,
            api_key=self.settings.ragas_llm_api_key,
            base_url=self.settings.ragas_llm_base_url,
            temperature=0,
        )
        self._wrapped_llm = LangchainLLMWrapper(judge_llm)

        embed_model = OpenAIEmbeddings(
            model=self.settings.embedding_model_name,
            api_key=self.settings.embedding_model_api_key,
            base_url=self.settings.embedding_model_api_base,
        )
        self._wrapped_embed = LangchainEmbeddingsWrapper(embed_model)

    def _build_metrics(self, metric_names: List[str]) -> list:
        """根据名称列表构建 ragas 指标实例。"""
        metrics = []
        for name in metric_names:
            cls = _METRIC_REGISTRY.get(name)
            if cls is None:
                logger.warning("未知的 RAGAS 指标: %s，已跳过", name)
                continue
            kwargs = {"llm": self._wrapped_llm}
            if name in _METRICS_NEED_EMBED:
                kwargs["embeddings"] = self._wrapped_embed
            metrics.append(cls(**kwargs))
        return metrics

    async def evaluate(
        self,
        query: str,
        response: str,
        contexts: List[str],
        metrics: Optional[List[str]] = None,
        reference: Optional[str] = None,
        **kwargs: Any,
    ) -> RAGASResult:
        """执行 RAGAS 评估。

        Args:
            query: 用户查询文本。
            response: LLM 生成的回答。
            contexts: 检索到的上下文列表。
            metrics: 要执行的评估指标名称列表。
            reference: 标准参考答案。
            **kwargs: 预留扩展参数。

        Returns:
            评估结果对象。
        """
        metric_names = metrics or ["faithfulness"]

        # 检查是否需要 reference
        need_ref = set(metric_names) & _METRICS_NEED_REF
        if need_ref and not reference:
            logger.warning(
                "指标 %s 需要 reference 但未提供，将跳过这些指标",
                need_ref,
            )
            metric_names = [m for m in metric_names if m not in _METRICS_NEED_REF]

        ragas_metrics = self._build_metrics(metric_names)
        if not ragas_metrics:
            return RAGASResult()

        try:
            sample = {
                "user_input": query,
                "retrieved_contexts": contexts,
                "response": response,
            }
            if reference:
                sample["reference"] = reference

            dataset = EvaluationDataset.from_list([sample])

            result = evaluate(
                dataset=dataset,
                metrics=ragas_metrics,
                llm=self._wrapped_llm,
                embeddings=self._wrapped_embed,
            )

            scores = result.scores[0] if result.scores else {}

            return RAGASResult(
                faithfulness=_clean_score(scores.get("faithfulness")),
                answer_relevancy=_clean_score(scores.get("answer_relevancy")),
                context_precision=_clean_score(scores.get("context_precision")),
                context_recall=_clean_score(scores.get("context_recall")),
            )
        except Exception as e:
            logger.error("RAGAS 评估失败: %s", e)
            return RAGASResult()

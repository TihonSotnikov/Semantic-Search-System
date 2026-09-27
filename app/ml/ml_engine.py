import heapq
import logging
from typing import Any

import torch
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger('semantic_search_system.ml')


def load_model(model_name: str = "cointegrated/rubert-tiny2") -> SentenceTransformer:
    """
    Загружает и возвращает NLP-модель для генерации эмбеддингов.

    Parameters
    ----------
    model_name : str
        Идентификатор модели на HuggingFace.

    Returns
    -------
    SentenceTransformer
        Инициализированная модель.
    """

    logger.info('Loading model %s', model_name)
    model = SentenceTransformer(model_name, trust_remote_code=True)
    model.max_seq_length = 2048
    logger.info('Model %s loaded with max_seq_length=%d', model_name, model.max_seq_length)
    return model


def compute_embeddings(texts: list[str], model: SentenceTransformer) -> torch.Tensor:
    """
    Вычисляет векторные представления для списка текстов.

    Parameters
    ----------
    texts : list[str]
        Массив строк для векторизации.
    model : SentenceTransformer
        Загруженная модель векторизации.

    Returns
    -------
    torch.Tensor
        Тензор эмбеддингов, оптимизированный для PyTorch.
    """

    logger.debug('Computing embeddings for %d texts', len(texts))
    embeddings = model.encode(texts, convert_to_tensor=True)
    logger.debug('Embeddings computed with shape %s', tuple(embeddings.shape))
    return embeddings


def encode_query(model: SentenceTransformer, query: str) -> torch.Tensor:
    """Кодирование запроса в вектор."""
    logger.debug('Encoding search query length=%d', len(query))
    encoding = model.encode(query, convert_to_tensor=True)
    logger.debug('Query encoding shape=%s', tuple(encoding.shape))
    return encoding


def compute_batch_scores(
    query_embedding: torch.Tensor,
    batch_embeddings: torch.Tensor
) -> torch.Tensor:
    """Вычисление косинусного сходства для батча."""
    scores = util.cos_sim(query_embedding, batch_embeddings)[0]
    logger.debug('Computed batch scores shape=%s', tuple(scores.shape))
    return scores


def select_top_k(
    existing_top_k: list[tuple[float, Any]],
    scores: torch.Tensor,
    contents: list[Any],
    k: int
) -> list[tuple[float, Any]]:
    """
    Обновление списка top-k с использованием min-heap.
    Храним (score, data), чтобы heapq сравнивал по score.
    При k <= 0 список не изменяется.
    """
    if k <= 0:
        return existing_top_k
    for score, data in zip(scores.tolist(), contents, strict=True):
        if len(existing_top_k) < k:
            heapq.heappush(existing_top_k, (score, data))
        else:
            if score > existing_top_k[0][0]:
                heapq.heapreplace(existing_top_k, (score, data))
    return existing_top_k


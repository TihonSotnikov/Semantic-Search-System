import logging

import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import database as db
from app.ml import ml_engine as ml

logger = logging.getLogger('semantic_search_system.services')

BATCH_SIZE = 100


def document_prompt(title: str, text: str) -> str:
    """
    Формирует строку, по которой строится эмбеддинг документа.
    Используется и при импорте, и при ручном добавлении,
    чтобы векторы всех документов были согласованы.
    """
    return f'# {title}\n{text}'


def embeddings_from_docs(documents: list[dict], model: SentenceTransformer) -> list[db.Knowledge]:
    """
    Объединяет заголовки с текстами из списка словарей,
    извлекает из них векторные представления и
    собирает список моделей, готовый к загрузке в базу данных.

    Parameters
    ----------
    documents : list[dict]
        Список словарей в формате
        `[{"title": "...", "text": "..."},]`
    model : SentenceTransformer
        Инициализированная модель векторизации текста

    Returns
    -------
    list[Knowledge]
        Список записей для базы данных
    """
    if not documents:
        return []

    logger.debug('Creating embeddings for %d documents', len(documents))
    prompts = [document_prompt(doc['title'], doc['text']) for doc in documents]
    embeddings = ml.compute_embeddings(prompts, model)

    knowledge_list = [
        db.Knowledge(title=doc['title'], text=doc['text'], vector=emb)
        for doc, emb in zip(documents, embeddings, strict=True)
    ]
    logger.debug('Generated %d knowledge records', len(knowledge_list))
    return knowledge_list


async def search_documents(
    session: AsyncSession,
    query_embedding: torch.Tensor,
    k: int,
    device: torch.device | str = 'cpu',
) -> list[tuple[float, tuple[int, str, str]]]:
    """
    Потоково проходит по базе знаний и выбирает k документов,
    наиболее близких к запросу по косинусному сходству.

    Parameters
    ----------
    session : AsyncSession
        Открытая сессия базы данных.
    query_embedding : torch.Tensor
        Вектор поискового запроса.
    k : int
        Максимальное число результатов.
    device : torch.device | str
        Устройство, на котором считается сходство.

    Returns
    -------
    list[tuple[float, tuple[int, str, str]]]
        Список `(score, (id, title, text))`, отсортированный по убыванию score.
    """
    query_embedding = query_embedding.to(device)
    top_k_heap: list[tuple[float, tuple[int, str, str]]] = []

    result_stream = await session.stream_scalars(select(db.Knowledge))
    async for partition in result_stream.partitions(BATCH_SIZE):
        # Кортежи сравнимы между собой, поэтому при равных score
        # heapq не упадет на сравнении данных
        batch_data = [(row.id, row.title, row.text) for row in partition]
        batch_vectors = [row.vector for row in partition]
        if not batch_vectors:
            continue

        embeddings_tensor = torch.stack(batch_vectors).to(device)
        scores = ml.compute_batch_scores(query_embedding, embeddings_tensor)
        top_k_heap = ml.select_top_k(top_k_heap, scores, batch_data, k)

    return sorted(top_k_heap, key=lambda item: item[0], reverse=True)

import argparse
import asyncio
import json
import logging
import os

import ranx
import torch
from sentence_transformers import SentenceTransformer
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database.database as db
import app.ml.ml_engine as ml
from app import services as sv
from app.logger.logger import configure_logging

logger = logging.getLogger('sss_evaluate')
ROOT = os.path.dirname(__file__)

queries = {
    "q_1": "Как работать из дома",
    "q_2": "Где заказать справку 2-НДФЛ",
    "q_3": "Оформление командировки и возврат денег",
    "q_4": "Как получить ДМС",
    "q_5": "Правила использования принтеров",
    "q_6": "Можно ли прийти на работу с собакой",
    "q_7": "Где оставить велосипед или самокат",
    "q_8": "Процесс увольнения и сдача техники",
    "q_9": "Что делать, если зависает или тормозит компьютер",
    "q_10": "Где взять почитать книги"
}

qrels_dict = {
    "q_1": {
        "1": 2,   # Основной документ про удаленную работу
        "28": 1   # Косвенно связанный документ про гибкий график
    },
    "q_2": {
        "5": 2,   # Заказ справок
        "82": 1   # Использование HR-портала общего назначения
    },
    "q_3": {
        "7": 2,   # Общие правила командировок
        "34": 2,  # Возмещение расходов
        "100": 2  # Порядок оформления расходов
    },
    "q_4": {
        "18": 2   # Полис ДМС
    },
    "q_5": {
        "12": 2,  # Использование принтера и МФУ
        "109": 2, # Ограничения по использованию принтеров
        "158": 2  # Работа с общими принтерами
    },
    "q_6": {
        "32": 2   # Dog-friendly офис
    },
    "q_7": {
        "25": 2,  # Велопарковка на паркинге
        "162": 2  # Правила парковки велосипедов
    },
    "q_8": {
        "46": 2,  # Процесс увольнения (Offboarding)
        "110": 2  # Обходной лист (Exit Checklist)
    },
    "q_9": {
        "20": 2,  # Оформление тикета в Helpdesk
        "42": 1,  # Плановое обновление техники
        "123": 1  # Профилактическая чистка ноутбука
    },
    "q_10": {
        "22": 2,  # Корпоративная библиотека
        "145": 2  # Использование офисной библиотеки
    }
}

qrels = ranx.Qrels(qrels_dict)


async def database_init(
        model: SentenceTransformer,
        session_maker: async_sessionmaker[AsyncSession]
        ):
    """
    Загружает в оценочную базу документы из `data/data.json`.
    Id документов совпадают с их порядковыми номерами в файле (с 1),
    на них ссылается разметка `qrels_dict`.
    """
    with open(os.path.join(ROOT, '../data/data.json'), encoding='utf8') as file:
        initial_data: list[dict] = json.load(file)

    knowledge_list = sv.embeddings_from_docs(initial_data, model)
    for doc_id, knowledge in enumerate(knowledge_list, 1):
        knowledge.id = doc_id

    async with session_maker() as session:
        await session.execute(delete(db.Knowledge))
        session.add_all(knowledge_list)
        await session.commit()


async def search(
        text: str,
        k: int,
        model: SentenceTransformer,
        device,
        session_maker: async_sessionmaker[AsyncSession]
        ) -> dict[str, float]:
    query_embedding = ml.encode_query(model, text)
    async with session_maker() as session:
        top_k = await sv.search_documents(session, query_embedding, k, device)
    return {str(doc_id): score for score, (doc_id, _, _) in top_k}


async def evaluate(model_name):
    engine = None
    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        engine = create_async_engine('sqlite+aiosqlite:///eval_data.db')
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        logger.info("DB engine created")
        model = ml.load_model(model_name).to(device)
        logger.info("Model '%s' loaded successfully on '%s'", model_name, device)

        async with engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        await database_init(model, session_maker)

        search_results: dict[str, dict] = {}
        for i, (key, query) in enumerate(queries.items(), 1):
            logger.info("Processing queries: %d/%d", i, len(queries))
            search_results[key] = await search(query, 10, model, device, session_maker)

        run = ranx.Run(search_results)

        metrics = ["recall@3", "recall@5", "ndcg@3", "ndcg@5", "mrr@5"]
        results = ranx.evaluate(qrels, run, metrics)
        logger.info("Evaluation results:\n%s", json.dumps(results, ensure_ascii=False, indent=2))

    except Exception:
        logger.error("Failed to run evaluation:", exc_info=True)
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == '__main__':
    configure_logging("sss_evaluate", "evaluation.log")
    configure_logging("semantic_search_system", "evaluation.log")

    parser = argparse.ArgumentParser('SSS Evaluation')
    parser.add_argument('--model', '-m', type=str, default='google/embeddinggemma-300m')
    args = parser.parse_args()

    asyncio.run(evaluate(args.model))


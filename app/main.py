import argparse
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

import torch
import uvicorn
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sentence_transformers import SentenceTransformer
from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app import __version__
from app import services as sv
from app.database import database as db
from app.frontend import frontend
from app.logger.logger import configure_logging, get_unified_logging_config
from app.ml import ml_engine as ml

logging_level = os.getenv('LOGGING', 'INFO').upper()
log_file = os.getenv('LOG_FILE', 'app.log') or None
configure_logging(
    "semantic_search_system",
    log_file,
    logging.getLevelNamesMapping().get(logging_level, logging.INFO)
)
custom_log_config = get_unified_logging_config(logging_level, log_file)

logger = logging.getLogger('semantic_search_system')


ROOT = os.path.dirname(__file__)
DEFAULT_DATA_FILE = os.path.join(ROOT, '..', 'data', 'data.json')
DEFAULT_DATABASE_URL = 'sqlite+aiosqlite:///data.db'
MODELS = {
    'gemma': 'google/embeddinggemma-300m',
    'rubert': 'cointegrated/rubert-tiny2',
    'gte': 'Alibaba-NLP/gte-multilingual-base',
}
DEFAULT_MODEL = 'gemma'
MAX_TOP_K = 50


class DocumentSchema(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    text: str = Field(..., min_length=20, max_length=2000)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    text: str


class SearchResult(BaseModel):
    id: int
    score: float
    title: str
    text: str


class ImportResult(BaseModel):
    imported: int
    files_failed: list[str] = []


document_list_adapter = TypeAdapter(list[DocumentSchema])

engine: AsyncEngine
model: SentenceTransformer
session_maker: async_sessionmaker

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def resolve_model_name(name: str) -> str:
    """Возвращает идентификатор модели на HF по короткому имени из `MODELS` (или само имя)."""
    return MODELS.get(name, name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, session_maker, model
    database_url = os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL)
    model_name = resolve_model_name(os.getenv('MODEL_NAME', DEFAULT_MODEL))

    logger.info('Initializing application lifecycle')
    logger.info('Using database = %s', database_url)
    logger.info('Using model = %s', model_name)
    logger.info('Using device = %s', device)
    if not os.getenv('ADMIN_TOKEN'):
        logger.warning('ADMIN_TOKEN is not set: database management endpoints are not protected')

    engine = create_async_engine(database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    model = ml.load_model(model_name).to(device)
    logger.info('Model loaded successfully')

    async with engine.begin() as conn:
        table_exists = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table(db.Knowledge.__tablename__)
        )
        await conn.run_sync(db.Base.metadata.create_all)

    if not table_exists:
        logger.info('Knowledge table was created, filling it with default data')
        await load_default_data()

    yield

    logger.info('Disposing database engine')
    await engine.dispose()


def require_admin_token(x_admin_token: Annotated[str | None, Header()] = None):
    """
    Проверяет заголовок `X-Admin-Token`, если задана переменная окружения `ADMIN_TOKEN`.
    Без `ADMIN_TOKEN` эндпоинты управления базой открыты.
    """
    admin_token = os.getenv('ADMIN_TOKEN')
    if not admin_token:
        return
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, admin_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, 'Invalid or missing admin token')


async def load_default_data() -> int:
    """Очищает базу и загружает в нее документы из `data/data.json`."""
    data_file = os.getenv('DATA_FILE', DEFAULT_DATA_FILE)
    try:
        with open(data_file, encoding='utf8') as file:
            initial_data = document_list_adapter.validate_python(json.load(file))
    except (OSError, ValueError) as e:
        logger.error('Error loading initial data from %s: %s', data_file, e, exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, 'Failed to load initial data') from e

    documents = [doc.model_dump() for doc in initial_data]
    knowledge_list = await run_in_threadpool(sv.embeddings_from_docs, documents, model)
    async with session_maker() as session:
        await session.execute(delete(db.Knowledge))
        session.add_all(knowledge_list)
        await session.commit()

    logger.info('Loaded %d default documents', len(knowledge_list))
    return len(knowledge_list)


app = FastAPI(
    title='Semantic Search System',
    description='Семантический поиск по корпоративной базе знаний',
    version=__version__,
    lifespan=lifespan,
)
app.mount(
    '/static',
    StaticFiles(directory=os.path.join(ROOT, 'frontend/static')),
    name='static',
)
app.include_router(frontend.router)

admin_only = [Depends(require_admin_token)]


@app.get('/health', tags=['Service'])
async def health():
    """Проверка того, что сервис запущен."""
    return {'status': 'ok', 'version': __version__}


@app.get('/documents', response_model=list[DocumentOut], tags=['Documents'])
async def list_documents():
    """
    Возвращает все документы базы знаний (без векторов).

    Returns
    -------
    list[DocumentOut]
        `[ { "id": int, "title": str, "text": str } ]`
    """
    async with session_maker() as session:
        result = await session.execute(select(db.Knowledge).order_by(db.Knowledge.id))
        documents = result.scalars().all()
    logger.info('Returning %d knowledge records', len(documents))
    return documents


@app.post(
    '/documents',
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
    tags=['Documents'],
)
async def create_document(schema: DocumentSchema):
    """
    Ручное добавление одиночного документа в базу.

    Parameters
    ----------
    schema : DocumentSchema
        - `title`: Заголовок
        - `text`: Текст документа

    Returns
    -------
    DocumentOut
        Созданный документ со статусом `201`.
    """
    logger.info('Adding document title=%s', schema.title)
    knowledge = (await run_in_threadpool(sv.embeddings_from_docs, [schema.model_dump()], model))[0]
    async with session_maker() as session:
        session.add(knowledge)
        await session.commit()
    logger.info('Document id=%d added', knowledge.id)
    return knowledge


@app.delete('/documents', status_code=status.HTTP_204_NO_CONTENT, dependencies=admin_only, tags=['Documents'])
async def clear_documents():
    """Полная очистка базы знаний."""
    logger.info('Clearing all knowledge base records')
    async with session_maker() as session:
        await session.execute(delete(db.Knowledge))
        await session.commit()
    logger.info('Knowledge base cleared successfully')
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete(
    '/documents/{document_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin_only,
    tags=['Documents'],
)
async def delete_document(document_id: int):
    """
    Удаление документа по id.

    Returns
    -------
    Response
        - `204`: Документ удален
        - `404`: Документ не найден
    """
    logger.info('Deleting document id=%s', document_id)
    async with session_maker() as session:
        result: CursorResult = await session.execute(  # type: ignore
            delete(db.Knowledge).where(db.Knowledge.id == document_id)
        )
        await session.commit()

    if result.rowcount == 0:
        logger.warning('Document id=%s not found', document_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Document not found')

    logger.info('Document id=%s deleted', document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post('/documents/import', response_model=ImportResult, dependencies=admin_only, tags=['Documents'])
async def import_documents(files: Annotated[list[UploadFile], File()]):
    """
    Загрузка документов из JSON файлов.
    Содержимое каждого файла должно иметь такую структуру::

        [
          {
            "title": "Заголовок документа",
            "text": "Текст документа"
          }
        ]

    Returns
    -------
    ImportResult
        - `200`: Все файлы импортированы
        - `207`: Часть файлов не удалось обработать, их имена в `files_failed`
    """
    files_failed = []
    imported = 0

    logger.info('Importing %d files', len(files))
    async with session_maker() as session:
        for file in files:
            logger.info('Processing uploaded file %s content_type=%s', file.filename, file.content_type)
            try:
                is_json = file.content_type == 'application/json' or (file.filename or '').endswith('.json')
                if not is_json:
                    raise ValueError('Invalid file type')
                documents = document_list_adapter.validate_json(await file.read())
                knowledge_list = await run_in_threadpool(
                    sv.embeddings_from_docs, [doc.model_dump() for doc in documents], model
                )
                session.add_all(knowledge_list)
                imported += len(knowledge_list)
                logger.info('Successfully imported %d documents from %s', len(knowledge_list), file.filename)
            except (ValueError, ValidationError):
                logger.error('Error processing file %s', file.filename, exc_info=True)
                files_failed.append(file.filename)
        await session.commit()

    result = ImportResult(imported=imported, files_failed=files_failed)
    if files_failed:
        return JSONResponse(status_code=status.HTTP_207_MULTI_STATUS, content=result.model_dump())
    return result


@app.post('/documents/reset', response_model=ImportResult, dependencies=admin_only, tags=['Documents'])
async def reset_documents():
    """
    Сброс базы знаний к состоянию по умолчанию.
    Очищает базу и импортирует стандартные документы из `data/data.json`.

    Raises
    ------
    HTTPException
        - 500: Не удалось загрузить документы по умолчанию
    """
    logger.info('Resetting knowledge base from default data file')
    return ImportResult(imported=await load_default_data())


@app.get('/search', response_model=list[SearchResult], tags=['Search'])
async def search(
    q: Annotated[str, Query(min_length=1, max_length=1000, description='Текст поискового запроса')],
    k: Annotated[int, Query(ge=1, le=MAX_TOP_K, description='Максимальное число результатов')] = 3,
):
    """
    Семантический поиск по базе знаний.

    Returns
    -------
    list[SearchResult]
        Документы с наибольшим косинусным сходством, по убыванию score.
    """
    if not q.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, 'Query must not be blank')

    logger.info('Search request text=%s top_k=%d', q[:200], k)
    query_embedding = await run_in_threadpool(ml.encode_query, model, q)

    async with session_maker() as session:
        top_k = await sv.search_documents(session, query_embedding, k, device)

    results = [
        SearchResult(id=doc_id, score=score, title=title, text=text)
        for score, (doc_id, title, text) in top_k
    ]
    logger.info('Search results count=%d', len(results))
    logger.debug('Results response:\n%s', '\n'.join(f'{res.score}: {res.title}' for res in results))
    return results


def main():
    parser = argparse.ArgumentParser("Semantic Search System")
    parser.add_argument(
        '--database',
        type=str,
        default=os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL),
        help="URL базы данных для SQLAlchemy.",
    )
    parser.add_argument(
        '--model',
        type=str,
        default=os.getenv('MODEL_NAME', DEFAULT_MODEL),
        help=f"Модель векторизации: идентификатор с HF или короткое имя ({', '.join(MODELS)}).",
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help="Порт сервера.",
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help="Хост сервера (0.0.0.0 для доступа из сети).",
    )
    args = parser.parse_args()

    os.environ['DATABASE_URL'] = args.database
    os.environ['MODEL_NAME'] = args.model

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_config=custom_log_config
    )


if __name__ == "__main__":
    main()

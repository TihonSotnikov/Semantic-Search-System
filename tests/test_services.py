import asyncio

import pytest
import torch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import services
from app.database import database as db


class StubDocumentModel:
    def encode(self, texts, convert_to_tensor=True):
        assert texts == ["# Title\nBody content"]
        return torch.tensor([[0.1, 0.2]], dtype=torch.float32)


def test_embeddings_from_docs_builds_knowledge_records():
    documents = [{"title": "Title", "text": "Body content"}]
    records = services.embeddings_from_docs(documents, StubDocumentModel())

    assert len(records) == 1
    assert records[0].title == "Title"
    assert records[0].text == "Body content"
    assert isinstance(records[0].vector, torch.Tensor)


def test_embeddings_from_docs_handles_empty_list():
    assert services.embeddings_from_docs([], StubDocumentModel()) == []


def test_document_prompt_joins_title_and_text():
    assert services.document_prompt("Title", "Body") == "# Title\nBody"


async def _search(tmp_path, vectors, query, k):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "search.db"}')
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add_all([
            db.Knowledge(title=f'doc {i}', text=f'text {i}', vector=torch.tensor(vec))
            for i, vec in enumerate(vectors)
        ])
        await session.commit()
        results = await services.search_documents(session, torch.tensor(query), k)
    await engine.dispose()
    return results


def test_search_documents_returns_sorted_top_k(tmp_path):
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]
    results = asyncio.run(_search(tmp_path, vectors, [1.0, 0.0], 2))

    assert [data[1] for _, data in results] == ['doc 0', 'doc 2']
    assert results[0][0] >= results[1][0]


def test_search_documents_handles_equal_scores(tmp_path):
    vectors = [[1.0, 0.0]] * 5
    results = asyncio.run(_search(tmp_path, vectors, [1.0, 0.0], 3))

    assert len(results) == 3


def test_vector_survives_database_roundtrip(tmp_path):
    results = asyncio.run(_search(tmp_path, [[0.25, -1.5, 3.0]], [0.25, -1.5, 3.0], 1))

    assert len(results) == 1
    assert results[0][0] == pytest.approx(1.0)

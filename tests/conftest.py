import json
import os
import re
import zlib

import pytest
import torch

# Логи тестов не должны попадать в app.log
os.environ.setdefault('LOG_FILE', '')

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402

DEFAULT_DOCUMENTS = [
    {"title": "Удаленная работа", "text": "Сотрудники могут работать из дома два дня в неделю по согласованию."},
    {"title": "Корпоративная библиотека", "text": "В офисе есть библиотека, книги можно брать домой на две недели."},
    {"title": "Парковка велосипедов", "text": "Велосипеды и самокаты оставляют на велопарковке у входа в здание."},
]


class StubModel:
    """
    Детерминированная замена SentenceTransformer: мешок слов с хешированием.
    Тексты с общими словами получают близкие векторы.
    """

    dim = 1024

    def to(self, device):
        return self

    def _vector(self, text: str) -> torch.Tensor:
        vector = torch.zeros(self.dim)
        for word in re.findall(r'\w+', text.lower()):
            vector[zlib.crc32(word.encode()) % self.dim] += 1.0
        return vector

    def encode(self, data, convert_to_tensor=True):
        if isinstance(data, str):
            return self._vector(data)
        return torch.stack([self._vector(text) for text in data])


@pytest.fixture
def stub_model():
    return StubModel()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    data_file = tmp_path / 'data.json'
    data_file.write_text(json.dumps(DEFAULT_DOCUMENTS, ensure_ascii=False), encoding='utf8')

    monkeypatch.setenv('DATABASE_URL', f'sqlite+aiosqlite:///{tmp_path / "test.db"}')
    monkeypatch.setenv('DATA_FILE', str(data_file))
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    monkeypatch.setattr(main.ml, 'load_model', lambda name: StubModel())
    return tmp_path


@pytest.fixture
def client(app_env):
    with TestClient(main.app) as test_client:
        yield test_client

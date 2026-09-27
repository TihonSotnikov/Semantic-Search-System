# 🔍 Система семантического поиска по корпоративной базе знаний

[![Tests](https://github.com/TihonSotnikov/Semantic-Search-System/actions/workflows/tests.yml/badge.svg)](https://github.com/TihonSotnikov/Semantic-Search-System/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.13+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 📝 Описание проекта
Веб-сервис для семантического поиска по базе документов. Поиск идет не по совпадению слов, а по смыслу:
документы и запросы переводятся в векторы NLP-моделью, а результаты ранжируются по косинусному сходству.

Возможности:
* Поиск по смыслу через веб-интерфейс или REST API
* Панель управления: просмотр, добавление, удаление и импорт документов из JSON
* Поддержка любой модели `sentence-transformers` с HuggingFace
* Работа на CPU и на NVIDIA GPU (CUDA)
* Docker-образ

## ⚙️ Стек технологий
* **Язык:** Python 3.13+
* **ML / NLP:** `sentence-transformers` (модель по умолчанию: `google/embeddinggemma-300m`)
* **Бэкенд:** Uvicorn + FastAPI
* **База данных:** SQLite (через SQLAlchemy, можно подключить другую)
* **Фронтенд:** Jinja2, HTML+CSS+JavaScript

## 🚀 Установка и запуск

> [!NOTE]
> Для модели `google/embeddinggemma-300m` (выбрана по умолчанию) нужна авторизация в HuggingFace Hub
> и принятие лицензии модели на её [странице](https://huggingface.co/google/embeddinggemma-300m).
> Токен можно передать через переменную окружения `HF_TOKEN` или командой `hf auth login`.
> Если такой возможности нет, выберите другую модель, например `--model rubert`.

> [!IMPORTANT]
> Эмбеддинги разных моделей несовместимы. После смены модели удалите файл базы (`data.db`)
> или сбросьте базу в панели управления.

### [Вариант 1] uv (рекомендуемый)
1. Установка `uv`: [Инструкция](https://docs.astral.sh/uv/getting-started/installation/)
2. Установка зависимостей:
```sh
uv sync
```
По умолчанию PyTorch ставится с PyPI. Чтобы выбрать сборку явно:
```sh
uv sync --extra cpu     # только CPU, самая легкая сборка
uv sync --extra cu126   # NVIDIA GPU, CUDA 12.6 (Linux и Windows)
```
3. Запуск:
```sh
uv run python -m app.main [ПАРАМЕТРЫ]
```
или через uvicorn (параметры задаются переменными окружения, см. ниже):
```sh
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### [Вариант 2] pip
```sh
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.main [ПАРАМЕТРЫ]
```

### [Вариант 3] Docker
Готовый образ:
```sh
docker run -d -p 8000:8000 -e HF_TOKEN=<ТОКЕН_HUGGINGFACE> \
    -v sss-storage:/home/sss/storage jwth32/semantic-ss:1.0.0 [ПАРАМЕТРЫ]
```
В томе `sss-storage` хранятся база, логи и скачанная модель, поэтому они переживают пересоздание контейнера.

Сборка своего образа (по умолчанию CPU, для GPU передайте `TORCH_BACKEND=cu126` и запускайте с `--gpus all`):
```sh
docker build -t semantic-ss .
docker build -t semantic-ss:gpu --build-arg TORCH_BACKEND=cu126 .
```

_При запуске за Nginx лучше не отдавать контейнеру порт 80 напрямую._

## 🛠 Настройка

Параметры командной строки (`python -m app.main` и Docker):

| Параметр     | По умолчанию                  | Описание |
| ------------ | ----------------------------- | -------- |
| `--host`     | `0.0.0.0`                     | Хост (`0.0.0.0` для доступа из сети) |
| `--port`     | `8000`                        | Порт |
| `--database` | `sqlite+aiosqlite:///data.db` | URL базы данных для SQLAlchemy |
| `--model`    | `gemma`                       | Модель: идентификатор с HuggingFace или короткое имя `gemma`, `rubert`, `gte` |

Переменные окружения (работают при любом способе запуска):

| Переменная     | По умолчанию                  | Описание |
| -------------- | ----------------------------- | -------- |
| `DATABASE_URL` | `sqlite+aiosqlite:///data.db` | То же, что `--database` |
| `MODEL_NAME`   | `gemma`                       | То же, что `--model` |
| `ADMIN_TOKEN`  | не задан                      | Токен для изменения базы (см. ниже) |
| `DATA_FILE`    | `data/data.json`              | Документы, которыми заполняется новая база и выполняется сброс |
| `LOGGING`      | `INFO`                        | Уровень логирования |
| `LOG_FILE`     | `app.log`                     | Файл логов (пустое значение отключает запись в файл) |
| `HF_TOKEN`     | не задан                      | Токен HuggingFace |

При первом запуске база создается и заполняется документами из `data/data.json`.
При следующих запусках существующая база не изменяется.

### 🔒 Защита панели управления
Если задан `ADMIN_TOKEN`, все запросы, изменяющие базу, требуют заголовок `X-Admin-Token`.
Панель управления сама запросит токен и запомнит его в браузере. Поиск и просмотр документов остаются открытыми.

Без `ADMIN_TOKEN` изменять базу может любой, у кого есть доступ к серверу. Для публичного запуска токен обязателен.

## 🖥 Использование

* `http://127.0.0.1:8000/` — страница поиска
* `http://127.0.0.1:8000/dashboard` — панель управления базой
* `http://127.0.0.1:8000/docs` — интерактивная документация API (Swagger)

### REST API

| Метод    | Путь                     | Описание |
| -------- | ------------------------ | -------- |
| `GET`    | `/search?q=...&k=3`      | Поиск, `k` от 1 до 50 |
| `GET`    | `/documents`             | Список документов |
| `POST`   | `/documents`             | 🔒 Добавить документ `{"title": "...", "text": "..."}` |
| `DELETE` | `/documents/{id}`        | 🔒 Удалить документ |
| `DELETE` | `/documents`             | 🔒 Удалить все документы |
| `POST`   | `/documents/import`      | 🔒 Импорт документов из JSON-файлов (`multipart/form-data`, поле `files`) |
| `POST`   | `/documents/reset`       | 🔒 Сбросить базу к документам по умолчанию |
| `GET`    | `/health`                | Проверка работоспособности |

🔒 — требует `X-Admin-Token`, если задан `ADMIN_TOKEN`.

Пример:
```sh
curl "http://127.0.0.1:8000/search?q=как%20оформить%20командировку&k=3"
```

Формат файла для импорта (пример: `data/data_50_docs.json`):
```json
[
  { "title": "Заголовок документа", "text": "Текст документа" }
]
```
Заголовок: от 3 до 100 символов, текст: от 20 до 2000 символов.

## 🧪 Тестирование и оценка качества

Тесты не скачивают модель: вместо неё используется заглушка.
```sh
uv run pytest
uv run ruff check .
```

Оценка качества поиска на размеченных запросах к `data/data.json` (171 документ):
```sh
uv run python -m evaluation.eval --model gemma
```

Результаты для `google/embeddinggemma-300m`:

| Метрика  | Значение |
| -------: | -------- |
| recall@3 | 0.917    |
| recall@5 | 0.950    |
| ndcg@3   | 0.932    |
| ndcg@5   | 0.946    |
| mrr@5    | 0.950    |

## 📚 Документация кода
```sh
uv sync --group docs
uv run sphinx-build docs/source docs/build
```

## 📁 Структура проекта
```text
Semantic-Search-System/
│
├── app/
│   ├── database/
│   │   └── database.py     # Модель таблицы и хранение векторов
│   ├── frontend/
│   │   ├── static/         # Скрипты, стили, медиа
│   │   ├── templates/      # HTML шаблоны
│   │   └── frontend.py     # Эндпоинты страниц
│   ├── logger/
│   │   └── logger.py       # Настройка логирования
│   ├── ml/
│   │   └── ml_engine.py    # Векторизация и косинусное сходство
│   ├── services.py         # Построение эмбеддингов документов и поиск top-k
│   └── main.py             # Приложение FastAPI и REST API
│
├── data/                   # Синтетические документы для базы
├── evaluation/             # Оценка качества поиска (ranx)
├── tests/                  # Тесты (pytest)
├── docs/                   # Документация кода (Sphinx)
├── dev/                    # План разработки и распределение обязанностей
├── reports/                # Еженедельные отчеты
├── Dockerfile
├── pyproject.toml          # Зависимости и настройки инструментов
├── requirements.txt        # Зависимости для pip
├── CHANGELOG.md
└── README.md
```

## 👥 Авторы
* Тихон Сотников — ML, база данных, ядро
* Андрей Червов — API, фронтенд

## 📄 Лицензия
[MIT](LICENSE)

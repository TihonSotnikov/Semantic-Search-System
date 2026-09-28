# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии соответствуют [Semantic Versioning](https://semver.org/lang/ru/).

## [1.0.1] - 2026-09-28

### Исправлено
- Документ с заголовком или текстом из одних пробелов проходил проверку длины: пробелы по краям теперь отбрасываются.
- Ошибка разметки в docstring `import_documents` ломала сборку документации Sphinx.
- Предупреждение сборки о версии `uv_build` с uv 0.12.

### Изменено
- README переписан.

## [1.0.0] - 2026-09-27

Первый стабильный релиз.

### Изменено (несовместимо с 0.x)
- API переведен на REST-стиль:

  | Было                          | Стало                          |
  | ----------------------------- | ------------------------------ |
  | `GET /dump`                   | `GET /documents`               |
  | `POST /add_document`          | `POST /documents` (ответ `201`) |
  | `DELETE /delete_document?id=` | `DELETE /documents/{id}`       |
  | `POST /clear`                 | `DELETE /documents`            |
  | `POST /import_data`           | `POST /documents/import`       |
  | `POST /reset`                 | `POST /documents/reset`        |
  | `GET /search?text=`           | `GET /search?q=`               |

- `GET /documents` больше не отдает векторы документов.
- Результаты поиска содержат `id` документа.
- Максимальная длина заголовка документа увеличена с 40 до 100 символов.
- `--model` принимает короткие имена `gemma`, `rubert`, `gte`.
- Минимальная версия Python: 3.13.

### Добавлено
- Настройка через переменные окружения: `DATABASE_URL`, `MODEL_NAME`, `DATA_FILE`, `LOG_FILE`, `ADMIN_TOKEN`.
- Защита эндпоинтов управления базой токеном `ADMIN_TOKEN` (заголовок `X-Admin-Token`).
- Эндпоинт `GET /health`.
- Выбор сборки PyTorch: `uv sync --extra cpu` или `--extra cu126`.
- Docker: образ на CPU по умолчанию (`--build-arg TORCH_BACKEND=cu126` для GPU),
  том `/home/sss/storage` для базы, логов и модели, healthcheck.
- Тесты API и сервисного слоя, CI в GitHub Actions (pytest + ruff).
- Документация Sphinx, CHANGELOG.
- Индикатор загрузки, сообщения «ничего не найдено» и об ошибках на странице поиска.

### Исправлено
- Установка на macOS: PyTorch больше не берется только из CUDA-индекса,
  без которого `uv sync` падал.
- На Apple Silicon не устанавливался `greenlet`, без которого не работает асинхронный доступ к базе.
- База знаний сбрасывалась к данным по умолчанию при каждом запуске сервера.
- Документы, добавленные вручную, векторизовались без заголовка, в отличие от импортированных.
- Панель управления показывала ошибку после успешного добавления документа.
- `/search` с `k <= 0` приводил к ошибке 500.
- Поиск падал, если у нескольких документов совпадал score.
- Удаление несуществующего документа возвращало `204` с телом вместо `404`.
- Импорт не проверял структуру и длину документов.
- Векторизация блокировала обработку остальных запросов.
- Запуск `python app/main.py` при установке через pip падал с `ModuleNotFoundError`: теперь запуск через `python -m app.main`.

### Удалено
- Неиспользуемые `app/logger/config.yaml`, `ml_engine.search_similar_texts`,
  `data/_renum.py`, `data/short_data.json`, `data/data_indexed.json`
  (оценка качества использует `data/data.json`).

## [0.1.0]

Учебная версия, разработанная в рамках курса.

[1.0.1]: https://github.com/TihonSotnikov/Semantic-Search-System/releases/tag/v1.0.1
[1.0.0]: https://github.com/TihonSotnikov/Semantic-Search-System/releases/tag/v1.0.0

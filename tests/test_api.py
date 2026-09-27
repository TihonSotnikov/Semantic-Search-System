import json

from fastapi.testclient import TestClient

from app import __version__, main
from tests.conftest import DEFAULT_DOCUMENTS

VALID_DOCUMENT = {"title": "Полис ДМС", "text": "Полис ДМС оформляется после испытательного срока через HR-портал."}


def test_health(client):
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'version': __version__}


def test_html_pages(client):
    assert client.get('/').status_code == 200
    assert client.get('/dashboard').status_code == 200


def test_startup_fills_empty_database(client):
    documents = client.get('/documents').json()

    assert [doc['title'] for doc in documents] == [doc['title'] for doc in DEFAULT_DOCUMENTS]
    assert set(documents[0]) == {'id', 'title', 'text'}


def test_restart_keeps_existing_documents(app_env):
    with TestClient(main.app) as client:
        client.post('/documents', json=VALID_DOCUMENT)
        client.delete('/documents/1')

    with TestClient(main.app) as client:
        titles = [doc['title'] for doc in client.get('/documents').json()]

    assert len(titles) == len(DEFAULT_DOCUMENTS)
    assert VALID_DOCUMENT['title'] in titles
    assert DEFAULT_DOCUMENTS[0]['title'] not in titles


def test_create_document(client):
    response = client.post('/documents', json=VALID_DOCUMENT)

    assert response.status_code == 201
    created = response.json()
    assert created['title'] == VALID_DOCUMENT['title']
    assert created['id'] in [doc['id'] for doc in client.get('/documents').json()]


def test_create_document_validation(client):
    response = client.post('/documents', json={"title": "ab", "text": "short"})

    assert response.status_code == 422


def test_created_document_is_searchable(client):
    client.post('/documents', json=VALID_DOCUMENT)
    results = client.get('/search', params={'q': 'полис ДМС', 'k': 1}).json()

    assert results[0]['title'] == VALID_DOCUMENT['title']


def test_delete_document(client):
    doc_id = client.get('/documents').json()[0]['id']

    assert client.delete(f'/documents/{doc_id}').status_code == 204
    assert client.delete(f'/documents/{doc_id}').status_code == 404
    assert doc_id not in [doc['id'] for doc in client.get('/documents').json()]


def test_clear_documents(client):
    assert client.delete('/documents').status_code == 204
    assert client.get('/documents').json() == []


def test_reset_documents(client):
    client.delete('/documents')
    response = client.post('/documents/reset')

    assert response.status_code == 200
    assert response.json()['imported'] == len(DEFAULT_DOCUMENTS)
    assert len(client.get('/documents').json()) == len(DEFAULT_DOCUMENTS)


def test_search_returns_relevant_documents(client):
    response = client.get('/search', params={'q': 'где оставить велосипеды', 'k': 2})

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert results[0]['title'] == 'Парковка велосипедов'
    assert results[0]['score'] >= results[1]['score']
    assert set(results[0]) == {'id', 'score', 'title', 'text'}


def test_search_k_larger_than_database(client):
    results = client.get('/search', params={'q': 'книги', 'k': 50}).json()

    assert len(results) == len(DEFAULT_DOCUMENTS)


def test_search_on_empty_database(client):
    client.delete('/documents')

    assert client.get('/search', params={'q': 'книги'}).json() == []


def test_search_validation(client):
    assert client.get('/search').status_code == 422
    assert client.get('/search', params={'q': ''}).status_code == 422
    assert client.get('/search', params={'q': '   '}).status_code == 422
    assert client.get('/search', params={'q': 'книги', 'k': 0}).status_code == 422
    assert client.get('/search', params={'q': 'книги', 'k': -1}).status_code == 422
    assert client.get('/search', params={'q': 'книги', 'k': 1000}).status_code == 422


def _json_file(name, content):
    return ('files', (name, json.dumps(content, ensure_ascii=False).encode(), 'application/json'))


def test_import_documents(client):
    client.delete('/documents')
    response = client.post('/documents/import', files=[
        _json_file('a.json', [VALID_DOCUMENT]),
        _json_file('b.json', DEFAULT_DOCUMENTS),
    ])

    assert response.status_code == 200
    assert response.json() == {'imported': 1 + len(DEFAULT_DOCUMENTS), 'files_failed': []}
    assert len(client.get('/documents').json()) == 1 + len(DEFAULT_DOCUMENTS)


def test_import_partially_failed(client):
    client.delete('/documents')
    response = client.post('/documents/import', files=[
        _json_file('good.json', [VALID_DOCUMENT]),
        _json_file('bad_schema.json', [{"title": "no text"}]),
        ('files', ('broken.json', b'{not json', 'application/json')),
        ('files', ('notes.txt', b'plain text', 'text/plain')),
    ])

    assert response.status_code == 207
    assert response.json() == {'imported': 1, 'files_failed': ['bad_schema.json', 'broken.json', 'notes.txt']}
    assert len(client.get('/documents').json()) == 1


def test_admin_token_protects_management_endpoints(client, monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'secret')

    assert client.post('/documents', json=VALID_DOCUMENT).status_code == 401
    assert client.delete('/documents', headers={'X-Admin-Token': 'wrong'}).status_code == 401
    assert client.post('/documents/reset').status_code == 401
    assert client.post('/documents', json=VALID_DOCUMENT, headers={'X-Admin-Token': 'secret'}).status_code == 201

    # Чтение и поиск остаются открытыми
    assert client.get('/documents').status_code == 200
    assert client.get('/search', params={'q': 'книги'}).status_code == 200


def test_resolve_model_name():
    assert main.resolve_model_name('gemma') == 'google/embeddinggemma-300m'
    assert main.resolve_model_name('org/custom-model') == 'org/custom-model'

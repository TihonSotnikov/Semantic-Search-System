// Global functions

const TOKEN_KEY = 'adminToken';

function getAdminToken() {
    try {
        return localStorage.getItem(TOKEN_KEY);
    } catch {
        return null;
    }
}

function setAdminToken(token) {
    try {
        if (token) localStorage.setItem(TOKEN_KEY, token);
        else localStorage.removeItem(TOKEN_KEY);
    } catch {
        // localStorage может быть недоступен (например, в приватном режиме)
    }
}

// fetch с заголовком X-Admin-Token. При 401 запрашивает токен и повторяет запрос.
async function adminFetch(url, options = {}) {
    let token = getAdminToken();
    for (;;) {
        const headers = new Headers(options.headers || {});
        if (token) headers.set('X-Admin-Token', token);
        const response = await fetch(url, { ...options, headers });
        if (response.status !== 401) return response;

        token = prompt('Введите токен администратора (ADMIN_TOKEN):');
        setAdminToken(token);
        if (!token) return response;
    }
}

async function reloadDocuments() {
    const documentsList = document.getElementById('documents-list');
    documentsList.innerHTML = 'Загрузка...';
    const response = await fetch('/documents');
    if (!response.ok) {
        documentsList.innerHTML = 'Не удалось загрузить документы';
        throw new Error('Could not load documents');
    }
    const data = await response.json();

    documentsList.innerHTML = '';
    if (data.length === 0) {
        documentsList.textContent = 'База пуста';
        return;
    }
    data.forEach(doc => {
        const div = document.createElement('div');
        div.classList.add('document-display');

        const titleBox = document.createElement('div');
        titleBox.classList.add('inline-flex');
        const title = document.createElement('h3');
        title.textContent = doc.title;
        const deleteButton = document.createElement('button');
        deleteButton.classList.add('status', 'delete');
        titleBox.appendChild(title);
        titleBox.appendChild(deleteButton);
        deleteButton.addEventListener('click', async function() {
            if (!confirm('Вы уверены, что хотите удалить этот документ?')) return;
            const response = await adminFetch(`/documents/${doc.id}`, {
                method: 'DELETE'
            });
            if (response.ok || response.status === 404) {
                div.remove();
            }
        });
        const text = document.createElement('p');
        text.textContent = doc.text;

        div.dataset.docId = doc.id;
        div.appendChild(titleBox);
        div.appendChild(text);
        documentsList.appendChild(div);
    });
}

async function clearStatuses() {
    const statusDivs = document.querySelectorAll('.status');
    statusDivs.forEach(div => {
        div.classList.remove('success', 'error', 'loader', 'alert');
    });
}

function setStatus(statusDiv, state) {
    statusDiv.classList.remove('success', 'error', 'loader', 'alert');
    if (state) statusDiv.classList.add(state);
}

// On page load
document.addEventListener('DOMContentLoaded', async function() {
    await reloadDocuments();
});

// Reset database
document.getElementById('reset-db-button').addEventListener('click', async function() {
    clearStatuses();
    const statusDiv = document.getElementById('reset-db-status');
    setStatus(statusDiv, 'loader');

    const response = await adminFetch('/documents/reset', {
        method: 'POST'
    });

    setStatus(statusDiv, response.ok ? 'success' : 'error');
    await reloadDocuments();
})

// Clear database
document.getElementById('clear-db-button').addEventListener('click', async function() {
    if (!confirm('Удалить все документы из базы?')) return;
    clearStatuses();
    const statusDiv = document.getElementById('clear-db-status');
    setStatus(statusDiv, 'loader');

    const response = await adminFetch('/documents', {
        method: 'DELETE'
    });

    setStatus(statusDiv, response.ok ? 'success' : 'error');
    await reloadDocuments();
});

// Refresh documents
document.getElementById('refresh-button').addEventListener('click', async function() {
    clearStatuses();
    const statusDiv = document.getElementById('refresh-status');
    setStatus(statusDiv, 'loader');

    try {
        await reloadDocuments();
        setStatus(statusDiv, 'success');
    } catch (error) {
        console.error('Error:', error);
        setStatus(statusDiv, 'error');
    }
});

// Import documents from files
const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const uploadButton = document.getElementById('upload-button')
uploadForm.addEventListener('submit', async function(event) {
    event.preventDefault();
    clearStatuses();
    uploadButton.classList.remove('tooltip')

    const statusDiv = document.getElementById('upload-status');
    const files = fileInput.files;
    if (files.length === 0) {
        setStatus(statusDiv, 'error');
        alert('Пожалуйста, выберите файл для загрузки');
        return;
    }
    setStatus(statusDiv, 'loader');

    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    try {
        const response = await adminFetch('/documents/import', {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            throw new Error('Could not upload file');
        }
        if (response.status === 207) {
            const result = await response.json();
            uploadButton.dataset.tooltip = `Не удалось обработать следующие файлы:\n\n${result.files_failed.join('\n')}`;
            uploadButton.classList.add('tooltip');
            setStatus(statusDiv, 'alert');
        } else {
            setStatus(statusDiv, 'success');
            uploadForm.reset();
        }
    } catch (error) {
        console.error('Error:', error);
        setStatus(statusDiv, 'error');
    }
    await reloadDocuments();
});

// Add document manually
const addDocumentForm = document.getElementById('add-document-form');
addDocumentForm.addEventListener('submit', async function(event) {
    event.preventDefault();
    clearStatuses();
    const statusDiv = document.getElementById('add-document-status');
    setStatus(statusDiv, 'loader');

    const formData = new FormData(addDocumentForm);
    const data = Object.fromEntries(formData.entries());

    if (data.title.trim() === '' || data.text.trim() === '' ) {
        setStatus(statusDiv, 'error');
        alert('Пожалуйста, заполните все поля');
        return;
    }

    try {
        const response = await adminFetch('/documents', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        if (response.status === 422) {
            setStatus(statusDiv, 'error');
            alert('Заголовок должен быть от 3 до 100 символов, текст — от 20 до 2000 символов');
            return;
        }
        if (!response.ok) {
            throw new Error('Could not add document');
        }
        setStatus(statusDiv, 'success');
        addDocumentForm.reset();
    } catch (error) {
        console.error('Error:', error);
        setStatus(statusDiv, 'error');
    }

    await reloadDocuments();
});

const resultsDiv = document.getElementById('results');

function showMessage(text, isError = false) {
    resultsDiv.innerHTML = '';
    const message = document.createElement('p');
    message.classList.add('results-message');
    if (isError) message.classList.add('error');
    message.textContent = text;
    resultsDiv.appendChild(message);
}

document.getElementById('search-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const query = document.getElementById('search-input').value;
    if (query.trim() === '') return;

    showMessage('Поиск...');
    try {
        const response = await fetch('/search?q=' + encodeURIComponent(query));
        if (!response.ok) {
            throw new Error(`Search failed with status ${response.status}`);
        }
        const data = await response.json();

        if (data.length === 0) {
            showMessage('Ничего не найдено');
            return;
        }

        resultsDiv.innerHTML = '';
        data.forEach(item => {
            const div = document.createElement('div');
            div.classList.add('result-item');
            const title = document.createElement('h3');
            title.textContent = item.title;
            const text = document.createElement('p');
            text.textContent = item.text;
            const score = document.createElement('p');
            score.classList.add('result-score');
            score.textContent = `Score: ${item.score.toFixed(3)}`;
            div.appendChild(title);
            div.appendChild(text);
            div.appendChild(score);
            resultsDiv.appendChild(div);
        });
    } catch (error) {
        console.error('Error:', error);
        showMessage('Не удалось выполнить поиск. Попробуйте позже.', true);
    }
});

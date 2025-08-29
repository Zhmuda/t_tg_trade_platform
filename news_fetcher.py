from datetime import datetime, timedelta
import requests
import json
from sentiment_analysis import analyze_sentiment

NEWS_API_KEY = '494f43ed93914c078016cf0e64db2c49'

def get_news(company, days):
    """Получает новости по компании за указанный период."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    url = (f'https://newsapi.org/v2/everything?q={company}&from={start_date.strftime("%Y-%m-%d")}&'
           f'to={end_date.strftime("%Y-%m-%d")}&sortBy=relevancy&apiKey={NEWS_API_KEY}')
    response = requests.get(url)
    return response.text

def process_news_response(response):
    """Обрабатывает ответ от API и анализирует новости."""
    try:
        response = json.loads(response)
    except json.JSONDecodeError:
        return "Ошибка декодирования JSON."

    if response.get("status") != "ok":
        return "Ошибка в ответе API новостей."

    articles = response.get("articles", [])
    if not articles:
        return "Нет доступных новостей."

    total_score = 0
    count = 0

    for article in articles:
        title = article.get("title", "Заголовок отсутствует")
        description = article.get("description", "Описание отсутствует")

        # Исправляем кодировку
        try:
            title = title.encode().decode('utf-8', errors='ignore')
            description = description.encode().decode('utf-8', errors='ignore')
        except Exception:
            continue

        # Пропускаем, если текст пустой или не на русском/английском
        if not any(c.isalpha() for c in title + description):
            continue

        sentiment_title, score_title = analyze_sentiment(title)
        sentiment_description, score_description = analyze_sentiment(description)

        print(f"Title: {title} -> {sentiment_title} ({score_title:.2f})")
        print(f"Description: {description} -> {sentiment_description} ({score_description:.2f})")

        total_score += score_title + score_description
        count += 2

    avg_score = total_score / count if count else 0

    if avg_score > 0.05:
        return f"📈 POSITIVE ({avg_score:.2f})"
    elif avg_score < -0.05:
        return f"📉 NEGATIVE ({avg_score:.2f})"
    else:
        return f"⚖ NEUTRAL ({avg_score:.2f})"

def get_news_and_analyze(company, days):
    """Комбинирует получение и анализ новостей."""
    response = get_news(company, days)
    return process_news_response(response)

if __name__ == "__main__":
    result = get_news_and_analyze("SBER", 7)
    print(f"Итог: {result}")
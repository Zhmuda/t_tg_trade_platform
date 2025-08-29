from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time


def fetch_rbc_news(company, days):
    """Парсит новости с rbc.ru по запросу компании с использованием Selenium."""
    url = f"https://www.rbc.ru/search/?query={company}"

    # Настройка Selenium для работы в фоновом режиме
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Без графического интерфейса
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    # Укажите путь к chromedriver
    service = Service()  # Замените на ваш путь
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        print(f"Загрузка страницы {url}...")
        driver.get(url)
        time.sleep(3)  # Ждём загрузки динамического контента

        # Парсим HTML после выполнения JavaScript
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Ищем контейнер с новостями
        news_container = soup.find("div", class_="l-row g-overflow js-search-container")
        if not news_container:
            return {"error": "Контейнер с новостями ('l-row g-overflow js-search-container') не найден."}

        news_items = news_container.select(".search-item")
        if not news_items:
            return {"error": "Новостей не найдено в контейнере."}

        # Фильтруем новости по заданному периоду
        start_date = datetime.now() - timedelta(days=days)
        news_list = []

        for item in news_items:
            title_tag = item.select_one(".search-item__title")
            title = title_tag.get_text(strip=True) if title_tag else "Заголовок отсутствует"

            desc_tag = item.select_one(".search-item__text")
            description = desc_tag.get_text(strip=True) if desc_tag else "Описание отсутствует"

            date_tag = item.select_one(".search-item__date")
            date_str = date_tag.get_text(strip=True) if date_tag else datetime.now().strftime("%d.%m.%Y")
            try:
                news_date = datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                news_date = datetime.now()

            if start_date <= news_date:
                news_list.append({
                    "title": title,
                    "description": description,
                    "date": news_date.strftime("%Y-%m-%d"),
                    "source": "rbc.ru"
                })

        if not news_list:
            return {"error": f"Нет новостей за последние {days} дней."}

        return news_list

    except Exception as e:
        return {"error": f"Ошибка при парсинге rbc.ru: {str(e)}"}

    finally:
        driver.quit()


def fetch_site_financial_news(company, days):
    """Собирает новости только с rbc.ru."""
    print(f"Парсинг новостей для {company} за {days} дней с rbc.ru...")
    return fetch_rbc_news(company, days)


# Тестовый запуск
if __name__ == "__main__":
    company = "Сбер"
    days = 7
    news = fetch_site_financial_news(company, days)
    if isinstance(news, list):
        for article in news:
            print(f"Source: {article['source']}")
            print(f"Title: {article['title']}")
            print(f"Description: {article['description']}")
            print(f"Date: {article['date']}")
            print("-" * 50)
    else:
        print(news["error"])
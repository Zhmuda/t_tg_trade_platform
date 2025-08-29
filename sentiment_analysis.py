from transformers import pipeline

# Инициализация двух моделей
finbert_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
rubert_pipeline = pipeline("sentiment-analysis", model="blanchefort/rubert-base-cased-sentiment")


def analyze_sentiment(text):
    """Анализ тональности текста с помощью двух моделей и усреднение результатов."""

    # Оценка с помощью FinBERT
    finbert_result = finbert_pipeline(text)
    finbert_label = finbert_result[0]["label"].upper()
    finbert_score = finbert_result[0]["score"]
    if finbert_label == "POSITIVE":
        finbert_value = finbert_score
    elif finbert_label == "NEGATIVE":
        finbert_value = -finbert_score
    else:
        finbert_value = 0

    # Оценка с помощью RuBERT
    rubert_result = rubert_pipeline(text)
    rubert_label = rubert_result[0]["label"].upper()
    rubert_score = rubert_result[0]["score"]
    if rubert_label == "POSITIVE":
        rubert_value = rubert_score
    elif rubert_label == "NEGATIVE":
        rubert_value = -rubert_score
    else:
        rubert_value = 0

    # Усреднение оценок
    avg_value = (finbert_value + rubert_value) / 2

    # Вывод промежуточных результатов для отладки
    print(
        f"FinBERT: {finbert_label} ({finbert_value:.2f}) | RuBERT: {rubert_label} ({rubert_value:.2f}) | Avg: {avg_value:.2f}")

    return (
        "POSITIVE" if avg_value > 0.05 else "NEGATIVE" if avg_value < -0.05 else "NEUTRAL",
        avg_value
    )
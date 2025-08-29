import os
from google import genai

# Установите переменную окружения
os.environ['GEMINI_API_KEY'] = 'AIzaSyCUMKJxhgeFmR3B4T59eHComBpl0v3gEgM'

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash", contents="Explain how AI works in a few words"
)
print(response.text)
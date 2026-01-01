import requests
import os
from dotenv import load_dotenv

load_dotenv()
chave = os.getenv("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={chave}"
payload = {"contents": [{"parts": [{"text": "Oi, você está funcionando?"}]}]}

r = requests.post(url, json=payload)

print(f"Status: {r.status_code}")
if r.status_code == 200:
    print("✅ SUCESSO! O problema era a chave anterior.")
    print("Resposta da IA:", r.json()['candidates'][0]['content']['parts'][0]['text'])
else:
    print("❌ ERRO AINDA PERSISTE:", r.text)

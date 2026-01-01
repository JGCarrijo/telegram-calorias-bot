import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Carregar variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_KEY:
    print("❌ Erro: Configure TELEGRAM_BOT_TOKEN e GROQ_API_KEY no arquivo .env")
    exit()

# Inicializar cliente Groq
client = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Banco de Dados Simples
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 3. Inteligência Artificial (Modelo Llama 3.3)
def ask_groq(text):
    # Usando o modelo atualizado de 2026
    prompt = f"""Você é um nutricionista experiente. 
    Analise o alimento: '{text}'. 
    Retorne APENAS um objeto JSON puro no formato: 
    {{"food": "nome do alimento", "calories": 000}}"""
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", # Modelo corrigido
            response_format={"type": "json_object"}
        )
        return json.loads(chat_completion.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Erro na IA: {e}")
        return None

# 4. Funções do Telegram
async def start(update: Update

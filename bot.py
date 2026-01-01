import json
import os
import requests
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Configurações e Chaves
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not all([TOKEN, GROQ_KEY, GEMINI_KEY]):
    print("❌ Erro: Verifique se TOKEN, GROQ_API_KEY e GEMINI_API_KEY estão no .env")
    exit()

client_groq = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Banco de Dados Simples
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 3. Inteligência Artificial (Texto via Groq)
def ask_groq_text(text):
    prompt = f"Nutricionista. Analise: '{text}'. Retorne APENAS um JSON puro: {{\"food\": \"nome\", \"calories\": 0}}"
    try:
        res = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"Erro Groq: {e}")
        return None

# 4. Inteligência Artificial (Visão via Gemini v1)
def ask_gemini_vision(image_path):
    # Usando a URL de produção v1 para evitar o erro 404 da beta
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = "Você é um nutricionista. Olhe esta imagem de comida e retorne APENAS um JSON: {\"food\": \"nome do prato\", \"calories\": 0}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": encode_image(image_path)}}
            ]
        }]
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"Erro Gemini: {r.status_code} - {r.text}")
            return None
            
        res_data = r.json()
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Limpeza de Markdown
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Erro Visão: {e}")
        return None

# 5. Lógica do Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 *NutriBot Híbrido Ativo!*\nEnvie uma mensagem de texto ou uma FOTO do que comeu.")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    status_msg = await update.message.reply_text("⏳ Analisando refeição...")

    if update.message.photo:
        # Baixa a foto
        file = await update.message.photo[-1].get_file()
        path = f"img_{user_id}.jpg"
        await file.download_to_drive(path)
        result = ask_gemini_vision(path)
        if os.path.exists(path): os.remove(path)
    else:
        # Processa o texto
        result = ask_groq_text(update.message.text)

    if result and result.get("food"):
        data = load_data()
        if user_id not in data: data[user_id] = {}
        if today not in data[user_id]: data[user_id][today] = {"calories": 0}
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)
        
        total = data[user_id][today]["calories"]
        await status_msg.edit_text(
            f"🥗 *Identificado:* {result['food']}\n🔥 +{cal} kcal\n📊 *Total hoje:* {total} / {META_CALORIAS} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui identificar. Tente descrever por texto.")

# 6. Execução
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    
    print("🚀 Bot iniciado! Texto: Groq | Fotos: Gemini")
    app.run_polling()

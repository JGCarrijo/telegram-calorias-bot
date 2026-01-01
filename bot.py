import json
import os
import requests
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Configurações
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_API_TOKEN") # Token da Hugging Face

client_groq = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Dados
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

# 3. IA Texto (Groq)
def ask_groq_text(text):
    prompt = f"Nutricionista. Analise: '{text}'. Retorne APENAS JSON: {{\"food\": \"nome\", \"calories\": 0}}"
    try:
        res = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except: return None

# 4. IA Visão (Hugging Face - Llava Model)
def ask_hf_vision(image_path):
    # Usando o modelo Llava 1.5 (Gratuito e excelente para fotos)
    API_URL = "https://api-inference.huggingface.co/models/llava-hf/llava-1.5-7b-hf"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    with open(image_path, "rb") as f:
        img_data = f.read()

    try:
        # Primeiro, pedimos para a IA descrever a foto
        response = requests.post(API_URL, headers=headers, data=img_data, timeout=30)
        description = response.json()[0]['generated_text'].split("ASSISTANT:")[-1]
        
        # Agora usamos a Groq para transformar essa descrição em calorias (JSON)
        return ask_groq_text(f"Com base nesta descrição: {description}, calcule as calorias.")
    except Exception as e:
        print(f"Erro HuggingFace: {e}")
        return None

# 5. Handlers
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    status_msg = await update.message.reply_text("⏳ Processando...")

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = f"img_{user_id}.jpg"
        await file.download_to_drive(path)
        result = ask_hf_vision(path)
        if os.path.exists(path): os.remove(path)
    else:
        result = ask_groq_text(update.message.text)

    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        data[user_id][today]["calories"] += result["calories"]
        save_data(data)
        
        await status_msg.edit_text(
            f"✅ *{result['food']}*\n🔥 +{result['calories']} kcal\n📊 Total hoje: {data[user_id][today]['calories']} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Erro ao identificar. Tente descrever por texto.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    print("🚀 Bot rodando! Texto: Groq | Fotos: Hugging Face")
    app.run_polling()

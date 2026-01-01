import json
import os
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Configurações
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"

# MODELOS ATUALIZADOS PARA 2026
MODEL_VISION = "llama-3.2-11b-vision-instant" 
MODEL_TEXT = "llama-3.3-70b-versatile"

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

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

# 3. Inteligência Artificial (Groq)
def ask_groq_vision(image_path):
    base64_image = encode_image(image_path)
    try:
        response = client.chat.completions.create(
            model=MODEL_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Aja como nutricionista. Identifique o alimento e estime as calorias. Retorne APENAS um JSON: {\"food\": \"nome\", \"calories\": 0}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ Erro na Visão Groq: {e}")
        return None

def ask_groq_text(text):
    try:
        response = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[{"role": "user", "content": f"Nutricionista. Analise: {text}. Retorne APENAS JSON: {{\"food\": \"nome\", \"calories\": 0}}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except: return None

# 4. Handlers do Telegram
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    status_msg = await update.message.reply_text("⏳ Analisando...")

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = f"temp_{user_id}.jpg"
        await file.download_to_drive(path)
        result = ask_groq_vision(path)
        if os.path.exists(path): os.remove(path)
    else:
        result = ask_groq_text(update.message.text)

    if result and "calories" in result:
        data = load_data()
        if user_id not in data: data[user_id] = {}
        if today not in data[user_id]: data[user_id][today] = {"calories": 0}
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)
        
        total = data[user_id][today]["calories"]
        await status_msg.edit_text(
            f"✅ *{result['food']}*\n🔥 +{cal} kcal\n📊 Total hoje: {total} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui identificar a comida. Tente mandar outra foto ou escrever o nome.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    print("-" * 30)
    print("🚀 BOT GROQ VISION ATUALIZADO!")
    print(f"Modelo: {MODEL_VISION}")
    print("-" * 30)
    app.run_polling()

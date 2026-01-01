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
# Usando o modelo de visão da Groq (Llama 3.2 11b Vision)
MODEL_VISION = "llama-3.2-11b-vision-preview"
MODEL_TEXT = "llama-3.3-70b-versatile"

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 2. IA Unificada (Groq para tudo!)
def ask_groq_vision(image_path):
    base64_image = encode_image(image_path)
    try:
        response = client.chat.completions.create(
            model=MODEL_VISION,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Retorne APENAS um JSON: {\"food\": \"nome\", \"calories\": 0}"},
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
            messages=[{"role": "user", "content": f"Nutricionista. Analise: {text}. JSON: {{\"food\": \"nome\", \"calories\": 0}}"}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except: return None

# 3. Lógica do Telegram
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
        # (Lógica de salvar no JSON igual à anterior)
        with open(DATA_FILE, "r+") as f: # Simplificado para o exemplo
            # ... (código de salvamento que já temos)
            pass
        await status_msg.edit_text(f"✅ {result['food']} - {result['calories']} kcal")
    else:
        await status_msg.edit_text("❌ Não consegui identificar.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    print("🚀 BOT 100% GROQ ATIVO! Sem frescura de Gemini.")
    app.run_polling()

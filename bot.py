import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# Carregar variáveis
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_KEY:
    print("❌ Erro: Configure TELEGRAM_BOT_TOKEN e GROQ_API_KEY no .env")
    exit()

client = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def ask_groq(text):
    prompt = f"Você é um nutricionista. Analise: '{text}'. Retorne APENAS um JSON: {{\"food\": \"nome\", \"calories\": 0}}"
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            response_format={"type": "json_object"}
        )
        return json.loads(chat_completion.choices[0].message.content)
    except Exception as e:
        print(f"Erro na IA: {e}")
        return None

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    msg = await update.message.reply_text("⏳ Calculando...")
    result = ask_groq(update.message.text)

    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        data[user_id][today]["calories"] += result["calories"]
        save_data(data)
        
        await msg.edit_text(f"✅ {result['food']}\n🔥 +{result['calories']} kcal\n📊 Total hoje: {data[user_id][today]['calories']} kcal")
    else:
        await msg.edit_text("❌ Não entendi o alimento.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🚀 Bot rodando com Groq! Mande o nome de uma comida no Telegram.")
    app.run_polling()

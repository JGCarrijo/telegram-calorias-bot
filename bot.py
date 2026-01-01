import os
import json
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN não definido")

DATA_FILE = "data.json"
USER_STATE = {}  # estado por usuário


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Envie a foto da refeição\n"
        "Depois envie a descrição (ex: 'uma maçã')\n\n"
        "/resumo → média semanal\n"
        "'primeira refeição' → reinicia o dia"
    )


async def reset_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    data[user_id] = []
    save_data(data)
    await update.message.reply_text("🔄 Dia reiniciado!")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    USER_STATE[user_id] = {"waiting_description": True}
    await update.message.reply_text("✍️ Agora envie a descrição da refeição")


def ask_gemini(description):
    prompt = f"""
    O usuário comeu: {description}

    Identifique o alimento e estime as calorias.
    Responda no formato:
    Alimento: nome
    Calorias: número
    """

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro:generateContent?key=" + GEMINI_API_KEY
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    response = requests.post(url, json=payload, timeout=30)

    if response.status_code != 200:
        return None

    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return text
    except Exception:
        return None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()

    if text == "primeira refeição":
        await reset_day(update, context)
        return

    if user_id not in USER_STATE or not USER_STATE[user_id].get("waiting_description"):
        return

    USER_STATE[user_id]["waiting_description"] = False

    result = ask_gemini(text)

    if not result:
        await update.message.reply_text("❌ Não consegui reconhecer o alimento. Tente descrever melhor.")
        return

    await update.message.reply_text(f"🍽️ Registro:\n{result}")

    data = load_data()
    uid = str(user_id)
    data.setdefault(uid, []).append(result)
    save_data(data)


def main():
    print("🤖 Bot rodando...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    main()

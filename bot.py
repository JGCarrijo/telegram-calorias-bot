import os
import json
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN não definido")

DATA_FILE = "data.json"
USER_STATE = {}


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
        "✍️ Depois descreva (ex: 'uma maçã média')\n\n"
        "/resumo → média semanal\n"
        "'primeira refeição' → reinicia o dia"
    )


async def reset_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load_data()
    data[uid] = []
    save_data(data)
    await update.message.reply_text("🔄 Dia reiniciado!")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    photo = update.message.photo[-1]
    USER_STATE[user_id] = {
        "step": "waiting_description",
        "photo_file_id": photo.file_id,
    }

    await update.message.reply_text(
        "✍️ Agora descreva a refeição\n"
        "Ex: *uma maçã média*", parse_mode="Markdown"
    )


def ask_gemini(description):
    prompt = f"""
O usuário descreveu a refeição como: {description}

Identifique UM alimento principal e estime as calorias.
Se não for comida, responda apenas: NÃO É ALIMENTO

Formato obrigatório:
Alimento: nome
Calorias: número
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro:generateContent?key=" + GEMINI_API_KEY
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        r = requests.post(url, json=payload, timeout=40)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return text
    except Exception:
        return None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    if text == "primeira refeição":
        await reset_day(update, context)
        return

    if user_id not in USER_STATE:
        return

    state = USER_STATE[user_id]

    if state["step"] != "waiting_description":
        return

    result = ask_gemini(text)

    if not result or "NÃO É ALIMENTO" in result.upper():
        await update.message.reply_text(
            "❌ Não consegui reconhecer.\n"
            "👉 Tente algo como:\n"
            "*uma maçã média*\n"
            "*200g de arroz cozido*",
            parse_mode="Markdown",
        )
        return  # 👈 NÃO APAGA O ESTADO

    # ✅ SUCESSO → AGORA SIM ENCERRA
    del USER_STATE[user_id]

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

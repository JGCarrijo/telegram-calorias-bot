import json
import os
import requests
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ========================
# CONFIG
# ========================

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN não definido")

DATA_FILE = "data.json"

META = {
    "calories": 3300
}

# ========================
# UTIL
# ========================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ========================
# GEMINI
# ========================

def ask_gemini(description):
    prompt = f"""
Você é um assistente de nutrição.

O usuário descreveu a refeição assim:
"{description}"

Responda APENAS em JSON válido, sem texto extra.

Formato obrigatório:
{{
  "food": "nome do alimento",
  "calories": número
}}

Se não for possível identificar um alimento, retorne:
{{ "food": null, "calories": null }}
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-pro:generateContent?key=" + GEMINI_API_KEY
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        r = requests.post(url, json=payload, timeout=40)
        r.raise_for_status()
        data = r.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)

        if not parsed.get("food") or not parsed.get("calories"):
            return None

        return parsed

    except Exception as e:
        print("Erro Gemini:", e)
        return None

# ========================
# HANDLERS
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Envie a descrição da refeição\n"
        "Exemplos:\n"
        "• uma maçã\n"
        "• prato de arroz e feijão\n\n"
        "/resumo → resumo do dia\n"
        "primeira refeição → reinicia o dia"
    )

async def reset_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.message.from_user.id)
    today = str(date.today())

    data = load_data()
    data.setdefault(user, {})
    data[user][today] = {"calories": 0}

    save_data(data)

    await update.message.reply_text("🔄 Dia reiniciado!")

async def resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.message.from_user.id)
    today = str(date.today())

    data = load_data()
    calories = data.get(user, {}).get(today, {}).get("calories", 0)

    await update.message.reply_text(
        f"🔥 Hoje: {int(calories)} / {META['calories']} kcal"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()

    if text == "primeira refeição":
        await reset_day(update, context)
        return

    result = ask_gemini(text)

    if not result:
        await update.message.reply_text(
            "❌ Não consegui reconhecer o alimento.\n"
            "👉 Tente algo como:\n"
            "• uma maçã média\n"
            "• 2 fatias de pão\n"
            "• prato de arroz e feijão"
        )
        return

    user = str(update.message.from_user.id)
    today = str(date.today())

    data = load_data()
    data.setdefault(user, {})
    data[user].setdefault(today, {"calories": 0})

    data[user][today]["calories"] += result["calories"]
    save_data(data)

    await update.message.reply_text(
        f"🍽️ {result['food']}\n"
        f"🔥 {int(result['calories'])} kcal adicionadas\n\n"
        f"Total hoje: {int(data[user][today]['calories'])} kcal"
    )

# ========================
# MAIN
# ========================

def main():
    print("🤖 Bot rodando... pressione CTRL+C para parar")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumo", resumo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()

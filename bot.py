import os
import json
import base64
import logging
import unicodedata
from datetime import date, timedelta

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# =====================
# CONFIGURAÇÃO
# =====================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
USDA_KEY = os.getenv("USDA_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN não definido")

META = {
    "calories": 3300,
    "protein": 175,
    "fat": 95,
    "carbs": 435
}

DATA_FILE = "data.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================
# UTILIDADES
# =====================

def normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.strip()

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# =====================
# USDA
# =====================

def fetch_usda(food):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "api_key": USDA_KEY,
        "query": food,
        "pageSize": 1
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    nutrients = data["foods"][0]["foodNutrients"]

    def get(name):
        for n in nutrients:
            if name in n["nutrientName"].lower():
                return float(n["value"])
        return 0.0

    return {
        "calories": get("energy"),
        "protein": get("protein"),
        "fat": get("fat"),
        "carbs": get("carbohydrate")
    }

# =====================
# GEMINI (IMAGEM)
# =====================

def identify_food(text, image_path):
    image_b64 = base64.b64encode(open(image_path, "rb").read()).decode()

    prompt = f"""
Analise a imagem e o texto: "{text}"
Retorne APENAS JSON neste formato:
{{ "food": "nome do alimento", "grams": numero }}
"""

    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_b64
                    }
                }
            ]
        }]
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GEMINI_KEY}"

    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    response = r.json()

    text_response = response["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text_response)

# =====================
# BOT
# =====================

data = load_data()
pending = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Envie a foto da refeição + descrição\n"
        "/resumo → média semanal\n"
        "'primeira refeição' → reinicia o dia"
    )

async def resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.message.from_user.id)
    days = [(date.today() - timedelta(days=i)).isoformat() for i in range(7)]

    totals = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
    count = 0

    for d in days:
        if user in data and d in data[user]:
            for k in totals:
                totals[k] += data[user][d][k]
            count += 1

    if count == 0:
        await update.message.reply_text("📊 Nenhum dado nos últimos 7 dias.")
        return

    for k in totals:
        totals[k] /= count

    await update.message.reply_text(
        f"📊 Média 7 dias\n"
        f"🔥 {int(totals['calories'])} kcal\n"
        f"🥩 {int(totals['protein'])} g\n"
        f"🥑 {int(totals['fat'])} g\n"
        f"🍞 {int(totals['carbs'])} g"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.message.from_user.id)
    today = date.today().isoformat()

    data.setdefault(user, {})
    data[user].setdefault(today, {"calories": 0, "protein": 0, "fat": 0, "carbs": 0})

    text = normalize(update.message.text or "")

    # PRIMEIRA REFEIÇÃO
    if "primeira refeicao" in text:
        data[user][today] = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0}
        save_data(data)
        await update.message.reply_text("🔄 Novo dia iniciado!")
        return

    # FOTO
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = f"temp_{user}.jpg"
        await file.download_to_drive(path)
        pending[user] = {"image": path}
        await update.message.reply_text("📸 Foto recebida! Agora descreva.")
        return

    # TEXTO APÓS FOTO
    if user in pending and "image" in pending[user]:
        try:
            info = identify_food(text, pending[user]["image"])
            base = fetch_usda(info["food"])

            pending[user] = {
                "grams": info["grams"],
                "base": base
            }

            await update.message.reply_text(
                f"🍽️ {info['food']}\n"
                f"📏 Estimado: {info['grams']} g\n"
                "Digite a quantidade real ou 'ok'"
            )
        except Exception as e:
            logger.exception(e)
            pending.pop(user, None)
            await update.message.reply_text(
                "⚠️ Não consegui identificar o alimento.\n"
                "Tente uma descrição mais clara."
            )
        return

    # CONFIRMAÇÃO
    if user in pending and "base" in pending[user]:
        grams = pending[user]["grams"] if text == "ok" else float(text)
        factor = grams / 100

        for k in META:
            data[user][today][k] += pending[user]["base"][k] * factor

        pending.pop(user)
        save_data(data)

        c = data[user][today]
        rest = META["calories"] - c["calories"]

        await update.message.reply_text(
            f"🔥 {int(c['calories'])}/{META['calories']} kcal\n"
            f"🥩 {int(c['protein'])}/{META['protein']} g\n"
            f"🥑 {int(c['fat'])}/{META['fat']} g\n"
            f"🍞 {int(c['carbs'])}/{META['carbs']} g\n\n"
            f"{'👉 Restam ' + str(int(rest)) + ' kcal 👍' if rest > 0 else '⚠️ Meta ultrapassada'}"
        )

# =====================
# MAIN
# =====================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("resumo", resumo))
app.add_handler(MessageHandler(filters.ALL, handle_message))

print("🤖 Bot rodando...")
app.run_polling()

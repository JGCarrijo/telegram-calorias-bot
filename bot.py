import json
import base64
import requests
from datetime import date, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =====================
# 🔑 TOKENS (fixos)
# =====================
TELEGRAM_TOKEN = "8460032402:AAH1-9x5GpyD30I_bBx6IjDAqFIp_2FV5Zo"
GEMINI_API_KEY = "AIzaSyBQbjjMx_5sQ4bNlfkJ5NFTpAmKVYvCOYc"
USDA_API_KEY = "WjwD1SJlqgaJfVWee01JeTkTZF8Cx3e9ShnTIhhH"

DATA_FILE = "data.json"

META = {
    "calories": 3300,
    "protein": 175,
    "fat": 95,
    "carbs": 435
}

pending = {}

# =====================
# 📦 Persistência
# =====================
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# =====================
# 🥗 USDA
# =====================
def fetch_usda(food):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "api_key": USDA_API_KEY,
        "query": food,
        "pageSize": 1
    }
    r = requests.get(url, params=params).json()
    nutrients = r["foods"][0]["foodNutrients"]

    def get(name):
        for n in nutrients:
            if name in n["nutrientName"].lower():
                return n.get("value", 0)
        return 0

    return {
        "calories": get("energy"),
        "protein": get("protein"),
        "fat": get("fat"),
        "carbs": get("carbohydrate")
    }

# =====================
# 🧠 Gemini Vision
# =====================
def identify_food(text, image_path):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    body = {
        "contents": [{
            "parts": [
                {"text": f'Analise a imagem e o texto "{text}". Retorne APENAS JSON no formato {{ "food": "nome", "grams": numero }}'},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_b64
                    }
                }
            ]
        }]
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key={GEMINI_API_KEY}"
    r = requests.post(url, json=body).json()
    return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])

# =====================
# 🤖 Handlers
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Envie a foto da refeição + descrição\n"
        "/resumo → média semanal\n"
        "'primeira refeição' → reinicia o dia"
    )

async def resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = str(update.effective_user.id)

    days = [(date.today() - timedelta(days=i)).isoformat() for i in range(7)]
    week = [data.get(user, {}).get(d) for d in days if d in data.get(user, {})]

    if not week:
        await update.message.reply_text("Sem dados ainda 🙂")
        return

    avg = {k: sum(d[k] for d in week) / len(week) for k in META}
    await update.message.reply_text(
        f"📊 Últimos 7 dias\n"
        f"🔥 {int(avg['calories'])} kcal\n"
        f"🥩 {int(avg['protein'])} g\n"
        f"🥑 {int(avg['fat'])} g\n"
        f"🍞 {int(avg['carbs'])} g"
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.lower()
    user = str(update.effective_user.id)
    today = date.today().isoformat()

    data = load_data()
    data.setdefault(user, {})
    data[user].setdefault(today, {k: 0 for k in META})

    if msg == "primeira refeição":
        data[user][today] = {k: 0 for k in META}
        save_data(data)
        await update.message.reply_text("🔄 Novo dia iniciado")
        return

    if user in pending and "base" in pending[user]:
        grams = pending[user]["grams"] if msg == "ok" else float(msg)
        factor = grams / 100

        for k in META:
            data[user][today][k] += pending[user]["base"][k] * factor

        save_data(data)
        pending.pop(user)

        c = data[user][today]
        await update.message.reply_text(
            f"🔥 {int(c['calories'])}/{META['calories']} kcal\n"
            f"🥩 {int(c['protein'])}/{META['protein']} g\n"
            f"🥑 {int(c['fat'])}/{META['fat']} g\n"
            f"🍞 {int(c['carbs'])}/{META['carbs']} g"
        )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    photo = update.message.photo[-1]
    file = await photo.get_file()
    path = f"tmp_{user}.jpg"
    await file.download_to_drive(path)

    pending[user] = {"image": path}
    await update.message.reply_text("📸 Foto recebida! Agora descreva.")

async def description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    if user not in pending or "image" not in pending[user]:
        return

    info = identify_food(update.message.text, pending[user]["image"])
    base = fetch_usda(info["food"])

    pending[user] = {
        "grams": info["grams"],
        "base": base
    }

    await update.message.reply_text(
        f"🍽️ {info['food']}\n"
        f"📏 Estimado: {info['grams']}g\n"
        "Digite a quantidade real ou 'ok'"
    )

# =====================
# 🚀 Main
# =====================
def main():
    print("🤖 Bot rodando... CTRL+C para parar")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumo", resumo))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, description_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

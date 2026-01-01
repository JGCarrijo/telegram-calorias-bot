import json
import os
import requests
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image

# ========================
# CONFIG
# ========================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("❌ Variáveis de ambiente não configuradas no .env")

DATA_FILE = "data.json"
META = {"calories": 3300}

# ========================
# UTIL
# ========================
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ========================
# GEMINI VISION (A MÁGICA ACONTECE AQUI)
# ========================
def ask_gemini(description=None, image_path=None):
    # Usando o modelo flash que é mais rápido e suporta imagem
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um nutricionista digital. Analise o que o usuário enviou (texto ou imagem).
    Retorne APENAS um JSON no formato: {"food": "nome do item", "calories": 000}.
    Se for uma imagem, identifique o alimento e estime as calorias.
    Se não for comida, retorne {"food": null, "calories": null}."""

    parts = [{"text": prompt}]
    
    if description:
        parts.append({"text": f"O usuário enviou este texto: {description}"})
    
    if image_path:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": encode_image(image_path)
            }
        })

    payload = {"contents": [{"parts": parts}]}

    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        res_data = r.json()
        
        # Limpeza simples para garantir que pegamos apenas o JSON
        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        clean_json = text_response.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"Erro na API Gemini: {e}")
        return None

# ========================
# HANDLERS
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 Mande uma foto do seu prato ou descreva o que comeu!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Detecta se é foto ou texto
    is_photo = bool(update.message.photo)
    image_path = None

    msg = await update.message.reply_text("⏳ Analisando sua refeição...")

    if is_photo:
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{update.message.from_user.id}.jpg"
        await photo_file.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        text = update.message.text
        if text.lower() == "resumo":
            # Chamar função de resumo aqui (opcional)
            return
        result = ask_gemini(description=text)

    if result and result.get("food"):
        user_id = str(update.message.from_user.id)
        today = str(date.today())
        
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        data[user_id][today]["calories"] += result["calories"]
        save_data(data)

        await msg.edit_text(
            f"✅ Identificado: {result['food']}\n"
            f"🔥 +{result['calories']} kcal\n"
            f"📊 Total hoje: {data[user_id][today]['calories']} / {META['calories']} kcal"
        )
    else:
        await msg.edit_text("❌ Não consegui identificar o alimento. Tente tirar uma foto mais clara ou descrever em texto.")
    
    # Limpa arquivo temporário se existir
    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# ========================
# MAIN
# ========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    # Um único handler para tratar ambos
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    
    print("🚀 Bot rodando com Gemini Vision!")
    app.run_polling()

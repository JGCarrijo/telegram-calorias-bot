import json
import os
import requests
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 1. Configurações Iniciais
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN or not GEMINI_API_KEY:
    print("❌ Erro: Configure TELEGRAM_BOT_TOKEN e GEMINI_API_KEY no arquivo .env")
    exit()

DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Suporte
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# 3. Inteligência Artificial (Versão v1beta)
def ask_gemini(description=None, image_path=None):
    # Esta URL v1beta/gemini-1.5-flash é a mais compatível para resolver o erro 404
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um nutricionista. Analise e retorne APENAS um JSON puro.
    Formato: {"food": "nome do item", "calories": 123}
    Se não for comida, use null."""

    parts = [{"text": prompt}]
    if description: parts.append({"text": description})
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
        
        # Se der erro 404, tentamos um modelo alternativo automaticamente
        if r.status_code == 404:
            print("⚠️ Modelo Flash não encontrado. Tentando modelo Pro...")
            url_pro = url.replace("gemini-1.5-flash", "gemini-pro")
            r = requests.post(url_pro, json=payload, timeout=30)

        if r.status_code != 200:
            print(f"❌ Erro na API. Status: {r.status_code}")
            return None
            
        res_text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        clean_json = res_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"⚠️ Erro no processamento: {e}")
        return None

# 4. Comandos do Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 *NutriBot Online!* \nEnvie uma foto da comida ou descreva o que comeu.")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    image_path = None

    status_msg = await update.message.reply_text("⏳ Analisando...")

    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}.jpg"
        await photo.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        result = ask_gemini(description=update.message.text)

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
        await status_msg.edit_text("❌ Não identifiquei o alimento. Tente descrever por texto.")

    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# 5. Loop Principal
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_input))
    
    print("🚀 Bot iniciado! Teste enviando a palavra 'Maçã'.")
    app.run_polling()

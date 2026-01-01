import json
import os
import requests
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ========================
# CONFIGURAÇÃO
# ========================
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("❌ Verifique se TELEGRAM_BOT_TOKEN e GEMINI_API_KEY estão no seu arquivo .env")

DATA_FILE = "data.json"
META_CALORIAS = 3300

# ========================
# UTILITÁRIOS
# ========================
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ========================
# INTEGRAÇÃO GEMINI 1.5 FLASH
# ========================
def ask_gemini(description=None, image_path=None):
    # Endpoint v1 oficial (mais estável que v1beta)
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um nutricionista. Analise o alimento e retorne APENAS um JSON.
    Formato: {"food": "nome", "calories": 000}
    Se não for comida, use null nos campos."""

    parts = [{"text": prompt}]
    
    if description:
        parts.append({"text": f"Usuário descreveu: {description}"})
    
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
        
        if r.status_code == 404:
            print("❌ ERRO 404: O modelo Gemini 1.5 Flash não foi encontrado. Verifique sua chave de API.")
            return None
        if r.status_code == 400:
            print("❌ ERRO 400: Requisição inválida. Verifique o formato dos dados.")
            return None

        r.raise_for_status()
        res_data = r.json()
        
        # Extrai e limpa o JSON da resposta
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        
        return json.loads(clean_json)
    except Exception as e:
        print(f"⚠️ Erro na API Gemini: {e}")
        return None

# ========================
# HANDLERS DO TELEGRAM
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 Envie uma foto do prato ou texto para contar calorias!")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    image_path = None

    status_msg = await update.message.reply_text("⏳ Analisando...")

    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}.jpg"
        await photo_file.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        result = ask_gemini(description=update.message.text)

    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)

        await status_msg.edit_text(
            f"✅ {result['food']}\n🔥 +{cal} kcal\n📊 Total hoje: {data[user_id][today]['calories']} kcal"
        )
    else:
        await status_msg.edit_text("❌ Não reconheci o alimento. Tente descrever melhor.")

    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# ========================
# EXECUÇÃO
# ========================
if __name__ == "__main__":
    print("🚀 Bot Iniciado!")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_input))
    app.run_polling()

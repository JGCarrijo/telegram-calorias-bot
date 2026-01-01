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
    print("❌ Erro: Chaves não configuradas no .env")
    exit()

DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Sistema
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

# 3. Função de Inteligência Artificial (Corrigida)
def ask_gemini(description=None, image_path=None):
    # URL com sufixo -latest para evitar erro 404
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um nutricionista. Analise o que foi enviado e responda APENAS um JSON.
    Exemplo: {"food": "Frango com arroz", "calories": 450}
    Se não for comida, responda: {"food": null, "calories": null}"""

    parts = [{"text": prompt}]
    if description:
        parts.append({"text": f"O usuário diz: {description}"})
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
        
        if r.status_code != 200:
            print(f"❌ Erro na API. Status: {r.status_code}")
            # Se der 400 aqui, verifique se sua chave tem espaços extras no .env
            return None
            
        res_data = r.json()
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Limpa formatações de código (```json) que a IA costuma colocar
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"⚠️ Erro ao processar IA: {type(e).__name__}")
        return None

# 4. Handlers do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 *NutriBot Online!* \nEnvie uma foto ou descreva o que comeu.")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    image_path = None

    status = await update.message.reply_text("🧐 Analisando...")

    if update.message.photo:
        # Pega a foto de maior qualidade
        photo = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}.jpg"
        await photo.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        result = ask_gemini(description=update.message.text)

    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)

        await status.edit_text(
            f"✅ *{result['food']}*\n🔥 +{cal} kcal\n📊 Total hoje: {data[user_id][today]['calories']} kcal"
        )
    else:
        await status.edit_text("❌ Não consegui identificar. Tente descrever por texto.")

    # Apaga a imagem temporária
    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# 5. Inicialização
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_input))
    
    print("🚀 Bot rodando! Mande um 'Oi' no Telegram para testar.")
    app.run_polling()

import json
import os
import requests
import base64
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 1. Carregar configurações do arquivo .env secreto
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN or not GEMINI_API_KEY:
    print("❌ Erro: Chaves não detectadas. Verifique seu arquivo .env")
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

# 3. Inteligência Artificial (Gemini 1.5 Flash)
def ask_gemini(description=None, image_path=None):
    # Usando v1beta e o modelo Flash (Multimodal)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um nutricionista digital. 
    Analise o que foi enviado (texto ou imagem) e retorne APENAS um JSON puro.
    Formato: {"food": "nome do item", "calories": 500}
    Se não for comida, use null nos campos."""

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
        # Enviamos a requisição
        r = requests.post(url, json=payload, timeout=30)
        
        # Se o status não for 200 (sucesso), avisamos sem mostrar a chave
        if r.status_code != 200:
            print(f"❌ Erro na API Gemini. Status: {r.status_code}")
            # Se for 400 ou 403, sua chave provavelmente foi desativada pelo Google
            return None
            
        res_data = r.json()
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Limpando possíveis formatações de markdown da resposta da IA
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
        
    except Exception as e:
        print(f"⚠️ Erro de processamento interno: {type(e).__name__}")
        return None

# 4. Comandos do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 *Bot de Calorias Ativo!*\n\nEnvie uma foto do prato ou descreva sua refeição.", parse_mode="Markdown")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    image_path = None

    status_msg = await update.message.reply_text("⏳ Processando...")

    # Verifica se o usuário mandou foto ou texto
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}.jpg"
        await photo_file.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        result = ask_gemini(description=update.message.text)

    # Lógica de salvamento e resposta
    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)

        await status_msg.edit_text(
            f"✅ *{result['food']}*\n🔥 +{cal} kcal\n📊 Total de hoje: {data[user_id][today]['calories']} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui identificar o alimento. Tente descrever por texto.")

    # Limpeza de arquivos temporários
    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# 5. Loop Principal
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_input))
    
    print("🚀 Bot iniciado com sucesso!")
    app.run_polling()

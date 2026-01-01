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
    raise RuntimeError("❌ Variáveis de ambiente TELEGRAM_BOT_TOKEN ou GEMINI_API_KEY não encontradas.")

DATA_FILE = "data.json"
META_CALORIAS = 3300

# ========================
# UTILITÁRIOS DE DADOS
# ========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ========================
# INTEGRAÇÃO GEMINI VISION
# ========================
def ask_gemini(description=None, image_path=None):
    # Usamos o endpoint v1 com o modelo gemini-1.5-flash
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """Você é um assistente de nutrição rigoroso. 
    Analise a entrada (texto ou imagem) e identifique o alimento e a estimativa de calorias.
    Responda APENAS um JSON puro, sem markdown, no formato:
    {"food": "nome do alimento", "calories": 500}
    Se não for comida, retorne: {"food": null, "calories": null}"""

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
        r.raise_for_status()
        res_data = r.json()
        
        # Extrai o texto da resposta
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # Limpeza de possíveis marcações de markdown ```json ... ```
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        
        return json.loads(clean_json)
    except Exception as e:
        print(f"Erro detalhado na API Gemini: {e}")
        return None

# ========================
# COMANDOS DO TELEGRAM
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍎 *Bem-vindo ao NutriBot!*\n\n"
        "Como usar:\n"
        "1. Envie uma **foto** do seu prato.\n"
        "2. Ou digite o que comeu (ex: '2 fatias de pizza').\n"
        "3. Use /resumo para ver o total do dia.",
        parse_mode="Markdown"
    )

async def resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    data = load_data()
    
    consumo = data.get(user_id, {}).get(today, {}).get("calories", 0)
    await update.message.reply_text(f"📊 *Resumo de Hoje*\n🔥 Consumido: {consumo} kcal\n🎯 Meta: {META_CALORIAS} kcal", parse_mode="Markdown")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    image_path = None

    msg_aguarde = await update.message.reply_text("🤔 Deixa eu ver...")

    # Verifica se é foto ou texto
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}.jpg"
        await photo_file.download_to_drive(image_path)
        result = ask_gemini(image_path=image_path)
    else:
        result = ask_gemini(description=update.message.text)

    # Processa o resultado da IA
    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        calorias = result["calories"]
        data[user_id][today]["calories"] += calorias
        save_data(data)

        texto_sucesso = (
            f"✅ *Identificado:* {result['food']}\n"
            f"🔥 *Calorias:* +{calorias} kcal\n"
            f"📈 *Total hoje:* {data[user_id][today]['calories']} kcal"
        )
        await msg_aguarde.edit_text(texto_sucesso, parse_mode="Markdown")
    else:
        await msg_aguarde.edit_text("❌ Não consegui identificar. Tente descrever por texto ou tire uma foto mais nítida.")

    # Remove a imagem temporária para não ocupar espaço
    if image_path and os.path.exists(image_path):
        os.remove(image_path)

# ========================
# EXECUÇÃO
# ========================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumo", resumo))
    # Captura tanto texto quanto foto no mesmo handler
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_input))

    print("🚀 Bot rodando! Aguardando mensagens...")
    app.run_polling()

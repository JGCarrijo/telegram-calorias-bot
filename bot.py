import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq
import google.generativeai as genai

# 1. Configurações de Ambiente
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Validação das chaves para evitar erros silenciosos
if not TOKEN:
    print("❌ ERRO: TELEGRAM_BOT_TOKEN não encontrado no .env")
    exit()
if not GROQ_KEY:
    print("❌ ERRO: GROQ_API_KEY não encontrado no .env")
    exit()
if not GEMINI_KEY:
    print("❌ ERRO: GEMINI_API_KEY não encontrado no .env")
    exit()

# Configuração da SDK Oficial do Google Gemini
genai.configure(api_key=GEMINI_KEY)
model_vision = genai.GenerativeModel('gemini-1.5-flash')

# Inicialização da Groq
client_groq = Groq(api_key=GROQ_KEY)

DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Banco de Dados (JSON)
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 3. Inteligência Artificial para Texto (Groq)
def ask_groq_text(text):
    prompt = f"Você é um nutricionista. Analise: '{text}'. Retorne APENAS um JSON: {{\"food\": \"nome\", \"calories\": 0}}"
    try:
        res = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Erro Groq: {e}")
        return None

# 4. Inteligência Artificial para Visão (Gemini SDK)
def ask_gemini_vision(image_path):
    try:
        # Carrega a imagem
        with open(image_path, "rb") as f:
            img_data = f.read()
        
        prompt = "Você é um nutricionista. Olhe esta imagem e retorne APENAS um JSON: {\"food\": \"nome do prato\", \"calories\": 0}"
        
        # Uso da SDK oficial para evitar erros de requisição manual
        response = model_vision.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": img_data}
        ])
        
        # Extração e limpeza do JSON na resposta
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ Erro na Visão (Gemini SDK): {e}")
        return None

# 5. Handlers do Telegram
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    status_msg = await update.message.reply_text("⏳ Analisando refeição...")

    if update.message.photo:
        # Baixa a foto enviada
        file = await update.message.photo[-1].get_file()
        path = f"temp_img_{user_id}.jpg"
        await file.download_to_drive(path)
        
        # Chama a visão do Gemini
        result = ask_gemini_vision(path)
        
        # Remove arquivo temporário
        if os.path.exists(path): os.remove(path)
    else:
        # Processa texto via Groq
        result = ask_groq_text(update.message.text)

    if result and "calories" in result:
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal = result["calories"]
        data[user_id][today]["calories"] += cal
        save_data(data)
        
        total = data[user_id][today]["calories"]
        await status_msg.edit_text(
            f"✅ *{result.get('food', 'Alimento')}*\n🔥 +{cal} kcal\n📊 Total hoje: {total} / {META_CALORIAS} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui identificar. Tente descrever por texto ou mande uma foto mais nítida.")

# 6. Inicialização
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    
    print("-" * 30)
    print("🚀 BOT NUTRI ATIVO!")
    print("Texto via: Groq (Llama 3.3)")
    print("Fotos via: Gemini (Flash 1.5)")
    print("-" * 30)
    app.run_polling()

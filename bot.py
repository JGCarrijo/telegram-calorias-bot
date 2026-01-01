import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq
import google.generativeai as genai

# 1. Configurações
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# Configura o Gemini pela biblioteca oficial
genai.configure(api_key=GEMINI_KEY)
model_gemini = genai.GenerativeModel('gemini-1.5-flash')

client_groq = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Banco de Dados
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

# 3. IA Texto (Groq)
def ask_groq_text(text):
    prompt = f"Nutricionista. Analise: '{text}'. Retorne APENAS JSON: {{\"food\": \"nome\", \"calories\": 0}}"
    try:
        res = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except: return None

# 4. IA Visão (Biblioteca Oficial Gemini)
def ask_gemini_vision(image_path):
    try:
        # Carrega a imagem
        with open(image_path, "rb") as f:
            img_data = f.read()
        
        prompt = "Você é um nutricionista. Olhe esta imagem e retorne APENAS um JSON: {\"food\": \"nome do prato\", \"calories\": 0}"
        
        # Faz a requisição usando a SDK oficial (mais estável)
        response = model_gemini.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": img_data}
        ])
        
        # Limpa e converte para JSON
        text_res = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text_res)
    except Exception as e:
        print(f"❌ Erro na Visão Gemini: {e}")
        return None

# 5. Lógica do Bot
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    status_msg = await update.message.reply_text("⏳ Analisando...")

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = f"img_{user_id}.jpg"
        await file.download_to_drive(path)
        result = ask_gemini_vision(path)
        if os.path.exists(path): os.remove(path)
    else:
        result = ask_groq_text(update.message.text)

    if result and result.get("food"):
        data = load_data()
        if user_id not in data: data[user_id] = {}
        if today not in data[user_id]: data[user_id][today] = {"calories": 0}
        
        data[user_id][today]["calories"] += result["calories"]
        save_data(data)
        
        await status_msg.edit_text(
            f"✅ *{result['food']}*\n🔥 +{result['calories']} kcal\n📊 Total hoje: {data[user_id][today]['calories']} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui identificar a comida.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    print("🚀 Bot rodando! Texto: Groq | Fotos: Gemini SDK")
    app.run_polling()

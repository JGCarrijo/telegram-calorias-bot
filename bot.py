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

# Validação crítica
if not all([TOKEN, GROQ_KEY, GEMINI_KEY]):
    print("❌ ERRO: Verifique se todas as chaves estão no arquivo .env")
    exit()

# Configuração da SDK Oficial do Google Gemini
# Usando a versão 1.5-flash-8b para máxima compatibilidade em 2026
genai.configure(api_key=GEMINI_KEY)
model_vision = genai.GenerativeModel('gemini-1.5-flash-8b')

# Inicialização da Groq
client_groq = Groq(api_key=GROQ_KEY)

DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Banco de Dados
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

# 3. IA para Texto (Groq)
def ask_groq_text(text):
    prompt = f"Nutricionista. Analise: '{text}'. Retorne APENAS um JSON: {{\"food\": \"nome\", \"calories\": 0}}"
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

# 4. IA para Visão (Gemini SDK)
def ask_gemini_vision(image_path):
    try:
        # Carregando imagem
        with open(image_path, "rb") as f:
            img_data = f.read()
        
        prompt = "Analise a imagem como nutricionista. Retorne APENAS um JSON puro: {\"food\": \"nome do prato\", \"calories\": 0}"
        
        # Fazendo a chamada para o modelo 8b
        response = model_vision.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": img_data}
        ])
        
        # Limpando a resposta de possíveis blocos de código Markdown
        raw_text = response.text
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"❌ Erro na Visão (Gemini SDK): {e}")
        return None

# 5. Lógica do Bot no Telegram
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    status_msg = await update.message.reply_text("⏳ Analisando refeição...")

    if update.message.photo:
        # Processamento de Foto
        file = await update.message.photo[-1].get_file()
        path = f"temp_{user_id}.jpg"
        await file.download_to_drive(path)
        
        result = ask_gemini_vision(path)
        
        if os.path.exists(path): os.remove(path)
    else:
        # Processamento de Texto
        result = ask_groq_text(update.message.text)

    if result and "calories" in result:
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal = int(result["calories"])
        data[user_id][today]["calories"] += cal
        save_data(data)
        
        total_dia = data[user_id][today]["calories"]
        await status_msg.edit_text(
            f"✅ *{result.get('food', 'Alimento')}*\n🔥 +{cal} kcal\n📊 Total hoje: {total_dia} / {META_CALORIAS} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui processar. Tente novamente ou descreva por texto.")

# 6. Inicialização do Bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_input))
    
    print("-" * 40)
    print("🚀 BOT NUTRI 2026 ATIVO!")
    print("Fotos usando: gemini-1.5-flash-8b")
    print("-" * 40)
    app.run_polling()

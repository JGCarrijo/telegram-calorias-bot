import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Configurações e Chaves
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_KEY:
    print("❌ Erro: Configure TELEGRAM_BOT_TOKEN e GROQ_API_KEY no arquivo .env")
    exit()

# Inicializa o cliente Groq
client = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Persistência de Dados
def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 3. Inteligência Artificial (Modelo Llama 3.3 Versatile)
def ask_groq(text):
    # Modelo atualizado para 2026 para evitar o erro de 'decommissioned'
    prompt = f"""Você é um nutricionista. Analise o alimento: '{text}'. 
    Retorne APENAS um objeto JSON puro no formato: 
    {{"food": "nome do alimento", "calories": 000}}"""
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile", 
            response_format={"type": "json_object"}
        )
        return json.loads(chat_completion.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ Erro na IA: {e}")
        return None

# 4. Handlers do Telegram
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍎 *NutriBot Ativo (Groq Llama 3.3)*\n\n"
        "Me diga o que você comeu e eu calculo as calorias.\n"
        "Exemplo: '1 pão francês com manteiga e um café'",
        parse_mode="Markdown"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    # Feedback visual para o usuário
    status_msg = await update.message.reply_text("⏳ Calculando...")
    
    result = ask_groq(update.message.text)

    if result and result.get("food"):
        data = load_data()
        data.setdefault(user_id, {}).setdefault(today, {"calories": 0})
        
        cal_item = result["calories"]
        data[user_id][today]["calories"] += cal_item
        save_data(data)
        
        total_hoje = data[user_id][today]["calories"]
        
        await status_msg.edit_text(
            f"✅ *{result['food']}*\n"
            f"🔥 +{cal_item} kcal\n\n"
            f"📊 *Total do dia:* {total_hoje} / {META_CALORIAS} kcal",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não consegui processar esse alimento. Tente ser mais específico.")

# 5. Loop Principal
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    print("🚀 Bot iniciado com sucesso! Use o comando /start no Telegram.")
    app.run_polling()

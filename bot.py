import json
import os
from datetime import date
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from groq import Groq

# 1. Configurações
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_KEY:
    print("❌ Erro: Configure TELEGRAM_BOT_TOKEN e GROQ_API_KEY no .env")
    exit()

client = Groq(api_key=GROQ_KEY)
DATA_FILE = "data.json"
META_CALORIAS = 3300

# 2. Funções de Dados (REVISADA)
def load_data():
    if not os.path.exists(DATA_FILE): 
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try: 
            data = json.load(f)
            # Garante que os dados sejam um dicionário, não uma lista
            return data if isinstance(data, dict) else {}
        except: 
            return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 3. IA com Modelo Atual
def ask_groq(text):
    prompt = f"Você é um nutricionista. Analise: '{text}'. Retorne APENAS um JSON puro: {{\"food\": \"nome\", \"calories\": 0}}"
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

# 4. Handlers do Telegram (REVISADO)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍎 *NutriBot Online!*\nMe mande o que você comeu.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    today = str(date.today())
    
    status_msg = await update.message.reply_text("⏳ Calculando...")
    result = ask_groq(update.message.text)

    if result and result.get("food"):
        # Carrega dados garantindo que é um dicionário
        data = load_data()
        
        # Estrutura: data[user_id][data_hoje]
        if user_id not in data:
            data[user_id] = {}
        if today not in data[user_id]:
            data[user_id][today] = {"calories": 0}
        
        cal_item = result["calories"]
        data[user_id][today]["calories"] += cal_item
        save_data(data)
        
        total = data[user_id][today]["calories"]
        await status_msg.edit_text(
            f"✅ *{result['food']}*\n🔥 +{cal_item} kcal\n📊 Total hoje: {total} / {META_CALORIAS} kcal", 
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Não entendi o alimento. Tente ser mais específico.")

# 5. Loop Principal
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    print("🚀 Bot iniciado com sucesso!")
    app.run_polling()

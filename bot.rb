require "telegram/bot"
require "net/http"
require "json"
require "bigdecimal"
require "bigdecimal/util"
require "date"
require "base64"
require "logger"

# =========================
# 🔑 TOKENS (COLE OS SEUS)
# =========================
TOKEN = "8460032402:AAH1-9x5GpyD30I_bBx6IjDAqFIp_2FV5Zo"
GEMINI_KEY = "AIzaSyBQbjjMx_5sQ4bNlfkJ5NFTpAmKVYvCOYc"
USDA_KEY = "WjwD1SJlqgaJfVWee01JeTkTZF8Cx3e9ShnTIhhH"

# =========================
# 🎯 METAS DIÁRIAS
# =========================
META = {
  calories: 3300.to_d,
  protein:  175.to_d,
  fat:      95.to_d,
  carbs:    435.to_d
}

DATA_FILE = "data.json"

# =========================
# 📦 STORAGE
# =========================
def load_data
  File.exist?(DATA_FILE) ? JSON.parse(File.read(DATA_FILE)) : {}
end

def save_data(data)
  File.write(DATA_FILE, JSON.pretty_generate(data))
end

# =========================
# 🥗 USDA
# =========================
def fetch_usda(food)
  uri = URI(
    "https://api.nal.usda.gov/fdc/v1/foods/search" \
    "?api_key=#{USDA_KEY}&query=#{URI.encode_www_form_component(food)}&pageSize=1"
  )

  res = JSON.parse(Net::HTTP.get(uri))
  nutrients = res.dig("foods", 0, "foodNutrients") || []

  get = ->(name) {
    n = nutrients.find { |x| x["nutrientName"].to_s.downcase.include?(name) }
    n ? n["value"].to_d : 0.to_d
  }

  {
    calories: get.call("energy"),
    protein:  get.call("protein"),
    fat:      get.call("fat"),
    carbs:    get.call("carbohydrate")
  }
end

# =========================
# 🤖 GEMINI (VISÃO)
# =========================
def identify_food(text, image_path)
  image_base64 = Base64.strict_encode64(File.binread(image_path))

  prompt = <<~PROMPT
    Analise a imagem e o texto "#{text}".
    Retorne APENAS JSON neste formato:
    { "food": "nome", "grams": numero }
  PROMPT

  body = {
    contents: [
      {
        parts: [
          { text: prompt },
          {
            inline_data: {
              mime_type: "image/jpeg",
              data: image_base64
            }
          }
        ]
      }
    ]
  }

  uri = URI(
    "https://generativelanguage.googleapis.com/v1beta/" \
    "models/gemini-pro-vision:generateContent?key=#{GEMINI_KEY}"
  )

  res = Net::HTTP.post(uri, body.to_json, "Content-Type" => "application/json")
  json = JSON.parse(res.body)

  JSON.parse(json["candidates"][0]["content"]["parts"][0]["text"])
end

# =========================
# 🚨 FORÇA POLLING (REMOVE WEBHOOK)
# =========================
puts "🧹 Removendo webhook (garantindo polling)..."
Net::HTTP.get(URI("https://api.telegram.org/bot#{TOKEN}/deleteWebhook"))

puts "🤖 Bot rodando... pressione CTRL+C para parar"

# =========================
# 📲 TELEGRAM BOT
# =========================
Telegram::Bot::Client.run(TOKEN, logger: Logger.new($stdout)) do |bot|
  data = load_data
  pending = {}

  bot.listen do |msg|
    next unless msg.from

    user = msg.from.id.to_s
    today = Date.today.to_s

    data[user] ||= {}
    data[user][today] ||= META.transform_values { 0.to_d }

    puts "📩 Mensagem recebida: #{msg.text || '[foto]'}"

    if msg.text == "/start"
      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "📸 Envie a foto da refeição + descrição\n" \
              "'primeira refeição' → novo dia\n" \
              "/resumo → média semanal"
      )
    end

    if msg.text == "primeira refeição"
      data[user][today] = META.transform_values { 0.to_d }
      save_data(data)
      bot.api.send_message(chat_id: msg.chat.id, text: "🔄 Novo dia iniciado")
    end

    if msg.photo
      file = bot.api.get_file(file_id: msg.photo.last.file_id)
      path = "tmp_#{user}.jpg"
      File.write(
        path,
        Net::HTTP.get(
          URI("https://api.telegram.org/file/bot#{TOKEN}/#{file["result"]["file_path"]}")
        )
      )
      pending[user] = { image: path }
      bot.api.send_message(chat_id: msg.chat.id, text: "📸 Foto recebida! Agora descreva.")
    end

    if pending[user]&.dig(:image) && msg.text && !msg.text.start_with?("/")
      info = identify_food(msg.text, pending[user][:image])
      base = fetch_usda(info["food"])

      pending[user] = {
        grams: info["grams"].to_d,
        base: base
      }

      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "🍽️ #{info["food"]}\n" \
              "📏 Estimado: #{info["grams"]}g\n" \
              "Digite a quantidade real ou 'ok'"
      )
    end

    if pending[user]&.dig(:base) && msg.text
      grams = msg.text == "ok" ? pending[user][:grams] : msg.text.to_d
      factor = grams / 100

      META.each_key do |k|
        data[user][today][k] += pending[user][:base][k] * factor
      end

      pending.delete(user)
      save_data(data)

      c = data[user][today]
      rest = META[:calories] - c["calories"]

      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "🔥 #{c["calories"].to_i}/3300 kcal\n" \
              "🥩 #{c["protein"].to_i}/175g\n" \
              "🥑 #{c["fat"].to_i}/95g\n" \
              "🍞 #{c["carbs"].to_i}/435g\n\n" \
              "#{rest > 0 ? "👉 Restam #{rest.to_i} kcal" : "⚠️ Meta ultrapassada"}"
      )
    end

    if msg.text == "/resumo"
      days = (0..6).map { |i| (Date.today - i).to_s }
      week = days.map { |d| data[user][d] }.compact

      avg = META.transform_values { 0.to_d }
      week.each { |d| avg.each_key { |k| avg[k] += d[k].to_d } }
      avg.each_key { |k| avg[k] /= week.size if week.any? }

      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "📊 Média últimos 7 dias\n" \
              "🔥 #{avg[:calories].to_i} kcal\n" \
              "🥩 #{avg[:protein].to_i}g\n" \
              "🥑 #{avg[:fat].to_i}g\n" \
              "🍞 #{avg[:carbs].to_i}g"
      )
    end
  end
end

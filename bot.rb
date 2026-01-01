require "telegram/bot"
require "net/http"
require "json"
require "bigdecimal"
require "bigdecimal/util"
require "date"
require "base64"
require "logger"
require "openssl"

# =========================
# 🔑 TOKENS (JÁ DEFINIDOS)
# =========================
TOKEN = "8460032402:AAH1-9x5GpyD30I_bBx6IjDAqFIp_2FV5Zo"
GEMINI_KEY = "AIzaSyBQbjjMx_5sQ4bNlfkJ5NFTpAmKVYvCOYc"
USDA_KEY = "WjwD1SJlqgaJfVWee01JeTkTZF8Cx3e9ShnTIhhH"

# =========================
# ⚙️ NETWORK FIX (WINDOWS)
# =========================
Net::HTTP.const_set(:DEFAULT_OPEN_TIMEOUT, 30)
Net::HTTP.const_set(:DEFAULT_READ_TIMEOUT, 30)
OpenSSL::SSL::VERIFY_PEER = OpenSSL::SSL::VERIFY_NONE

# =========================
# 🎯 METAS
# =========================
META = {
  calories: 3300.to_d,
  protein: 175.to_d,
  fat: 95.to_d,
  carbs: 435.to_d
}

DATA_FILE = "data.json"

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
  uri = URI("https://api.nal.usda.gov/fdc/v1/foods/search")
  uri.query = URI.encode_www_form(
    api_key: USDA_KEY,
    query: food,
    pageSize: 1
  )

  res = Net::HTTP.get_response(uri)
  return { calories: 0, protein: 0, fat: 0, carbs: 0 } unless res.is_a?(Net::HTTPSuccess)

  json = JSON.parse(res.body)
  nutrients = json.dig("foods", 0, "foodNutrients") || []

  get = ->(name) {
    n = nutrients.find { |x| x["nutrientName"].to_s.downcase.include?(name) }
    n ? n["value"].to_d : 0.to_d
  }

  {
    calories: get.call("energy"),
    protein: get.call("protein"),
    fat: get.call("fat"),
    carbs: get.call("carbohydrate")
  }
end

# =========================
# 🤖 GEMINI
# =========================
def identify_food(text, image_path)
  image_base64 = Base64.strict_encode64(File.binread(image_path))

  body = {
    contents: [{
      parts: [
        { text: "Identifique o alimento e o peso aproximado. Retorne apenas JSON {food, grams}" },
        { inline_data: { mime_type: "image/jpeg", data: image_base64 } }
      ]
    }]
  }

  uri = URI("https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key=#{GEMINI_KEY}")
  res = Net::HTTP.post(uri, body.to_json, "Content-Type" => "application/json")

  json = JSON.parse(res.body)
  JSON.parse(json["candidates"][0]["content"]["parts"][0]["text"])
rescue
  { "food" => "alimento desconhecido", "grams" => 100 }
end

# =========================
# 🚀 BOT
# =========================
puts "🤖 Bot rodando (polling puro)... CTRL+C para parar"

Telegram::Bot::Client.run(TOKEN, logger: Logger.new($stdout)) do |bot|
  data = load_data
  pending = {}

  bot.listen do |msg|
    next unless msg.from
    user = msg.from.id.to_s
    today = Date.today.to_s

    data[user] ||= {}
    data[user][today] ||= META.transform_values { 0.to_d }

    if msg.text == "/start"
      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "📸 Envie a foto da refeição + descrição\nDigite 'primeira refeição' para zerar o dia"
      )
    end

    if msg.text == "primeira refeição"
      data[user][today] = META.transform_values { 0.to_d }
      save_data(data)
      bot.api.send_message(chat_id: msg.chat.id, text: "🔄 Dia reiniciado")
    end

    if msg.photo
      file = bot.api.get_file(file_id: msg.photo.last.file_id)
      path = "img_#{user}.jpg"
      File.write(path, Net::HTTP.get(URI("https://api.telegram.org/file/bot#{TOKEN}/#{file["result"]["file_path"]}")))
      pending[user] = { image: path }
      bot.api.send_message(chat_id: msg.chat.id, text: "📸 Foto recebida! Agora descreva.")
    end

    if pending[user]&.dig(:image) && msg.text && !msg.text.start_with?("/")
      info = identify_food(msg.text, pending[user][:image])
      base = fetch_usda(info["food"])
      pending[user] = { grams: info["grams"].to_d, base: base }

      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "🍽️ #{info["food"]}\nEstimado: #{info["grams"]}g\nDigite a quantidade real ou 'ok'"
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
      bot.api.send_message(
        chat_id: msg.chat.id,
        text: "🔥 #{c["calories"].to_i}/3300 kcal\n🥩 #{c["protein"].to_i}g"
      )
    end
  end
end

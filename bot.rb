require "net/http"
require "json"
require "bigdecimal"
require "bigdecimal/util"
require "date"
require "base64"

TOKEN      = ENV["TELEGRAM_BOT_TOKEN"]
USDA_KEY   = ENV["USDA_API_KEY"]
GEMINI_KEY = ENV["GEMINI_API_KEY"]

META = {
  calories: 3300.to_d,
  protein:  175.to_d,
  fat:      95.to_d,
  carbs:    435.to_d
}

DATA_FILE = "data.json"

def load_data
  File.exist?(DATA_FILE) ? JSON.parse(File.read(DATA_FILE)) : {}
end

def save_data(data)
  File.write(DATA_FILE, JSON.pretty_generate(data))
end

def tg_post(method, payload)
  uri = URI("https://api.telegram.org/bot#{TOKEN}/#{method}")
  Net::HTTP.post(uri, payload.to_json, "Content-Type" => "application/json")
end

def fetch_usda(food)
  uri = URI("https://api.nal.usda.gov/fdc/v1/foods/search?api_key=#{USDA_KEY}&query=#{URI.encode(food)}&pageSize=1")
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

def identify_food(text, image_path)
  image_base64 = Base64.strict_encode64(File.binread(image_path))

  prompt = <<~PROMPT
    Analise a imagem e o texto "#{text}".
    Identifique o alimento e estime a quantidade.
    Retorne APENAS JSON:
    { "food": "nome", "grams": numero }
  PROMPT

  body = {
    contents: [{
      parts: [
        { text: prompt },
        {
          inline_data: {
            mime_type: "image/jpeg",
            data: image_base64
          }
        }
      ]
    }]
  }

  uri = URI("https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision:generateContent?key=#{GEMINI_KEY}")
  res = Net::HTTP.post(uri, body.to_json, "Content-Type" => "application/json")
  json = JSON.parse(res.body)

  JSON.parse(json["candidates"][0]["content"]["parts"][0]["text"])
end

offset  = 0
data    = load_data
pending = {}

puts "🤖 Bot rodando... pressione CTRL+C para parar"

loop do
  uri = URI("https://api.telegram.org/bot#{TOKEN}/getUpdates?timeout=30&offset=#{offset}")
  updates = JSON.parse(Net::HTTP.get(uri))["result"]

  updates.each do |update|
    offset = update["update_id"] + 1
    msg = update["message"]
    next unless msg

    chat_id = msg["chat"]["id"]
    user    = msg["from"]["id"].to_s
    today   = Date.today.to_s

    data[user] ||= {}
    data[user][today] ||= META.transform_values { 0.to_d }

    if msg["text"] == "/start"
      tg_post("sendMessage", {
        chat_id: chat_id,
        text: "📸 Envie a foto da refeição + descrição\n/resumo → resumo semanal\n'primeira refeição' → novo dia"
      })
    end

    if msg["text"] == "primeira refeição"
      data[user][today] = META.transform_values { 0.to_d }
      save_data(data)
      tg_post("sendMessage", { chat_id: chat_id, text: "🔄 Novo dia iniciado" })
    end

    if msg["photo"]
      file_id = msg["photo"].last["file_id"]
      file = JSON.parse(Net::HTTP.get(URI("https://api.telegram.org/bot#{TOKEN}/getFile?file_id=#{file_id}")))
      path = "tmp_#{user}.jpg"
      File.write(path, Net::HTTP.get(URI("https://api.telegram.org/file/bot#{TOKEN}/#{file["result"]["file_path"]}")))

      pending[user] = { image: path }
      tg_post("sendMessage", { chat_id: chat_id, text: "📸 Foto recebida! Agora descreva." })
    end

    if pending[user]&.dig(:image) && msg["text"] && !msg["text"].start_with?("/")
      info = identify_food(msg["text"], pending[user][:image])
      base = fetch_usda(info["food"])

      pending[user] = { grams: info["grams"].to_d, base: base }

      tg_post("sendMessage", {
        chat_id: chat_id,
        text: "🍽️ #{info["food"]}\n📏 Estimado: #{info["grams"]}g\nDigite a quantidade real ou 'ok'"
      })
    end

    if pending[user]&.dig(:base) && msg["text"]
      grams  = msg["text"] == "ok" ? pending[user][:grams] : msg["text"].to_d
      factor = grams / 100

      META.each_key do |k|
        data[user][today][k] += pending[user][:base][k] * factor
      end

      pending.delete(user)
      save_data(data)

      c = data[user][today]
      rest = META[:calories] - c["calories"]

      tg_post("sendMessage", {
        chat_id: chat_id,
        text: "🔥 #{c["calories"].to_i}/3300 kcal\n🥩 #{c["protein"].to_i}/175g\n🥑 #{c["fat"].to_i}/95g\n🍞 #{c["carbs"].to_i}/435g\n\n#{rest > 0 ? "👉 Restam #{rest.to_i} kcal 👍" : "⚠️ Meta ultrapassada"}"
      })
    end

    if msg["text"] == "/resumo"
      days = (0..6).map { |i| (Date.today - i).to_s }
      week = days.map { |d| data[user][d] }.compact

      avg = META.transform_values { 0.to_d }
      week.each { |d| avg.each_key { |k| avg[k] += d[k].to_d } }
      avg.each_key { |k| avg[k] /= week.size if week.any? }

      tg_post("sendMessage", {
        chat_id: chat_id,
        text: "📊 Últimos 7 dias\n🔥 Média: #{avg[:calories].to_i} kcal\n🥩 #{avg[:protein].to_i}g\n🥑 #{avg[:fat].to_i}g\n🍞 #{avg[:carbs].to_i}g"
      })
    end
  end
end

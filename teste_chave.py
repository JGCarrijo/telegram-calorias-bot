import requests

# COLOQUE SUA CHAVE NOVA ENTRE AS ASPAS ABAIXO
CHAVE = "AIzaSyBQbjjMx_5sQ4bNlfkJ5NFTpAmKVYvCOYc"

# Testando dois endpoints comuns para ver qual responde
endpoints = [
    f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={CHAVE}",
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CHAVE}"
]

print("--- INICIANDO DIAGNÓSTICO ---")

for url in endpoints:
    version = "v1" if "v1/" in url else "v1beta"
    print(f"\nTentando versão {version}...")
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": "Oi"}]}]}, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("✅ SUCESSO! Este endpoint funciona.")
        else:
            print(f"❌ FALHA: {r.text}")
    except Exception as e:
        print(f"💥 ERRO DE CONEXÃO: {e}")

print("\n--- FIM DO TESTE ---")

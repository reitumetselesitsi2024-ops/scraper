import requests
import time

URL = "https://ebe8f301-2691-4730-94c7-9cd8eeea02b3-00-1l5p3jcikfpp4.worf.replit.dev"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Connection': 'keep-alive',
}

print("🚀 Monitor started. Pinging every 5 minutes...")

while True:
    try:
        r = requests.get(URL, headers=headers)
        print(f"[{time.strftime('%H:%M:%S')}] Status: {r.status_code}")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")
    time.sleep(300)

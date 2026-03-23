from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Your Replit URL
REPLIT_URL = "https://ebe8f301-2691-4730-94c7-9cd8eeea02b3-00-1l5p3jcikfpp4.worf.replit.dev"

print("🚀 Starting Selenium Keeper...")
print(f"Target URL: {REPLIT_URL}")

while True:
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        options.binary_location = '/usr/bin/google-chrome-stable'
        
        driver = webdriver.Chrome(options=options)
        print("✅ Chrome started")
        
        driver.get(REPLIT_URL)
        print(f"✅ Visited Replit: {driver.title}")
        
        # Keep the page open for 5 minutes
        time.sleep(300)
        
        driver.quit()
        print("✅ Session ended, restarting...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(60)

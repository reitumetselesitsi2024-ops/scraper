from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import os
import re
from datetime import datetime
from flask import Flask, jsonify
import threading

# ============= CONFIGURATION =============
SCRAPE_INTERVAL_MINUTES = 15
JSON_FILENAME = "results.json"
# ==========================================

app = Flask(__name__)

def sort_by_round_number(results):
    if not results:
        return results
    return sorted(results, key=lambda x: x.get('round_number', 0), reverse=True)

def load_existing_data():
    if not os.path.exists(JSON_FILENAME):
        return []
    try:
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('results', [])
    except:
        return []

def save_results(new_results):
    existing = load_existing_data()
    
    # Merge
    seen = set()
    all_results = []
    for r in existing:
        num = r.get('round_number')
        if num not in seen:
            seen.add(num)
            all_results.append(r)
    for r in new_results:
        num = r.get('round_number')
        if num not in seen:
            seen.add(num)
            all_results.append(r)
    
    # Sort by round number (newest first)
    all_results.sort(key=lambda x: x.get('round_number', 0), reverse=True)
    
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump({
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rows": len(all_results),
            "results": all_results
        }, f, indent=2)
    
    return len(all_results)

def extract_numbers_from_balls(balls_div):
    numbers = []
    buttons = balls_div.find_elements(By.TAG_NAME, "button")
    for button in buttons:
        text = button.text.strip()
        if text and text.isdigit():
            numbers.append(text)
    return numbers

def scrape_rounds():
    """Scrape rounds directly without Selenium Grid"""
    driver = None
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        
        driver = webdriver.Chrome(options=options)
        print("   ✅ Chrome started")
        
        driver.get('https://www.simacombet.com/luckysix')
        time.sleep(3)
        
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "PluginLuckySix"))
        )
        driver.switch_to.frame(iframe)
        
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Results')]"))
        )
        button.click()
        time.sleep(2)
        
        round_rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
        print(f"   Found {len(round_rows)} rounds")
        
        existing = load_existing_data()
        existing_nums = {r.get('round_number') for r in existing}
        
        new_rounds = []
        
        for row in round_rows:
            try:
                title = row.find_element(By.CSS_SELECTOR, "div.accordion-title")
                title_text = title.text.strip()
                match = re.search(r'Round\s*(\d+)', title_text)
                if not match:
                    continue
                round_num = int(match.group(1))
                
                if round_num in existing_nums:
                    continue
                
                driver.execute_script("arguments[0].scrollIntoView();", row)
                time.sleep(0.5)
                row.click()
                time.sleep(2)
                
                draw_seqs = driver.find_elements(By.CSS_SELECTOR, "div.draw-sequence")
                first_numbers = []
                
                for seq in draw_seqs:
                    seq_title = seq.find_element(By.CSS_SELECTOR, "div.title").text.lower()
                    if "drawn" in seq_title:
                        balls = seq.find_elements(By.CSS_SELECTOR, "div.balls")
                        for b in balls:
                            first_numbers.extend(extract_numbers_from_balls(b))
                
                result = {
                    'round_number': round_num,
                    'round_title': title_text,
                    'first_draw_numbers': [int(n) for n in first_numbers],
                    'second_draw_numbers': [],
                    'timestamp': datetime.now().isoformat()
                }
                new_rounds.append(result)
                print(f"   ✅ Round {round_num} collected")
                
                row.click()
                time.sleep(1)
                
            except Exception as e:
                print(f"   ⚠️ Error on round: {e}")
                continue
        
        if new_rounds:
            total = save_results(new_rounds)
            print(f"   💾 Saved {len(new_rounds)} new rounds. Total: {total}")
        else:
            print("   No new rounds found")
        
        return True, len(load_existing_data())
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False, 0
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def run_scraper_loop():
    print("=" * 70)
    print("🤖 LOTTERY SCRAPER - DIRECT CHROME")
    print("=" * 70)
    print("   ✓ No Selenium Grid needed")
    print("   ✓ Direct Chrome connection")
    print("=" * 70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 70)
    
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} rounds")
    
    iteration = 0
    while True:
        iteration += 1
        print(f"\n🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        success, total = scrape_rounds()
        
        if success:
            print(f"✅ Scrape successful! Total: {total}")
        else:
            print(f"⚠️ Scrape failed")
        
        print(f"\n💤 Sleeping {SCRAPE_INTERVAL_MINUTES} minutes...")
        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)

@app.route('/')
def home():
    return "<h1>Lottery Scraper</h1><p><a href='/data'>View data</a></p>"

@app.route('/data')
def get_data():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            results.sort(key=lambda x: x.get('round_number', 0), reverse=True)
            data['results'] = results
            return jsonify(data)
    return {"error": "No data"}

if __name__ == "__main__":
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    print("\nStarting web server...")
    app.run(host='0.0.0.0', port=10000)

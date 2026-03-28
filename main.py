from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver import Remote
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
BACKUP_FILENAME = "results_backup.json"
# ==========================================

app = Flask(__name__)

def sort_by_round_number(results):
    """Sort rounds by round number (highest first = newest)"""
    if not results:
        return results
    return sorted(results, key=lambda x: x.get('round_number', 0), reverse=True)

def load_existing_data():
    """Load existing data"""
    if not os.path.exists(JSON_FILENAME):
        return []
    try:
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            print(f"   📚 Loaded {len(results)} existing rounds")
            return results
    except Exception as e:
        print(f"   ⚠️ Error loading file: {e}")
        return []

def save_results_safely(new_results):
    """Save results - append new, no duplicates"""
    existing_results = load_existing_data()
    
    print(f"   Existing: {len(existing_results)} rounds")
    print(f"   New: {len(new_results)} rounds")
    
    # Merge
    all_results = []
    seen_rounds = set()
    
    for r in existing_results:
        round_num = r.get('round_number')
        if round_num not in seen_rounds:
            seen_rounds.add(round_num)
            all_results.append(r)
    
    added = 0
    for r in new_results:
        round_num = r.get('round_number')
        if round_num not in seen_rounds:
            seen_rounds.add(round_num)
            all_results.append(r)
            added += 1
            print(f"      Added new round {round_num}")
    
    if added == 0:
        return len(existing_results)
    
    # Sort by round number
    sorted_results = sort_by_round_number(all_results)
    
    # Create backup
    if os.path.exists(JSON_FILENAME):
        try:
            import shutil
            shutil.copy(JSON_FILENAME, BACKUP_FILENAME)
        except:
            pass
    
    # Save
    json_data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(sorted_results),
        "results": sorted_results,
        "order": "ROUND NUMBER DESCENDING (newest first)"
    }
    
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"   💾 Saved {len(sorted_results)} total rounds")
    return len(sorted_results)

def extract_numbers_from_balls(balls_div):
    numbers = []
    buttons = balls_div.find_elements(By.TAG_NAME, "button")
    for button in buttons:
        text = button.text.strip()
        if text and text.isdigit():
            numbers.append(text)
    return numbers

def scrape_current_rounds(driver):
    """Scrape current rounds"""
    print("\n📡 SCRAPING DATA...")
    
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
    print("✅ Results button clicked")
    time.sleep(3)
    
    round_rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
    print(f"✅ Found {len(round_rows)} rounds")
    
    existing_results = load_existing_data()
    existing_round_nums = {r.get('round_number'): r for r in existing_results}
    
    new_results = []
    
    for row in round_rows:
        try:
            title_element = row.find_element(By.CSS_SELECTOR, "div.accordion-title")
            title_text = title_element.text.strip()
            round_num = re.search(r'Round\s*(\d+)', title_text)
            round_num = int(round_num.group(1)) if round_num else None
            
            if round_num in existing_round_nums:
                continue
            
            driver.execute_script("arguments[0].scrollIntoView();", row)
            time.sleep(0.5)
            row.click()
            time.sleep(2)
            
            draw_sequences = driver.find_elements(By.CSS_SELECTOR, "div.draw-sequence")
            first_draw_numbers = []
            second_draw_numbers = []
            
            for seq in draw_sequences:
                seq_title = seq.find_element(By.CSS_SELECTOR, "div.title").text.lower()
                balls_containers = seq.find_elements(By.CSS_SELECTOR, "div.balls")
                
                if "drawn" in seq_title:
                    for container in balls_containers:
                        first_draw_numbers.extend(extract_numbers_from_balls(container))
                elif "bonus" in seq_title:
                    if balls_containers:
                        second_draw_numbers = extract_numbers_from_balls(balls_containers[0])
            
            result = {
                'round_number': round_num,
                'round_title': title_text,
                'first_draw_numbers': [int(n) for n in first_draw_numbers],
                'second_draw_numbers': [int(n) for n in second_draw_numbers],
                'timestamp': datetime.now().isoformat()
            }
            new_results.append(result)
            print(f"   ✅ Round {round_num} collected")
            
            row.click()
            time.sleep(1)
            
        except Exception as e:
            print(f"   ⚠️ Error on round: {e}")
            continue
    
    return new_results

def create_driver():
    """Create new driver with retry"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    try:
        driver = Remote(
            command_executor='http://selenium-hub:4444/wd/hub',
            options=options
        )
        return driver
    except Exception as e:
        print(f"   ⚠️ Failed to connect: {e}")
        return None

def perform_scrape():
    """Perform scrape with session recovery"""
    driver = None
    
    try:
        driver = create_driver()
        if not driver:
            print("❌ Could not connect to Selenium Grid")
            return False, 0
        
        print("✅ Connected to Selenium Grid")
        
        # Get current rounds
        current_rounds = scrape_current_rounds(driver)
        
        if current_rounds:
            print(f"\n📊 Found {len(current_rounds)} new rounds")
            total = save_results_safely(current_rounds)
            return True, total
        else:
            print(f"\n📊 No new rounds found")
            return True, len(load_existing_data())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def run_scraper_loop():
    print("=" * 70)
    print("🤖 LOTTERY SCRAPER - WITH SESSION RECOVERY")
    print("=" * 70)
    print("✓ Auto-reconnects if session fails")
    print("✓ Never loses data")
    print("=" * 70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 70)
    
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} existing rounds")
    
    iteration = 0
    consecutive_failures = 0
    
    while True:
        iteration += 1
        print(f"\n{'='*70}")
        print(f"🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        success, total = perform_scrape()
        
        if success:
            consecutive_failures = 0
            print(f"\n✅ Scrape successful! Total rounds: {total}")
        else:
            consecutive_failures += 1
            print(f"\n⚠️ Scrape failed ({consecutive_failures})")
            
            if consecutive_failures >= 5:
                print("   Too many failures, waiting 10 minutes...")
                time.sleep(600)
                consecutive_failures = 0
        
        print(f"\n💤 Sleeping for {SCRAPE_INTERVAL_MINUTES} minutes...")
        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)

@app.route('/')
def home():
    return "<h1>Lottery Scraper</h1><p><a href='/data'>View data</a></p><p><a href='/stats'>View stats</a></p>"

@app.route('/data')
def get_data():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            sorted_results = sort_by_round_number(results)
            data['results'] = sorted_results
            return jsonify(data)
    return {"error": "No data yet"}

@app.route('/stats')
def get_stats():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            sorted_results = sort_by_round_number(results)
            stats = {
                "total_rounds": len(results),
                "newest_round": sorted_results[0].get('round_number') if sorted_results else None,
                "oldest_round": sorted_results[-1].get('round_number') if sorted_results else None
            }
            return jsonify(stats)
    return {"error": "No data yet"}

if __name__ == "__main__":
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    print("\nStarting web server...")
    app.run(host='0.0.0.0', port=10000)

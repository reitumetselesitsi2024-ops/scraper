"""
ULTIMATE LOTTERY SCRAPER - SORT BY ROUND NUMBER
Rounds sorted by round number (highest first = newest)
"""

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
import shutil
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
    """
    SIMPLE FIX: Sort rounds by round number (highest first = newest)
    This works because:
    1. Website shows rounds sequentially (1,2,3... up to 289, then resets to 1)
    2. Higher round number = more recent
    3. No need for complex cycle detection
    """
    if not results:
        return results
    
    # Sort by round number descending (largest first = newest)
    sorted_results = sorted(results, key=lambda x: x.get('round_number', 0), reverse=True)
    
    return sorted_results

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
    """Save results - append new, no duplicates, sort by round number"""
    existing_results = load_existing_data()
    
    print(f"   Existing: {len(existing_results)} rounds")
    print(f"   New: {len(new_results)} rounds")
    
    # Merge: keep existing + add new (no duplicates by round_number)
    all_results = []
    seen_rounds = set()
    
    # Add existing first
    for r in existing_results:
        round_num = r.get('round_number')
        if round_num not in seen_rounds:
            seen_rounds.add(round_num)
            all_results.append(r)
    
    # Add new (skip if already exists)
    added = 0
    for r in new_results:
        round_num = r.get('round_number')
        if round_num not in seen_rounds:
            seen_rounds.add(round_num)
            all_results.append(r)
            added += 1
            print(f"      Added new round {round_num}")
    
    if added == 0:
        print("   No new rounds to add")
        return len(existing_results)
    
    # CRITICAL: Sort by round number (highest first = newest)
    sorted_results = sort_by_round_number(all_results)
    
    # Create backup before saving
    if os.path.exists(JSON_FILENAME):
        try:
            shutil.copy(JSON_FILENAME, BACKUP_FILENAME)
            print(f"   💾 Backup saved to {BACKUP_FILENAME}")
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
    
    # Show first 5 rounds (newest)
    if len(sorted_results) > 0:
        print(f"\n   📅 NEWEST ROUNDS FIRST (by round number):")
        for r in sorted_results[:5]:
            print(f"      Round {r.get('round_number')} - {r.get('timestamp')}")
    
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
    """Scrape the current visible rounds from website (last 10 rounds)"""
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
    print(f"✅ Found {len(round_rows)} rounds visible on website")
    
    current_rounds = []
    
    for row in round_rows:
        try:
            title_element = row.find_element(By.CSS_SELECTOR, "div.accordion-title")
            title_text = title_element.text.strip()
            round_num = re.search(r'Round\s*(\d+)', title_text)
            round_num = int(round_num.group(1)) if round_num else None
            
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
            current_rounds.append(result)
            print(f"   ✓ Round {round_num} collected")
            
            row.click()
            time.sleep(1)
            
        except Exception as e:
            print(f"   ⚠️ Error on round: {e}")
            continue
    
    return current_rounds

def perform_scrape():
    driver = None
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        
        driver = Remote(
            command_executor='http://selenium-hub:4444/wd/hub',
            options=options
        )
        print("✅ Connected to Selenium Grid")
        
        current_rounds = scrape_current_rounds(driver)
        
        if current_rounds:
            print(f"\n📊 Found {len(current_rounds)} current rounds")
            total = save_results_safely(current_rounds)
            return True, total
        else:
            print(f"\n⚠️ No rounds found")
            return True, len(load_existing_data())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0
    finally:
        if driver:
            driver.quit()

def run_scraper_loop():
    print("=" * 70)
    print("🤖 LOTTERY SCRAPER - SORT BY ROUND NUMBER")
    print("=" * 70)
    print("✓ NEVER loses data (appends, never replaces)")
    print("✓ Sorts by ROUND NUMBER (highest first = newest)")
    print("✓ No complex cycle detection needed")
    print("=" * 70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 70)
    
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} existing rounds")
    
    if existing:
        sorted_existing = sort_by_round_number(existing)
        print("\n   📅 NEWEST ROUNDS FIRST (by round number):")
        for r in sorted_existing[:5]:
            print(f"      Round {r.get('round_number')} - {r.get('timestamp')}")
    
    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'='*70}")
        print(f"🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        success, total = perform_scrape()
        
        if success:
            print(f"\n✅ Scrape successful! Total rounds: {total}")
        else:
            print(f"\n⚠️ Scrape failed")
        
        print(f"\n💤 Sleeping for {SCRAPE_INTERVAL_MINUTES} minutes...")
        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)

@app.route('/')
def home():
    return """
    <h1>🤖 Lottery Scraper - Sorted by Round Number</h1>
    <p>✓ NEVER loses data</p>
    <p>✓ Sorted by ROUND NUMBER (highest first = newest)</p>
    <p>✓ No complex cycle detection needed</p>
    <br>
    <p><a href='/data'>View all data (newest first)</a></p>
    <p><a href='/stats'>View statistics</a></p>
    """

@app.route('/data')
def get_data():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            # Sort by round number for display
            sorted_results = sort_by_round_number(results)
            data['results'] = sorted_results
            data['order'] = "ROUND NUMBER DESCENDING (newest first)"
            
            # Show preview
            data['preview'] = [{'round': r.get('round_number')} for r in sorted_results[:10]]
            
        return jsonify(data)
    return {"error": "No data yet"}

@app.route('/stats')
def get_stats():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if results:
                sorted_results = sort_by_round_number(results)
                stats = {
                    "total_rounds": len(results),
                    "newest_round": sorted_results[0].get('round_number') if sorted_results else None,
                    "oldest_round": sorted_results[-1].get('round_number') if sorted_results else None,
                    "order": "ROUND NUMBER DESCENDING (newest first)",
                    "backup_exists": os.path.exists(BACKUP_FILENAME)
                }
                return jsonify(stats)
    
    return {"error": "No data yet"}

if __name__ == "__main__":
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    print("\n" + "=" * 70)
    print("Starting web server...")
    print("Available endpoints:")
    print("  /data   - View all data (newest first)")
    print("  /stats  - View statistics")
    print("=" * 70)
    app.run(host='0.0.0.0', port=10000) 

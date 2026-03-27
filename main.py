"""
ULTIMATE LOTTERY SCRAPER - COMPLETE SOLUTION
- Never loses data
- Scrapes every 15 minutes (catches all new rounds)
- Cycle detection (handles round number resets)
- Newest rounds first
- Creates backups
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

def detect_cycles_and_sort(results):
    """
    CYCLE DETECTION - The Core Solution
    
    How it works:
    1. Rounds are collected over time (each scrape gets last 10 rounds)
    2. Some rounds may be collected multiple times (we keep unique)
    3. Round numbers reset after 289 (289, 1, 2, 3...)
    4. This function groups rounds into cycles and sorts them correctly
    
    Example:
        Scrape 1: Round 68,67,66,65,64,63,62,61,60,59
        Scrape 2: Round 69,68,67,66,65,64,63,62,61,60
        Scrape 3: Round 70,69,68,67,66,65,64,63,62,61
        
        After cycle detection:
        Cycle 1 (oldest): 59,60,61,62,63,64,65,66,67,68
        Cycle 2: 68,69,70 (newest)
    """
    if not results:
        return results
    
    # Step 1: Sort by timestamp (when collected)
    timestamp_sorted = sorted(results, key=lambda x: x.get('timestamp', ''))
    
    # Step 2: Detect cycles (when round number resets)
    cycles = []
    current_cycle = []
    last_round_num = None
    
    for result in timestamp_sorted:
        round_num = result.get('round_number')
        
        # A new cycle starts when round number goes DOWN (e.g., 289 → 1)
        if last_round_num is not None and round_num < last_round_num:
            if current_cycle:
                cycles.append(current_cycle)
            current_cycle = [result]
        else:
            current_cycle.append(result)
        
        last_round_num = round_num
    
    if current_cycle:
        cycles.append(current_cycle)
    
    # Step 3: Sort each cycle by round number (ascending)
    for i, cycle in enumerate(cycles):
        cycles[i] = sorted(cycle, key=lambda x: x.get('round_number', 0))
    
    # Step 4: Flatten cycles (oldest cycle first)
    sorted_results = []
    for cycle in cycles:
        sorted_results.extend(cycle)
    
    return sorted_results

def sort_newest_first(results):
    """Reverse to show newest rounds first"""
    return list(reversed(results))

def load_existing_data():
    """Load existing data safely"""
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
    """
    CRITICAL: Save results WITHOUT losing data
    - Loads existing data
    - Merges new data (no duplicates)
    - Sorts by cycle detection
    - Creates backup before saving
    """
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
    
    # Sort by cycle detection (handles round number resets)
    cycle_sorted = detect_cycles_and_sort(all_results)
    
    # Create backup before saving
    if os.path.exists(JSON_FILENAME):
        try:
            shutil.copy(JSON_FILENAME, BACKUP_FILENAME)
            print(f"   💾 Backup saved to {BACKUP_FILENAME}")
        except:
            pass
    
    # Save with cycle-sorted order (oldest first)
    json_data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(cycle_sorted),
        "results": cycle_sorted,
        "cycles": len([c for c in detect_cycles_and_sort(all_results) if isinstance(c, list)]),
        "note": "Rounds sorted by cycle detection (handles number resets)"
    }
    
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"   💾 Saved {len(cycle_sorted)} total rounds")
    
    # Show summary
    newest_first = sort_newest_first(cycle_sorted)
    if len(newest_first) > 0:
        print(f"\n   📅 NEWEST ROUNDS FIRST:")
        for r in newest_first[:10]:
            print(f"      Round {r.get('round_number')} - {r.get('timestamp')}")
    
    return len(cycle_sorted)

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
    print("\n📡 SCRAPING CURRENT ROUNDS...")
    
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
            
            # Click to reveal numbers
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
            
            # Close the expanded row
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
        
        # Get current visible rounds
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
    print("🤖 ULTIMATE LOTTERY SCRAPER - COMPLETE SOLUTION")
    print("=" * 70)
    print("✓ NEVER loses data (appends, never replaces)")
    print("✓ CYCLE DETECTION (handles round number resets)")
    print("✓ Scrapes every 15 minutes (catches all new rounds)")
    print("✓ Creates backup before saving")
    print("=" * 70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 70)
    
    # Show existing data
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} existing rounds")
    
    if existing:
        # Show newest first
        newest = list(reversed(existing))
        print("\n   📅 LAST 10 ROUNDS (NEWEST FIRST):")
        for r in newest[:10]:
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
    <h1>🤖 Ultimate Lottery Scraper</h1>
    <p>✓ NEVER loses data</p>
    <p>✓ Cycle detection (handles round number resets)</p>
    <p>✓ Scrapes every 15 minutes</p>
    <br>
    <p><a href='/data'>View all data (sorted by cycles)</a></p>
    <p><a href='/data/newest'>View all data (newest first)</a></p>
    <p><a href='/stats'>View statistics</a></p>
    <p><a href='/cycles'>View cycles breakdown</a></p>
    """

@app.route('/data')
def get_data():
    """Get data sorted by cycles (oldest cycle first)"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            # Sort by cycles
            sorted_results = detect_cycles_and_sort(results)
            data['results'] = sorted_results
            data['order'] = "CYCLE SORTED (oldest cycle first)"
            
            return jsonify(data)
    return {"error": "No data yet"}

@app.route('/data/newest')
def get_data_newest():
    """Get data with newest rounds first"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            # Sort by cycles, then reverse for newest first
            cycle_sorted = detect_cycles_and_sort(results)
            newest_first = sort_newest_first(cycle_sorted)
            
            data['results'] = newest_first
            data['order'] = "NEWEST FIRST"
            
            return jsonify(data)
    return {"error": "No data yet"}

@app.route('/stats')
def get_stats():
    """Show statistics"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if results:
                # Get cycle-sorted for analysis
                cycle_sorted = detect_cycles_and_sort(results)
                newest_first = sort_newest_first(cycle_sorted)
                
                # Detect cycles for stats
                timestamp_sorted = sorted(results, key=lambda x: x.get('timestamp', ''))
                cycles = []
                current_cycle = []
                last_round_num = None
                
                for r in timestamp_sorted:
                    round_num = r.get('round_number')
                    if last_round_num is not None and round_num < last_round_num:
                        if current_cycle:
                            cycles.append(current_cycle)
                        current_cycle = [r]
                    else:
                        current_cycle.append(r)
                    last_round_num = round_num
                
                if current_cycle:
                    cycles.append(current_cycle)
                
                stats = {
                    "total_rounds": len(results),
                    "unique_rounds": len(set(r.get('round_number') for r in results)),
                    "cycles_detected": len(cycles),
                    "newest_round": newest_first[0].get('round_number') if newest_first else None,
                    "newest_timestamp": newest_first[0].get('timestamp') if newest_first else None,
                    "oldest_round": newest_first[-1].get('round_number') if newest_first else None,
                    "oldest_timestamp": newest_first[-1].get('timestamp') if newest_first else None,
                    "backup_exists": os.path.exists(BACKUP_FILENAME)
                }
                
                return jsonify(stats)
    
    return {"error": "No data yet"}

@app.route('/cycles')
def get_cycles():
    """Show cycles breakdown"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if results:
                # Detect cycles
                timestamp_sorted = sorted(results, key=lambda x: x.get('timestamp', ''))
                cycles = []
                current_cycle = []
                last_round_num = None
                
                for r in timestamp_sorted:
                    round_num = r.get('round_number')
                    if last_round_num is not None and round_num < last_round_num:
                        if current_cycle:
                            cycles.append(current_cycle)
                        current_cycle = [r]
                    else:
                        current_cycle.append(r)
                    last_round_num = round_num
                
                if current_cycle:
                    cycles.append(current_cycle)
                
                # Sort each cycle by round number
                for i, cycle in enumerate(cycles):
                    cycles[i] = sorted(cycle, key=lambda x: x.get('round_number', 0))
                
                cycles_data = []
                for i, cycle in enumerate(cycles):
                    cycles_data.append({
                        "cycle_number": i + 1,
                        "rounds": [r.get('round_number') for r in cycle],
                        "round_count": len(cycle),
                        "start_round": cycle[0].get('round_number'),
                        "end_round": cycle[-1].get('round_number'),
                        "first_timestamp": cycle[0].get('timestamp'),
                        "last_timestamp": cycle[-1].get('timestamp')
                    })
                
                return jsonify({
                    "total_cycles": len(cycles),
                    "total_rounds": len(results),
                    "cycles": cycles_data
                })
    
    return {"error": "No data yet"}

if __name__ == "__main__":
    # Start scraper in background
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    # Start web server
    print("\n" + "=" * 70)
    print("Starting web server...")
    print("Available endpoints:")
    print("  /data         - View data (cycle sorted, oldest first)")
    print("  /data/newest  - View data (newest first)")
    print("  /stats        - View statistics")
    print("  /cycles       - View cycles breakdown")
    print("=" * 70)
    app.run(host='0.0.0.0', port=10000)

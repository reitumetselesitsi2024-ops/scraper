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

def sort_results_by_cycle_newest_first(results):
    """
    CRITICAL: Sort rounds by cycle detection with NEWEST FIRST
    - Groups rounds by timestamp order
    - Detects when round number resets (new cycle)
    - Within each cycle, sorts by round number (oldest first within cycle)
    - Finally reverses entire list to show NEWEST FIRST
    """
    if not results:
        return results
    
    # First, sort by timestamp to understand order of collection (oldest first)
    timestamp_sorted = sorted(results, key=lambda x: x.get('timestamp', ''))
    
    # Detect cycles based on round number resets
    cycles = []
    current_cycle = []
    last_round_num = None
    
    for result in timestamp_sorted:
        round_num = result.get('round_number')
        
        # If round number resets (new cycle)
        if last_round_num is not None and round_num < last_round_num:
            # Complete current cycle
            if current_cycle:
                cycles.append(current_cycle)
            current_cycle = [result]
        else:
            current_cycle.append(result)
        
        last_round_num = round_num
    
    # Add the last cycle
    if current_cycle:
        cycles.append(current_cycle)
    
    # Sort each cycle by round number (oldest to newest within cycle)
    for i, cycle in enumerate(cycles):
        cycles[i] = sorted(cycle, key=lambda x: x.get('round_number', 0))
    
    # Flatten all cycles into final sorted list (oldest first overall)
    sorted_results = []
    for cycle in cycles:
        sorted_results.extend(cycle)
    
    # REVERSE to show NEWEST FIRST
    sorted_results.reverse()
    
    return sorted_results

def load_existing_data():
    """Load existing data SAFELY - never loses data"""
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
    - Loads existing data first
    - Merges with new data
    - Removes duplicates
    - Sorts by cycle with NEWEST FIRST
    - Creates backup before saving
    """
    # Load existing data
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
    for r in new_results:
        round_num = r.get('round_number')
        if round_num not in seen_rounds:
            seen_rounds.add(round_num)
            all_results.append(r)
            print(f"      Added new round {round_num}")
    
    # Sort by cycle with NEWEST FIRST
    sorted_results = sort_results_by_cycle_newest_first(all_results)
    
    # Create backup before saving
    if os.path.exists(JSON_FILENAME):
        try:
            import shutil
            shutil.copy(JSON_FILENAME, BACKUP_FILENAME)
            print(f"   💾 Backup saved to {BACKUP_FILENAME}")
        except:
            pass
    
    # Save
    json_data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(sorted_results),
        "results": sorted_results,
        "note": "Sorted by cycle detection - NEWEST ROUNDS FIRST"
    }
    
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"   💾 Saved {len(sorted_results)} total rounds")
    
    # Show first few rounds (newest first)
    if len(sorted_results) > 0:
        print(f"\n   📅 First 5 rounds (NEWEST FIRST):")
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

def scrape_new_rounds(driver):
    """Scrape ALL rounds from website and return only NEW ones"""
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
    print(f"✅ Found {len(round_rows)} rounds on website")
    
    # Get existing rounds from file
    existing_results = load_existing_data()
    existing_round_nums = {r.get('round_number'): r for r in existing_results}
    
    new_results = []
    
    # Process all rounds from website
    for i in range(len(round_rows) - 1, -1, -1):
        rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
        current_row = rows[i]
        
        title_element = current_row.find_element(By.CSS_SELECTOR, "div.accordion-title")
        title_text = title_element.text.strip()
        round_num = re.search(r'Round\s*(\d+)', title_text)
        round_num = int(round_num.group(1)) if round_num else None
        
        # Skip if we already have this round
        if round_num in existing_round_nums:
            continue
        
        driver.execute_script("arguments[0].scrollIntoView();", current_row)
        time.sleep(0.5)
        current_row.click()
        time.sleep(2)
        
        try:
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
                'round_number': int(round_num),
                'round_title': title_text,
                'first_draw_numbers': [int(n) for n in first_draw_numbers],
                'second_draw_numbers': [int(n) for n in second_draw_numbers],
                'timestamp': datetime.now().isoformat()
            }
            new_results.append(result)
            print(f"✅ New round {round_num} collected")
            
        except Exception as e:
            print(f"❌ Error on Round {round_num}: {e}")
        
        current_row.click()
        time.sleep(1)
    
    return new_results

def perform_scrape():
    driver = None
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        
        # Connect to Railway's Selenium Hub
        driver = Remote(
            command_executor='http://selenium-hub:4444/wd/hub',
            options=options
        )
        print("✅ Connected to Selenium Grid")
        
        # Get only NEW rounds (doesn't delete old data)
        new_results = scrape_new_rounds(driver)
        
        if new_results:
            print(f"\n📊 Found {len(new_results)} new rounds to add")
            total = save_results_safely(new_results)
            return True, total
        else:
            print(f"\n📊 No new rounds found")
            return True, len(load_existing_data())
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0
    finally:
        if driver:
            driver.quit()

def run_scraper_loop():
    print("=" * 60)
    print("🤖 LOTTERY SCRAPER - SAFE VERSION")
    print("=" * 60)
    print("✓ NEVER loses data (appends, never replaces)")
    print("✓ Sorts by cycle detection")
    print("✓ NEWEST ROUNDS FIRST")
    print("✓ Creates backup before saving")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 60)
    
    # Show existing data count on startup
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} existing rounds")
    
    if existing:
        print("\n   First 5 rounds (NEWEST FIRST):")
        for r in existing[:5]:
            print(f"      Round {r.get('round_number')} - {r.get('timestamp')}")
    
    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'='*60}")
        print(f"🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
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
    <h1>🤖 Lottery Scraper - SAFE VERSION</h1>
    <p>✓ NEVER loses data (appends, never replaces)</p>
    <p>✓ Sorts by cycle detection</p>
    <p>✓ <strong>NEWEST ROUNDS FIRST</strong></p>
    <p>✓ Creates backup before saving</p>
    <br>
    <p><a href='/data'>View all data (newest first)</a></p>
    <p><a href='/stats'>View statistics</a></p>
    <p><a href='/backup'>View backup status</a></p>
    """

@app.route('/data')
def get_data():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            # Ensure newest first for display
            if results:
                # Show first 10 (newest)
                preview = results[:10] if len(results) > 10 else results
                data['preview'] = [{
                    'round': r.get('round_number'),
                    'timestamp': r.get('timestamp')
                } for r in preview]
                data['order'] = "NEWEST FIRST"
        
        return jsonify(data)
    return {"error": "No data yet"}

@app.route('/stats')
def get_stats():
    """Show statistics about the data"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if results:
                stats = {
                    "total_rounds": len(results),
                    "newest_round": results[0].get('round_number') if results else None,
                    "newest_timestamp": results[0].get('timestamp') if results else None,
                    "oldest_round": results[-1].get('round_number') if results else None,
                    "oldest_timestamp": results[-1].get('timestamp') if results else None,
                    "order": "NEWEST FIRST",
                    "backup_exists": os.path.exists(BACKUP_FILENAME)
                }
                return jsonify(stats)
    
    return {"error": "No data yet"}

@app.route('/backup')
def get_backup():
    """Check if backup exists"""
    if os.path.exists(BACKUP_FILENAME):
        try:
            with open(BACKUP_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return jsonify({
                    "backup_exists": True,
                    "backup_size": len(data.get('results', [])),
                    "note": "Backup file exists. Main data is safe."
                })
        except:
            return {"backup_exists": True, "error": "Can't read backup"}
    return {"backup_exists": False}

if __name__ == "__main__":
    # Start scraper in background
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    # Start web server
    print("\n" + "=" * 60)
    print("Starting web server...")
    print("Available endpoints:")
    print("  /data    - View all data (NEWEST FIRST)")
    print("  /stats   - View statistics")
    print("  /backup  - Check backup status")
    print("=" * 60)
    app.run(host='0.0.0.0', port=10000)

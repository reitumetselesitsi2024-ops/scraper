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
from datetime import datetime, timedelta
from flask import Flask, jsonify
import threading

# ============= CONFIGURATION =============
SCRAPE_INTERVAL_MINUTES = 15
JSON_FILENAME = "results.json"
# ==========================================

app = Flask(__name__)

def sort_results_by_cycle(results):
    """
    CRITICAL FIX: Sort rounds by cycles
    - Detects when round number resets (new cycle)
    - Within each cycle, sorts by round number
    - This puts missing rounds (like Round 2) in correct position
    """
    if not results:
        return results
    
    # First, sort by timestamp to understand order of collection
    timestamp_sorted = sorted(results, key=lambda x: x.get('timestamp', ''))
    
    # Detect cycles based on round number resets
    cycles = []
    current_cycle = []
    last_round_num = None
    
    print("   🔄 Detecting cycles from timestamp order...")
    
    for result in timestamp_sorted:
        round_num = result.get('round_number')
        
        # If this is a new cycle (round number reset to a smaller number)
        if last_round_num is not None and round_num < last_round_num:
            # Complete current cycle
            if current_cycle:
                cycles.append(current_cycle)
                print(f"      Cycle {len(cycles)}: Rounds {current_cycle[0].get('round_number')} to {current_cycle[-1].get('round_number')}")
            current_cycle = [result]
        else:
            current_cycle.append(result)
        
        last_round_num = round_num
    
    # Add the last cycle
    if current_cycle:
        cycles.append(current_cycle)
        print(f"      Cycle {len(cycles)}: Rounds {current_cycle[0].get('round_number')} to {current_cycle[-1].get('round_number')}")
    
    # Sort each cycle by round number
    for i, cycle in enumerate(cycles):
        cycles[i] = sorted(cycle, key=lambda x: x.get('round_number', 0))
        print(f"      Cycle {i+1} sorted by round number")
    
    # Flatten all cycles into final sorted list
    sorted_results = []
    for cycle in cycles:
        sorted_results.extend(cycle)
    
    return sorted_results

def fix_existing_data():
    """Fix any existing data that is out of order"""
    print("\n🔧 Checking and fixing existing data...")
    
    if not os.path.exists(JSON_FILENAME):
        print("   No existing data found.")
        return []
    
    try:
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if not results:
                print("   No results found.")
                return []
            
            print(f"   Loaded {len(results)} rounds.")
            
            # Apply cycle-based sorting
            sorted_results = sort_results_by_cycle(results)
            
            # Check if sorting was needed
            if sorted_results != results:
                print("   ⚠️ Data was out of order. Fixing...")
                # Save the fixed data
                json_data = {
                    "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_rows": len(sorted_results),
                    "results": sorted_results,
                    "note": "Sorted by cycles (detects round resets)"
                }
                with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                print(f"   ✅ Fixed data saved. Now {len(sorted_results)} rounds in correct order.")
                
                # Show the sequence
                print("\n   📅 Corrected round sequence:")
                for i, r in enumerate(sorted_results[-10:] if len(sorted_results) > 10 else sorted_results):
                    print(f"      Position {i+1}: Round {r.get('round_number')} - {r.get('timestamp')}")
            else:
                print("   ✅ Data is already in correct order.")
            
            return sorted_results
            
    except Exception as e:
        print(f"   ⚠️ Error fixing data: {e}")
        return []

def extract_numbers_from_balls(balls_div):
    numbers = []
    buttons = balls_div.find_elements(By.TAG_NAME, "button")
    for button in buttons:
        text = button.text.strip()
        if text and text.isdigit():
            numbers.append(text)
    return numbers

def load_existing_data():
    """Load data with cycle-based sorting"""
    if os.path.exists(JSON_FILENAME):
        try:
            with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                results = data.get('results', [])
                
                # Always sort by cycle when loading
                sorted_results = sort_results_by_cycle(results)
                
                return sorted_results
        except Exception as e:
            print(f"⚠️ Error loading file: {e}")
    return []

def save_results(results):
    """Save results with cycle-based sorting"""
    # Sort by cycle before saving
    sorted_results = sort_results_by_cycle(results)
    
    json_data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(sorted_results),
        "results": sorted_results,
        "note": "Sorted by cycles - missing rounds are placed correctly"
    }
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    return len(sorted_results)

def scrape_data(driver):
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
    
    existing_results = load_existing_data()
    existing_round_nums = {r.get('round_number'): r for r in existing_results}
    new_results = []
    
    # Collect all new rounds (by round number)
    for i in range(len(round_rows) - 1, -1, -1):
        rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
        current_row = rows[i]
        
        title_element = current_row.find_element(By.CSS_SELECTOR, "div.accordion-title")
        title_text = title_element.text.strip()
        round_num = re.search(r'Round\s*(\d+)', title_text)
        round_num = int(round_num.group(1)) if round_num else None
        
        # Check if we already have this round number in any cycle
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
            print(f"✅ Round {round_num} collected")
            
        except Exception as e:
            print(f"❌ Error on Round {round_num}: {e}")
        
        current_row.click()
        time.sleep(1)
    
    # Combine old and new results
    all_results = existing_results + new_results
    
    # CRITICAL: Sort everything by cycle (detects resets, places missing rounds correctly)
    all_results = sort_results_by_cycle(all_results)
    
    total = save_results(all_results)
    
    print(f"\n💾 Total rounds: {total}")
    if new_results:
        print(f"   New rounds added: {len(new_results)}")
        
        # Show where the new rounds were placed
        print("\n   📅 Updated round sequence (last 15 positions):")
        for i, r in enumerate(all_results[-15:] if len(all_results) > 15 else all_results):
            print(f"      Position {len(all_results)-15+i+1}: Round {r.get('round_number')} - {r.get('timestamp')}")
    
    return all_results

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
        
        results = scrape_data(driver)
        return True, len(results)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0
    finally:
        if driver:
            driver.quit()

def run_scraper_loop():
    print("=" * 60)
    print("🤖 LOTTERY SCRAPER - CYCLE SORTING FIX")
    print("=" * 60)
    print("✓ Rounds sorted by CYCLE (detects when numbers reset)")
    print("✓ Missing rounds (like Round 2) go in correct position")
    print("✓ Works with existing data and new data")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 60)
    
    # Fix existing data on startup
    fix_existing_data()
    
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
    <h1>🤖 Lottery Scraper - Cycle Sorting</h1>
    <p>Rounds are sorted by <strong>CYCLES</strong> (detects when round numbers reset)</p>
    <p>Missing rounds (like Round 2 collected later) are placed in correct position</p>
    <p>This works with both existing and new data</p>
    <br>
    <p>📊 <a href='/data'>View all data</a></p>
    <p>📈 <a href='/stats'>View statistics</a></p>
    <p>🔄 <a href='/cycle-view'>View by cycle</a></p>
    """

@app.route('/data')
def get_data():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
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
                # Get sorted by cycle
                sorted_results = sort_results_by_cycle(results)
                
                # Detect cycles for display
                cycles = []
                current_cycle = []
                last_round_num = None
                
                for r in sorted_results:
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
                    "total_rounds": len(sorted_results),
                    "cycles_detected": len(cycles),
                    "cycles": []
                }
                
                for i, cycle in enumerate(cycles):
                    stats["cycles"].append({
                        "cycle_number": i + 1,
                        "rounds": [r.get('round_number') for r in cycle],
                        "start_round": cycle[0].get('round_number'),
                        "end_round": cycle[-1].get('round_number'),
                        "round_count": len(cycle),
                        "first_timestamp": cycle[0].get('timestamp'),
                        "last_timestamp": cycle[-1].get('timestamp')
                    })
                
                stats["note"] = "Rounds are sorted by cycle - missing rounds are placed correctly"
                
                return jsonify(stats)
    
    return {"error": "No data yet"}

@app.route('/cycle-view')
def cycle_view():
    """Show rounds grouped by cycle"""
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            
            if results:
                sorted_results = sort_results_by_cycle(results)
                
                # Group by cycle
                cycles = []
                current_cycle = []
                last_round_num = None
                
                for r in sorted_results:
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
                
                # Build HTML response
                html = "<html><body>"
                html += "<h1>Lottery Rounds by Cycle</h1>"
                html += f"<p>Total cycles: {len(cycles)}</p>"
                html += f"<p>Total rounds: {len(sorted_results)}</p>"
                html += "<hr>"
                
                for i, cycle in enumerate(cycles):
                    html += f"<h2>Cycle {i+1}</h2>"
                    html += f"<p>Rounds: {[r.get('round_number') for r in cycle]}</p>"
                    html += f"<p>Count: {len(cycle)}</p>"
                    html += f"<p>Time range: {cycle[0].get('timestamp')} to {cycle[-1].get('timestamp')}</p>"
                    html += "<hr>"
                
                html += "</body></html>"
                return html
    
    return "<h1>No data yet</h1>"

if __name__ == "__main__":
    # Start scraper in background
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    # Start web server
    print("\n" + "=" * 60)
    print("Starting web server...")
    print("Available endpoints:")
    print("  /data        - View all data")
    print("  /stats       - View statistics (cycles detected)")
    print("  /cycle-view  - View rounds grouped by cycle")
    print("=" * 60)
    app.run(host='0.0.0.0', port=10000)

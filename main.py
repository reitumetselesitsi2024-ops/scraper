from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime
from flask import Flask, jsonify
import threading

# ============= CONFIGURATION =============
SCRAPE_INTERVAL_MINUTES = 27
JSON_FILENAME = "results.json"
MAX_CONSECUTIVE_FAILURES = 3
# ==========================================

app = Flask(__name__)

def install_chrome():
    """Install Chrome and ChromeDriver"""
    print("   📦 Installing Chrome...")
    try:
        subprocess.run(['apt-get', 'update', '-qq'], check=False, capture_output=True)
        subprocess.run(['apt-get', 'install', '-y', '-qq', 'wget', 'unzip', 'curl'], check=False, capture_output=True)
        
        # Install Chrome
        subprocess.run(['wget', '-q', 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb'], check=False, capture_output=True)
        subprocess.run(['dpkg', '-i', 'google-chrome-stable_current_amd64.deb'], check=False, capture_output=True)
        subprocess.run(['apt-get', 'install', '-y', '-f', '-qq'], check=False, capture_output=True)
        
        # Install matching ChromeDriver
        subprocess.run(['wget', '-q', 'https://storage.googleapis.com/chrome-for-testing-public/146.0.7680.165/linux64/chromedriver-linux64.zip'], check=False, capture_output=True)
        subprocess.run(['unzip', '-q', '-o', 'chromedriver-linux64.zip'], check=False, capture_output=True)
        subprocess.run(['mv', 'chromedriver-linux64/chromedriver', '/usr/local/bin/'], check=False, capture_output=True)
        subprocess.run(['chmod', '+x', '/usr/local/bin/chromedriver'], check=False, capture_output=True)
        
        # Create cache directory
        subprocess.run(['mkdir', '-p', '/.cache/selenium'], check=False, capture_output=True)
        subprocess.run(['chmod', '777', '/.cache/selenium'], check=False, capture_output=True)
        
        print("   ✅ Chrome and ChromeDriver installed")
        return True
    except Exception as e:
        print(f"   ⚠️ Chrome install error: {e}")
        return False

def create_driver():
    """Create a fresh Chrome driver with unique temp directory"""
    try:
        # Create unique temp directory for this instance
        unique_id = uuid.uuid4().hex[:8]
        user_data_dir = tempfile.mkdtemp(prefix=f'chrome-{unique_id}-')
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument(f'--user-data-dir={user_data_dir}')
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        return driver
    except Exception as e:
        print(f"   ❌ Failed to create driver: {e}")
        return None

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
    
    # Merge - no duplicates
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
            print(f"      Added new round {num}")
    
    # Sort by round number (newest first)
    all_results.sort(key=lambda x: x.get('round_number', 0), reverse=True)
    
    # Create backup
    if os.path.exists(JSON_FILENAME):
        try:
            import shutil
            shutil.copy(JSON_FILENAME, f"{JSON_FILENAME}.backup")
        except:
            pass
    
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

def scrape_rounds(driver):
    """Scrape current rounds using the provided driver"""
    try:
        driver.get('https://www.simacombet.com/luckysix')
        driver.set_page_load_timeout(30)
        time.sleep(3)
        
        iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "PluginLuckySix"))
        )
        driver.switch_to.frame(iframe)
        
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Results')]"))
        )
        driver.execute_script("arguments[0].click();", button)
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
        
        return new_rounds
        
    except Exception as e:
        print(f"   ❌ Scrape error: {e}")
        return None

def run_scraper_loop():
    print("=" * 70)
    print("🤖 LOTTERY SCRAPER - AUTO-RECOVERY VERSION")
    print("=" * 70)
    print("   ✓ Auto-recovery on failures")
    print("   ✓ Fresh Chrome on each recovery")
    print("   ✓ No data loss")
    print("=" * 70)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 70)
    
    # Install Chrome on first run
    install_chrome()
    
    existing = load_existing_data()
    print(f"\n📊 Starting with {len(existing)} rounds")
    
    iteration = 0
    consecutive_failures = 0
    driver = None
    
    while True:
        iteration += 1
        print(f"\n{'='*70}")
        print(f"🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")
        
        # Create driver if needed
        if driver is None:
            print("   Creating new Chrome driver...")
            driver = create_driver()
            if driver is None:
                print("   ❌ Failed to create driver")
                consecutive_failures += 1
                time.sleep(60)
                continue
        
        try:
            # Scrape rounds
            new_rounds = scrape_rounds(driver)
            
            if new_rounds is not None:
                if new_rounds:
                    total = save_results(new_rounds)
                    print(f"   💾 Saved {len(new_rounds)} new rounds. Total: {total}")
                    consecutive_failures = 0
                else:
                    print("   No new rounds found")
                    consecutive_failures = 0
                
                print(f"✅ Scrape successful! Total rounds: {len(load_existing_data())}")
                
            else:
                # Scrape failed
                consecutive_failures += 1
                print(f"⚠️ Scrape failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")
                
                # Close old driver
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print("   Too many failures, waiting 5 minutes before retry...")
                    time.sleep(300)
                    consecutive_failures = 0
                
        except Exception as e:
            consecutive_failures += 1
            print(f"❌ Error: {e}")
            
            # Close old driver
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None
            
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("   Too many failures, waiting 5 minutes...")
                time.sleep(300)
                consecutive_failures = 0
        
        # Sleep between iterations
        print(f"\n💤 Sleeping for {SCRAPE_INTERVAL_MINUTES} minutes...")
        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)

@app.route('/')
def home():
    return """
    <h1>🤖 Lottery Scraper - Auto-Recovery</h1>
    <p>✓ Auto-recovery on failures</p>
    <p>✓ Fresh Chrome on each recovery</p>
    <p>✓ No data loss</p>
    <br>
    <p><a href='/data'>View all data</a></p>
    <p><a href='/stats'>View statistics</a></p>
    """

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

@app.route('/stats')
def get_stats():
    if os.path.exists(JSON_FILENAME):
        with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            stats = {
                "total_rounds": len(results),
                "newest_round": results[0].get('round_number') if results else None,
                "oldest_round": results[-1].get('round_number') if results else None,
                "backup_exists": os.path.exists(f"{JSON_FILENAME}.backup")
            }
            return jsonify(stats)
    return {"error": "No data"}

if __name__ == "__main__":
    thread = threading.Thread(target=run_scraper_loop)
    thread.daemon = True
    thread.start()
    
    print("\nStarting web server...")
    app.run(host='0.0.0.0', port=10000)

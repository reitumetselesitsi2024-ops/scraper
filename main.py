from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import json
import os
import re
from datetime import datetime, timedelta
from collections import Counter
import traceback

# ============= CONFIGURATION =============
SCRAPE_INTERVAL_MINUTES = 15
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30
MAX_CONSECUTIVE_FAILURES = 5
JSON_FILENAME = "results.json"
# ==========================================

def extract_numbers_from_balls(balls_div):
    numbers = []
    buttons = balls_div.find_elements(By.TAG_NAME, "button")
    for button in buttons:
        text = button.text.strip()
        if text and text.isdigit():
            numbers.append(text)
    return numbers

def load_existing_data():
    if os.path.exists(JSON_FILENAME):
        try:
            with open(JSON_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('results', [])
        except Exception as e:
            print(f"⚠️ Error loading file: {e}")
    return []

def save_results(results):
    results.sort(key=lambda x: x.get('round_number', 0), reverse=True)
    json_data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(results),
        "results": results
    }
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved {len(results)} total rounds")
    return len(results)

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
    print(f"✅ Found {len(round_rows)} rounds")
    
    existing_results = load_existing_data()
    existing_round_nums = {r.get('round_number'): r for r in existing_results}
    new_results = []
    
    for i in range(len(round_rows) - 1, -1, -1):
        rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
        current_row = rows[i]
        
        title_element = current_row.find_element(By.CSS_SELECTOR, "div.accordion-title")
        title_text = title_element.text.strip()
        round_num = re.search(r'Round\s*(\d+)', title_text)
        round_num = int(round_num.group(1)) if round_num else None
        
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
            print(f"✅ Round {round_num} saved")
            
        except Exception as e:
            print(f"❌ Error on Round {round_num}: {e}")
        
        current_row.click()
        time.sleep(1)
    
    all_results = new_results + existing_results
    save_results(all_results)
    
    if new_results:
        print(f"   New rounds added: {len(new_results)}")
    
    return all_results

def perform_scrape():
    driver = None
    
    try:
        # Force webdriver to use system chromedriver
        import subprocess
        result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
        chromedriver_path = result.stdout.strip()
        print(f"🔍 Found chromedriver at: {chromedriver_path}")
        
        result = subprocess.run(['which', 'chromium'], capture_output=True, text=True)
        chrome_path = result.stdout.strip()
        print(f"🔍 Found chromium at: {chrome_path}")
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        options.binary_location = chrome_path
        
        # Create service with explicit path
        from selenium.webdriver.chrome.service import Service
        service = Service(executable_path=chromedriver_path)
        
        # Disable Selenium Manager entirely
        import os
        os.environ['SELENIUM_DRIVER_MANAGER'] = '0'
        
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Chrome ready")
        
        results = scrape_data(driver)
        return True, len(results)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return False, 0
        
    finally:
        if driver:
            driver.quit()
def run_scraping_loop():
    consecutive_failures = 0
    iteration = 0
    
    print("=" * 80)
    print("🚀 RAILWAY LOTTERY SCRAPER")
    print("=" * 80)
    print(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️  Scrape interval: {SCRAPE_INTERVAL_MINUTES} minutes")
    print("=" * 80)
    
    while True:
        iteration += 1
        print(f"\n{'=' * 80}")
        print(f"🔄 ITERATION #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 80}")
        
        success = False
        total_rounds = 0
        
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n📡 Attempt {attempt}/{MAX_RETRIES}")
            
            try:
                success, total_rounds = perform_scrape()
                
                if success:
                    print(f"\n✅ Scrape successful! Total rounds: {total_rounds}")
                    consecutive_failures = 0
                    break
                else:
                    print(f"\n⚠️ Attempt {attempt} failed")
                    if attempt < MAX_RETRIES:
                        print(f"⏱️  Retrying in {RETRY_DELAY_SECONDS} seconds...")
                        time.sleep(RETRY_DELAY_SECONDS)
                        
            except Exception as e:
                print(f"\n❌ Error: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS)
        
        if not success:
            consecutive_failures += 1
            print(f"\n⚠️ Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}")
            
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"\n❌ Too many consecutive failures. Stopping.")
                break
        else:
            next_run = datetime.now() + timedelta(minutes=SCRAPE_INTERVAL_MINUTES)
            print(f"\n⏰ Next scrape: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"💤 Sleeping for {SCRAPE_INTERVAL_MINUTES} minutes...")
            time.sleep(SCRAPE_INTERVAL_MINUTES * 60)

def main():
    try:
        run_scraping_loop()
    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopped by user")

if __name__ == "__main__":
    main()

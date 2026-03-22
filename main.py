from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import re
from datetime import datetime

JSON_FILENAME = "results.json"

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
        except:
            pass
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
    print(f"💾 Saved {len(results)} rounds")
    return len(results)

def main():
    print("🚀 Starting scraper...")
    
    # Simple Chrome setup - no extra options
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=options)
        print("✅ Chrome started")
        
        driver.get('https://www.simacombet.com/luckysix')
        time.sleep(3)
        print("✅ Page loaded")
        
        # Switch to iframe
        iframe = driver.find_element(By.ID, "PluginLuckySix")
        driver.switch_to.frame(iframe)
        
        # Click Results button
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Results')]"))
        )
        button.click()
        print("✅ Results clicked")
        time.sleep(3)
        
        # Find all rounds
        round_rows = driver.find_elements(By.CSS_SELECTOR, "div.round-row")
        print(f"✅ Found {len(round_rows)} rounds")
        
        # Load existing data
        existing = load_existing_data()
        existing_rounds = {r.get('round_number'): r for r in existing}
        new_results = []
        
        # Process each round
        for i, row in enumerate(round_rows):
            try:
                # Get round number from title
                title = row.find_element(By.CSS_SELECTOR, "div.accordion-title").text
                round_num = re.search(r'Round\s*(\d+)', title)
                round_num = int(round_num.group(1)) if round_num else None
                
                if round_num in existing_rounds:
                    continue
                
                # Click to open
                row.click()
                time.sleep(2)
                
                # Extract numbers
                draw_sequences = driver.find_elements(By.CSS_SELECTOR, "div.draw-sequence")
                first_draw = []
                
                for seq in draw_sequences:
                    seq_title = seq.find_element(By.CSS_SELECTOR, "div.title").text.lower()
                    if "drawn" in seq_title:
                        balls = seq.find_elements(By.CSS_SELECTOR, "div.balls")
                        for ball in balls:
                            first_draw.extend(extract_numbers_from_balls(ball))
                
                result = {
                    'round_number': round_num,
                    'round_title': title,
                    'first_draw_numbers': [int(n) for n in first_draw],
                    'second_draw_numbers': [],
                    'timestamp': datetime.now().isoformat()
                }
                new_results.append(result)
                print(f"✅ Round {round_num} saved")
                
                # Close the row
                row.click()
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Error on round: {e}")
                continue
        
        # Save all data
        if new_results:
            all_results = new_results + existing
            save_results(all_results)
            print(f"✅ Added {len(new_results)} new rounds")
        else:
            print("📭 No new rounds")
        
        driver.quit()
        print("✅ Done")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()

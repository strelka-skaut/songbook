#!/usr/bin/env python3
"""
Extract chords from pisnicky-akordy.cz pages listed in song_metadata_with_url.json.

Behavior:
- Loads song metadata JSON with schema:
  [{"title": "...", "artist": "...", "release_year": "...", "url": "https://.../song-slug"}, ...]
- Opens each song URL in a visible Chrome browser using Selenium.
- Waits up to 3 seconds for page load, then cancels loading.
- Clicks the cookie consent button automatically if found.
- If there is no <ul id="trans" class="pagination"> element, extracts chords immediately.
- Otherwise, waits for user manual transposition and confirmation before extraction.
- Adds 'chords' key to each song and exports to song_with_chords.json.
"""

import json
import os
import time
from typing import List, Dict, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager

INPUT_JSON = "song_metadata_with_url.json"
OUTPUT_JSON = "song_with_chords.json"
PAGE_LOAD_TIMEOUT = 3  # seconds before canceling page load


# ---------- File I/O ----------
def load_metadata(path: str) -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found in {os.getcwd()}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list of song objects.")
    return data


def save_output(path: str, data: List[Dict]):
    breakpoint()
    with open(path, "r", encoding="utf-8") as input_file:
        existing_data = json.loads(input_file.read())
    existing_data.extend(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)


# ---------- Browser setup ----------
def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--start-maximized")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


# ---------- Page helpers ----------
def click_cookie_consent(driver: webdriver.Chrome):
    """Click the 'Rozumím a přijímám' cookie consent button if present."""
    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "didomi-notice-agree-button"))
        )
        button = driver.find_element(By.ID, "didomi-notice-agree-button")
        driver.execute_script("arguments[0].click();", button)
        print("✅ Clicked cookie consent button.")
        time.sleep(0.5)
    except TimeoutException:
        print("No cookie consent button found.")
    except Exception as e:
        print("Error clicking cookie consent button:", e)


def page_has_transposition(driver: webdriver.Chrome) -> bool:
    """Check if <ul id='trans' class='pagination'> exists."""
    try:
        driver.find_element(By.XPATH, "//ul[@id='trans' and contains(@class, 'pagination')]")
        return True
    except Exception:
        return False


def find_best_pre_text(driver: webdriver.Chrome) -> Optional[str]:
    """Return the textContent of the <pre> element with the longest content."""
    pres = driver.find_elements(By.TAG_NAME, "pre")
    best_text = None
    best_len = -1
    for el in pres:
        try:
            txt = el.get_attribute("textContent") or ""
            if len(txt) > best_len:
                best_len = len(txt)
                best_text = txt
        except WebDriverException:
            continue
    return best_text


def fallback_page_text(driver: webdriver.Chrome) -> str:
    """Fallback to body text if no <pre> found."""
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        return body.get_attribute("innerText") or ""
    except Exception:
        return ""


# ---------- Core extraction ----------
def extract_chords_for_song(driver: webdriver.Chrome, url: str) -> str:
    print(f"\nOpening: {url}")
    try:
        driver.get(url)
    except TimeoutException:
        print(f"⚠️ Page load timeout after {PAGE_LOAD_TIMEOUT}s — proceeding anyway.")
        # Stop page load manually
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass

    # Click cookie consent if appears
    click_cookie_consent(driver)

    has_trans = page_has_transposition(driver)
    if not has_trans:
        print("🎵 No transposition controls found — extracting chords immediately.")
        pre_text = find_best_pre_text(driver)
        if pre_text:
            print(f"✅ Extracted <pre> text ({len(pre_text)} chars).")
            return pre_text
        else:
            print("No <pre> found, falling back to full page text.")
            return fallback_page_text(driver)

    print("Transposition controls detected — please choose your transposition manually.")
    input("When ready, press Enter to extract chords...")

    pre_text = find_best_pre_text(driver)
    if pre_text:
        print(f"Extracted <pre> text ({len(pre_text)} chars).")
        return pre_text
    else:
        print("No <pre> found, falling back to full page text.")
        return fallback_page_text(driver)


# ---------- Main ----------
def main():
    print("Loading input JSON:", INPUT_JSON)
    songs = load_metadata(INPUT_JSON)

    processed = {}
    driver = None
    try:
        driver = create_driver()
    except Exception as e:
        print("Could not start Chrome:", e)
        return

    results = []
    try:
        for idx, song in enumerate(songs, start=1):
            print(f"\n--- ({idx}/{len(songs)}) {song.get('title', 'Unknown')} ---")
            url = song.get("url")
            if not url:
                print("No URL found; skipping.")
                results.append({**song, "chords": ""})
                continue

            if url in processed:
                print("Reusing previously extracted chords.")
                cached = processed[url]
                results.append({**song, "chords": cached.get("chords", "")})
                continue

            try:
                chords = extract_chords_for_song(driver, url)
                print(chords)
            except Exception as e:
                print("Error extracting chords:", e)
                chords = ""

            results.append({**song, "chords": chords})
            time.sleep(0.3)

    finally:
        print("\nClosing browser...")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    print(f"\nSaving results to {OUTPUT_JSON} ...")
    save_output(OUTPUT_JSON, results)
    print("Done. Saved to", OUTPUT_JSON)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
import json
import requests
import tempfile
import subprocess
import os
import sys
import logging
from bs4 import BeautifulSoup
from typing import List, Optional, Dict

# Selenium optional
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.common.exceptions import TimeoutException
    SELENIUM_AVAILABLE = True
except Exception:
    SELENIUM_AVAILABLE = False


logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

METADATA_FILE = 'song_metadata_with_url.json'
OUTPUT_FILE = 'song_with_chords.json'
TMP_DIR = '/tmp'


########################################
###   METADATA EDITOR (unchanged)   ###
########################################
def pretty_json_to_tempfile(data: dict) -> str:
    fd, path = tempfile.mkstemp(prefix='song_preview_', suffix='.json', dir=TMP_DIR)
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def edit_with_vim_or_skip(song: dict) -> Optional[dict]:
    """
    Opens metadata. 
    If empty → skip song.
    If == 'exit' → tell caller to abort entire run.
    Else parse updated JSON.
    """
    path = pretty_json_to_tempfile(song)

    try:
        subprocess.run(['vim', path])
    except FileNotFoundError:
        raise RuntimeError("vim not found")

    txt = ""
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read().strip()

    ### NEW ###
    # If user wants to abort whole run
    if txt == "exit":
        return "__EXIT__"

    if not txt:
        # treat empty as skip
        return None

    try:
        updated = json.loads(txt)
        return updated
    except:
        logging.error("Invalid edited metadata JSON → skipping song")
        return None


########################################
###   FETCHING + TRANSPOSE LOGIC     ###
########################################
def fetch_page_html(url: str, use_selenium: bool = False) -> str:
    if use_selenium:
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium requested but unavailable.")

        chrome_opts = ChromeOptions()
        chrome_opts.add_argument('--no-sandbox')
        chrome_opts.add_argument('--disable-dev-shm-usage')
        chrome_opts.headless = True

        driver = webdriver.Chrome(options=chrome_opts)
        driver.set_page_load_timeout(5)   ### NEW ###

        try:
            try:
                driver.get(url)
                driver.implicitly_wait(3)
            except TimeoutException:
                logging.warning("Page load timeout → using partial HTML.")
            return driver.page_source
        finally:
            driver.quit()

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text


def detect_transpositions_from_soup(soup: BeautifulSoup) -> (List[str], Optional[str]):
    trans_ul = soup.find("ul", id="trans")
    if not trans_ul:
        return [], None

    keys = []
    active = None
    for li in trans_ul.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        txt = a.get_text(strip=True)
        keys.append(txt)
        if 'active' in li.get('class', []):
            active = txt
    return keys, active


def click_transpose_via_selenium(url: str, select_key: str) -> str:
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium not available")

    chrome_opts = ChromeOptions()
    chrome_opts.add_argument('--no-sandbox')
    chrome_opts.add_argument('--disable-dev-shm-usage')
    chrome_opts.headless = True

    driver = webdriver.Chrome(options=chrome_opts)
    driver.set_page_load_timeout(5)   ### NEW ###

    try:
        try:
            driver.get(url)
            driver.implicitly_wait(3)
        except TimeoutException:
            logging.warning("Initial load timeout → continuing")

        try:
            ul = driver.find_element(By.ID, "trans")
            items = ul.find_elements(By.TAG_NAME, "li")
            clicked = False

            for li in items:
                try:
                    a = li.find_element(By.TAG_NAME, "a")
                    txt = a.text.strip()
                    if txt == select_key:
                        a.click()
                        clicked = True
                        break
                except:
                    pass

            if not clicked:
                logging.warning("Requested transpose %s not found", select_key)

        except:
            logging.warning("Could not find trans UL")

        driver.implicitly_wait(2)
        return driver.page_source

    except TimeoutException:
        logging.warning("Timeout after clicking → partial content")
        return driver.page_source

    finally:
        driver.quit()


########################################
###       PREVIEW + EXTRACTION       ###
########################################
def extract_chords_from_soup(soup: BeautifulSoup) -> List[str]:
    selectors = [
        "pre",
        "div.chords", "div.song-chords", "div#chords", "div#songtext",
        "div.songtext", "div.text", "div#song",
        "table.chords", "div.note", "article", "div[id*='song']"
    ]

    out = []
    for sel in selectors:
        for node in soup.select(sel):
            t = node.get_text("\n", strip=True)
            if t and len(t) > 10:
                out.append(t)

    if not out:
        divs = soup.find_all("div")
        best = ""
        for d in divs:
            t = d.get_text("\n", strip=True)
            if len(t) > len(best):
                best = t
        if len(best) > 50:
            out.append(best)

    return out


def preview_first_lines_from_soup(soup: BeautifulSoup, n: int = 10) -> List[str]:
    text = soup.get_text("\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[:n]


########################################
### NEW ###
### TRANSPOSITION SELECTION VIA VIM ###
########################################
def select_transposition_via_vim(available: List[str], active: Optional[str], preview_lines: List[str]) -> Optional[str]:
    """
    Creates a temp file where user selects transposition by placing '>' before one key.
    preview text is appended below.
    """

    fd, path = tempfile.mkstemp(prefix='transpose_', suffix='.txt', dir=TMP_DIR)
    os.close(fd)

    # Build initial text
    lines = ["Select transposition:"]
    for key in available:
        if key == active:
            lines.append(f">{key}")
        else:
            lines.append(key)
    lines.append("") 
    lines.append("------ PREVIEW ------")
    for line in preview_lines:
        lines.append(line)
    lines.append("---------------------")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # edit
    subprocess.run(["vim", path])

    # read
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().splitlines()

    # first section is selection
    selected = active
    for line in content:
        l = line.strip()
        if l.startswith(">"):
            sel = l[1:].strip()
            if sel:
                selected = sel
                break

    return selected


########################################
### PROCESS SINGLE SONG             ###
########################################
def process_song(song: Dict) -> Optional[Dict]:
    if 'url' not in song:
        logging.error("Song has no URL → skipping")
        return None

    updated_song = edit_with_vim_or_skip(song)

    ### NEW ###
    if updated_song == "__EXIT__":
        return "__EXIT__"

    if not updated_song:
        return None

    url = updated_song['url']
    html = fetch_page_html(url, use_selenium=False)
    soup = BeautifulSoup(html, "html.parser")

    available, active = detect_transpositions_from_soup(soup)
    preview = preview_first_lines_from_soup(soup)

    # choose transpose
    if available:
        chosen = select_transposition_via_vim(available, active, preview)
    else:
        chosen = active

    final_html = html

    if available and chosen and chosen != active:
        if not SELENIUM_AVAILABLE:
            logging.warning("Selenium unavailable → cannot transpose; using default")
        else:
            final_html = click_transpose_via_selenium(url, chosen)

    final_soup = BeautifulSoup(final_html, "html.parser")
    blocks = extract_chords_from_soup(final_soup)

    updated_song['chords'] = blocks
    updated_song['chosen_transpose'] = chosen
    return updated_song


########################################
### MAIN LOOP                       ###
########################################
def main():
    if not os.path.exists(METADATA_FILE):
        logging.error("Missing metadata file")
        sys.exit(1)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        songs = json.load(f)

    output = []

    for song in songs:
        logging.info("Processing: %s", song.get("title", song.get("url")))
        try:
            res = process_song(song)

            if res == "__EXIT__":      ### NEW ###
                logging.info("Exit requested. Saving progress and stopping.")
                break

            if res:
                output.append(res)

        except Exception as e:
            logging.exception("Error processing song")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logging.info("Done; wrote %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()


"""
pisnicky_batch_search_single_page.py

Programmatically search https://pisnicky-akordy.cz/ using Selenium.

Features:
- Loads homepage once.
- Searches a hardcoded list of terms sequentially in the same page.
- For each term, picks the first suggestion URL (or None).
- Prints final mapping.
"""

import time
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

import requests
import re
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Optional, List
import json

# --- Configuration ---
SEARCH_INPUT_SELECTOR = "input.ais-SearchBox-input"
SUGGESTIONS_CONTAINER_SELECTORS = [
    "div.ais-Hits", "ul.ais-Hits-list", "div.ais-Hits-list"
]
SUGGESTION_ITEM_SELECTORS = [
    "div.ais-Hits-item", "li.ais-Hits-item", "a.ais-Hits-item"
]
TYPING_DELAY = 0.05  # seconds per keystroke
PAGE_LOAD_TIMEOUT = 7  # max seconds to wait for homepage


# --- Functions ---

def create_driver(headless: bool = True):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_window_size(1200, 900)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver

def search_top_result(driver, query: str) -> Optional[str]:
    """
    Search for the query in the already loaded page and return the URL of the first suggestion.
    Returns None if no suggestions are found.
    """
    search_input = None
    start_time = time.time()
    max_wait = 3
    while time.time() - start_time < max_wait:
        try:
            search_input = driver.find_element(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
            if search_input:
                break
        except:
            time.sleep(0.2)
    if not search_input:
        print(f"Search input not found for query '{query}'. Skipping.")
        return None

    # --- Clear the input robustly ---
    search_input.click()
    search_input.clear()
    # Select all + backspace to ensure field is empty
    search_input.send_keys(Keys.COMMAND + "a")
    search_input.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)

    # Type the query
    for ch in query:
        search_input.send_keys(ch)
        time.sleep(TYPING_DELAY)
    time.sleep(1)
    # Try multiple possible containers
    container = None
    for sel in SUGGESTIONS_CONTAINER_SELECTORS:
        try:
            container = driver.find_element(By.CSS_SELECTOR, sel)
            if container:
                break
        except:
            continue

    # Collect suggestion items
    items = []
    if container:
        for sel in SUGGESTION_ITEM_SELECTORS:
            try:
                items = container.find_elements(By.CSS_SELECTOR, sel)
                if items:
                    break
            except:
                continue
    else:
        # fallback: search globally
        for sel in SUGGESTION_ITEM_SELECTORS:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, sel)
                items = [it for it in items if it.is_displayed()]
                if items:
                    break
            except:
                continue

    if not items:
        return None

    # Return href of the first suggestion
    first = items[0]
    href = None
    try:
        a = first.find_element(By.TAG_NAME, "a")
        href = a.get_attribute("href")
    except:
        pass
    return href

def select_only_songs(driver):
    """
    Type two letters to trigger the refinement filters, then select 'Písnička' only.
    """
    search_input = driver.find_element(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
    # type two letters to trigger filter
    search_input.send_keys("aa")
    time.sleep(0.5)  # wait for refinement filters to render

    try:
        checkbox = driver.find_element(
            By.CSS_SELECTOR, "input.ais-RefinementList-checkbox[value='Písnička']"
        )
        if not checkbox.is_selected():
            checkbox.click()
            time.sleep(0.5)  # wait for filter to apply
    except Exception as e:
        print(f"Warning: could not select 'Písnička' filter: {e}")

    # Clear the search input
    from selenium.webdriver.common.keys import Keys
    import platform
    search_input.clear()
    if platform.system() == "Darwin":
        search_input.send_keys(Keys.COMMAND + "a")
    else:
        search_input.send_keys(Keys.CONTROL + "a")
    search_input.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)

############################################################################

BASIC_CHARS = set("ABCDEFGH")   # basic chord characters
SPACE = " "
TILDE = "~"

def normalize_chord(ch):
    """Normalize m → mi."""
    ch = re.sub(r"(?<!i)m($|[^a-z])", r"mi\1", ch)
    return ch


def likely_chord_line(line):
    """Heuristic: many blanks + at least 1/4 characters chordish."""
    stripped = line.strip()
    if not stripped:
        return False
    pure = re.sub(r"[^A-Za-z#b]", "", line)
    if not pure:
        return False
    frac = sum(1 for c in pure if c in BASIC_CHARS) / len(pure)
    return frac >= 0.25


def extract_chords_positions(line):
    """Return list of (pos, chord) from chord line."""
    positions = []
    tokens = re.finditer(r"([A-H][#b]?(?:mi|m)?[0-9()\/\-]*)", line)
    for m in tokens:
        chord = normalize_chord(m.group(1))
        positions.append((m.start(), chord))
    return positions


def place_chords_in_lyric(chord_positions, lyric_line, label_offset=0):
    """
    Insert ^{Chord} into lyric_line according to character positions.
    Adjust positions by label_offset (for numbering like '1. ').
    """
    if not chord_positions:
        return lyric_line

    line = lyric_line
    inserts = []

    for pos, chord in chord_positions:
        # Adjust for label offset
        pos -= label_offset
        if pos < 0:
            pos = 0
        if pos >= len(line):
            pos = len(line) - 1
        inserts.append((pos, chord))

    inserts.sort(reverse=True)

    for pos, chord in inserts:
        before = line[:pos].rstrip()
        after = line[pos:].lstrip()

        insert_at = pos - 1
        chord_mark = f"^{{{chord}}}"

        # Check adjacency to previous chord
        prev_chord_collision = False
        search = line[:insert_at]
        if re.search(r"\}\s*$", search) is not None:
            prev_chord_collision = True

        if prev_chord_collision:
            chord_mark = f"^*{{{chord}}} "
        else:
            words = before.split()
            last_word = words[-1] if words else ""
            if len(last_word) < 3:
                chord_mark += TILDE
            else:
                chord_mark += SPACE

        line = line[:insert_at] + chord_mark + line[insert_at:]

    return line

def convert_block_to_list(text):
    """
    Convert chord+lyrics text to list of [section, text] pairs,
    detecting any label ending with ':' and adjusting for label offsets.
    """
    lines = text.splitlines()
    pending_chords = []
    sections_list = []

    current_section = "verse"
    current_lines = []
    label_offset = 0

    for line in lines:
        stripped = line.strip()

        # Numbered paragraph (verse)
        m_number = re.match(r"^(\s*\d+[\.\)])\s*(.*)", line)
        # Generic label ending with ':' (Chorus:, Bridge:, Pause:, etc.)
        m_label = re.match(r"^(\s*[\w\s]+:)\s*(.*)", line)

        if m_number:
            # Save previous section
            if current_lines:
                sections_list.append([current_section, "\n".join(current_lines)])
            current_section = "verse"
            current_lines = []

            # Compute offset for label
            label_offset = len(m_number.group(1))
            lyric_text = m_number.group(2)
            if lyric_text:
                converted = place_chords_in_lyric(pending_chords, lyric_text, label_offset)
                pending_chords = []
                current_lines.append(converted)
            continue

        elif m_label:
            if current_lines:
                sections_list.append([current_section, "\n".join(current_lines)])
            # Use the label name as section name (lowercased)
            current_section = m_label.group(1).strip().rstrip(':').lower()
            current_lines = []

            label_offset = len(m_label.group(1))
            lyric_text = m_label.group(2)
            if lyric_text:
                converted = place_chords_in_lyric(pending_chords, lyric_text, label_offset)
                pending_chords = []
                current_lines.append(converted)
            continue

        # Chord line?
        if likely_chord_line(line):
            pending_chords = extract_chords_positions(line)
            continue

        # Lyric line
        if stripped:
            converted = place_chords_in_lyric(pending_chords, stripped)
            pending_chords = []
            current_lines.append(converted)

    # Append last section
    if current_lines:
        sections_list.append([current_section, "\n".join(current_lines)])

    return sections_list

######################################################################################


def get_song_info(title: str, artist = None):
    """
    Retrieve the top match for a song by title.
    Returns a list: [band/artist, release year] or None if not found.
    """
    return [artist, 1999]
    query = f'recording:"{title}"'
    if artist:
        query += f' AND artist:"{artist}"'
    params = {
        'query': query,
        'fmt': 'json',
        'limit': 1
    }
    resp = requests.get(
        "https://musicbrainz.org/ws/2/recording/",
        params=params,
        headers={"User-Agent": "song-info-tool/0.1 (your-email@example.com)"}
    )

    if resp.status_code != 200:
        print(f"Error: {resp.status_code}")
        return None

    data = resp.json()
    recordings = data.get('recordings', [])
    if not recordings:
        return None

    rec = recordings[0]
    artist_name = rec['artist-credit'][0]['artist']['name']
    year = None

    # Try to get the first available release year
    if 'releases' in rec and rec['releases']:
        for rel in rec['releases']:
            date = rel.get('date')
            if date:
                year = date.split('-')[0]  # extract YYYY
                break

    return [artist_name, year]

######################################################################################

def main():
    driver = create_driver(headless=False)
    results: Dict[str, Optional[str]] = {}

    try:
        # Load homepage once
        SITE_URL = "https://pisnicky-akordy.cz/"
        try:
            driver.get(SITE_URL)
        except TimeoutException:
            print("Warning: homepage load timed out, proceeding...")

        time.sleep(1)
        # Select only songs filter once
        select_only_songs(driver)
        
        with open("song_metadata.json") as input_file:
            song_metadata = json.load(input_file)
        for song in song_metadata:
            term = song['title'] + " " +  song['artist']   
            print(f"Searching for: {term}")
            url = search_top_result(driver, term)
            song['url'] = url
            print(f" -> Top result: {url}\n")
            time.sleep(0.1)  # small delay between searches
    finally:
        driver.quit()

    with open("song_metadata_with_url.json", "wt") as output_file:
        output_file.write(json.dumps(song_metadata))

if __name__ == "__main__":
    main()



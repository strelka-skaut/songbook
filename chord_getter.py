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
SUGGESTION_ITEM_SELECTORS = [ "div.ais-Hits-item", "li.ais-Hits-item", "a.ais-Hits-item"
]
TYPING_DELAY = 0.05  # seconds per keystroke
PAGE_LOAD_TIMEOUT = 7  # max seconds to wait for homepage

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/117.0 Safari/537.36"
}

####################################################################

def extract_song(url: str) -> Optional[Dict[str, str]]:
    """
    Extract song title, lyrics, and chords from a single URL.
    Returns None if the page cannot be processed.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Example observation of site structure:
    # Lyrics/chords are often inside <pre> or <div class="songtext"> or similar
    # Song title usually in <h1>
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown title"

    # Lyrics/chords
    # Try <pre> first
    lyrics_chords = ""
    pre_tag = soup.find("pre")
    if pre_tag:
        lyrics_chords = pre_tag.get_text("\n", strip=True)
        println(pre_tag.get_text("", strip=False))
    else:
        # fallback: div with song text
        div_tag = soup.find("div", class_="songtext")
        if div_tag:
            lyrics_chords = div_tag.get_text("\n", strip=True)

    if not lyrics_chords:
        print(f"No lyrics/chords found for {title} ({url})")
        return None

    return {
        "title": title,
        "url": url,
        "lyrics_chords": lyrics_chords
    }


def extract_chords_and_lyrics(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    output_lines = []

    # find all chord blocks
    for el in soup.find("pre").find_all("el", class_="aline"):
        # ----- extract chord line -----
        chord_line = ""

        # We keep the inline structure: text + spans
        for item in el.children:
            if isinstance(item, NavigableString):
                chord_line += str(item)
            else:
                # chords are in <a> inside <span class="akord">
                a = item.find("a")
                if a:
                    chord_line += a.get_text()
                else:
                    chord_line += item.get_text()

        # Strip only right side to maintain indentation
        chord_line = chord_line.rstrip()
        output_lines.append(chord_line)

        # ----- extract lyric line following <el> -----
        next_text = ""
        nxt = el.next_sibling

        # move to next non-empty text node
        while nxt and (not isinstance(nxt, NavigableString) or not nxt.strip()):
            nxt = nxt.next_sibling

        if isinstance(nxt, NavigableString):
            next_text = nxt.strip("\n")
            output_lines.append(next_text)
    aligned_text = '\n'.join(output_lines)
    return aligned_text

def extract_song_aligned(url: str) -> Optional[Dict[str, str]]:
    """
    Fetches the page at url, extracts the title, and returns the text
    with chords aligned over lyric lines (so the output preserves chords positioned above lyrics).
    Returns None if extraction fails.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

    return extract_chords_and_lyrics(resp.text, url)

######################################################################################

def get_song_info(title: str, artist = None):
    """
    Retrieve the top match for a song by title.
    Returns a list: [band/artist, release year] or None if not found.
    """
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

####################################################################

def main():
    with open('song_metadata_with_url.json') as f:
        songs = json.load(f)
    
    for song in songs:
        print(f"Getting chords of {song['title']} ({song['url']})", end=": ")
        song['chords'] = extract_song_aligned(song['url'])
        print(song['chords'])

    with open('song_with_chords.json', "wt") as output_file:
        output_file.write(json.dumps(songs))
        
if __name__ == "__main__":
    main()

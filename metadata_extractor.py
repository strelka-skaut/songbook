import requests
from bs4 import BeautifulSoup
from pick import pick
import json

BASE_URL = "https://www.supraphonline.cz"

def read_song_list(filename="song_list.txt"):
    """Read the list of songs from a text file."""
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def search_song(song_title):
    """Search Supraphonline for a song and return a list of results."""
    search_url = f"{BASE_URL}/vyhledavani"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    params = {"q": song_title}
    response = requests.get(search_url, headers=headers, params=params)
    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for track in soup.find_all("tr", class_="track"):
        td_tags = track.find_all("td")
        if len(td_tags) < 5:
            continue

        title_tag = td_tags[1].find("a")
        album_tag = td_tags[3].find("a")
        artist_tag = td_tags[4].find("a")

        if title_tag and artist_tag and album_tag:
            results.append({
                "title": title_tag.text.strip(),
                "artist": artist_tag.text.strip(),
                "album_url": BASE_URL + album_tag['href'],
                "track_url": BASE_URL + title_tag['href']
            })

    return results


def get_release_year(track_url):
    """Get the release year from the song's track page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    response = requests.get(track_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the summary <ul> inside _trackdetail
    summary_ul = soup.select_one("div._trackdetail ul.summary")
    if summary_ul:
        for li in summary_ul.find_all("li"):
            span = li.find("span")
            if span and "Rok prvního vydání" in span.text:
                # Extract the year text after the span
                year_text = li.get_text(separator=" ").replace(span.text, "").strip()
                import re
                match = re.search(r"\b(19|20)\d{2}\b", year_text)
                if match:
                    return match.group(0)
                else:
                    return year_text  # fallback
    return None


def main():
    song_list = read_song_list()
    final_results = []

    for song in song_list:
        print(f"\nSearching for: {song}")
        results = search_song(song)
        if not results:
            print("No results found.")
            continue

        # Let user pick the correct song
        options = [f"{r['title']} - {r['artist']}" for r in results]
        option, index = pick(options, "Pick the correct song:")
        selected_song = results[index]

        # Get release year
        track_id = selected_song['track_url'].split("trackId=")[-1]
        release_year = get_release_year(selected_song['track_url'])
        if release_year:
            print(f"Found release year: {release_year}")
            confirm_year = input(f"Confirm or edit the release year for '{selected_song['title']}' (leave blank to keep): ")
            if confirm_year.strip():
                release_year = confirm_year.strip()
        else:
            release_year = input(f"Enter release year for '{selected_song['title']}': ")

        final_results.append({
            "title": selected_song['title'],
            "artist": selected_song['artist'],
            "release_year": release_year
        })

    print("\nFinal results:")
    print(json.dumps(final_results, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    main()


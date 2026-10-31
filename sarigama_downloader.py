#!/usr/bin/env python3
"""
Download all songs of an artist from sarigama.lk

Usage:
    pip install -r requirements.txt
    playwright install chromium   # one-time browser download
    python sarigama_downloader.py "https://sarigama.lk/artist/milton-mallawarachchi/9ce1e4cf-7b8a-4242-a47f-c99d80b6239f"

Options:
    -o, --out DIR       Output folder (default: ./downloads/<artist-slug>)
    --versions          Also download "Different Versions" (instrumental, remix...) of each song
    --delay SECONDS     Pause between songs (default: 1.5) - be polite to the server
    --limit N           Only download the first N songs (handy for a test run)
    --headed            Show the browser window (useful for debugging)

Re-running is safe: files that already exist are skipped.

Note: sarigama.lk serves a placeholder page to plain HTTP clients hitting the
download endpoint (anti-bot protection), so the actual download click is
driven through a real headless browser (Playwright) rather than requests.
"""
import argparse
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://sarigama.lk"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
SONG_RE = re.compile(r"/sinhala-song/[^/]+/[^/]+/[0-9a-f-]{36}$")
DOWNLOAD_BTN_SELECTOR = "a[href*='/files/'][href*='/download']"
VERSION_LINK_SELECTOR = "a[href^='#diff-song-']"


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .")
    return name or "untitled"


def get_soup(session, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def get_song_links(session, artist_url):
    """Return (artist_name, [(title, song_url), ...]) from the artist page."""
    soup = get_soup(session, artist_url)
    h1 = soup.find("h1")
    artist = h1.get_text(strip=True) if h1 else "artist"

    seen, songs = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"])
        path = urlparse(href).path
        if SONG_RE.search(path) and href not in seen:
            title = a.get_text(strip=True)
            if not title:  # image-only link; the title link appears separately
                continue
            seen.add(href)
            songs.append((title, href))
    return artist, songs


def click_and_capture_download(page, locator, timeout=60000):
    """Click a target="_blank" download link and capture the Download that
    lands on the popup tab it opens, closing the popup afterwards."""
    result = {}

    def on_popup(popup):
        def on_download(download):
            result["download"] = download

        popup.on("download", on_download)
        result["popup"] = popup

    page.context.on("page", on_popup)
    try:
        locator.click()
        deadline = time.monotonic() + timeout / 1000
        while "download" not in result and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        if "download" not in result:
            raise RuntimeError("no download event after clicking")
        return result["download"]
    finally:
        page.context.remove_listener("page", on_popup)
        popup = result.get("popup")
        if popup and not popup.is_closed():
            popup.close()


def download_song(page, song_url, out_dir, title, include_versions, delay):
    """Open the song page in a real browser and click through the download
    button(s), saving whatever file(s) the browser actually downloads."""
    page.goto(song_url, wait_until="domcontentloaded", timeout=60000)

    buttons = page.locator(DOWNLOAD_BTN_SELECTOR)
    count = buttons.count()
    if count == 0:
        raise RuntimeError("no download button found on page")

    labels = [""]
    if include_versions:
        vers = page.locator(VERSION_LINK_SELECTOR)
        labels += [vers.nth(i).inner_text().strip() for i in range(vers.count())]

    results = []
    n = count if include_versions else 1
    for i in range(n):
        label = labels[i] if i < len(labels) else f"version{i}"
        name = f"{title} - {label}" if label else title
        fname = safe_name(name) + ".mp3"
        path = os.path.join(out_dir, fname)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            results.append((path, False))
            continue

        download = click_and_capture_download(page, buttons.nth(i))
        tmp = path + ".part"
        download.save_as(tmp)
        os.replace(tmp, path)
        results.append((path, True))
        time.sleep(delay)

    return results


def main():
    ap = argparse.ArgumentParser(description="Download all songs of an artist from sarigama.lk")
    ap.add_argument("artist_url")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--versions", action="store_true", help="also download alternate versions")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()

    session = requests.Session()

    print(f"Fetching artist page: {args.artist_url}")
    artist, songs = get_song_links(session, args.artist_url)
    if not songs:
        sys.exit("No songs found on that page. Is the URL correct?")
    if args.limit:
        songs = songs[: args.limit]

    slug = urlparse(args.artist_url).path.strip("/").split("/")[1]
    out_dir = args.out or os.path.join("downloads", slug)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Artist: {artist} | {len(songs)} songs -> {out_dir}\n")

    ok = skipped = failed = 0
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], accept_downloads=True)
        page = context.new_page()

        for i, (title, song_url) in enumerate(songs, 1):
            prefix = f"[{i}/{len(songs)}] {title}"
            try:
                results = download_song(page, song_url, out_dir, title, args.versions, args.delay)
                for path, fresh in results:
                    if fresh:
                        ok += 1
                        print(f"{prefix}  ✓ {os.path.basename(path)}")
                    else:
                        skipped += 1
                        print(f"{prefix}  = already exists")
            except Exception as e:
                failed += 1
                failures.append((title, song_url, str(e)))
                print(f"{prefix}  ✗ {e}")
            time.sleep(args.delay)

        context.close()
        browser.close()

    print(f"\nDone. downloaded={ok} skipped={skipped} failed={failed}")
    if failures:
        fail_file = os.path.join(out_dir, "failed.txt")
        with open(fail_file, "w", encoding="utf-8") as f:
            for t, u, e in failures:
                f.write(f"{t}\t{u}\t{e}\n")
        print(f"Failed items listed in {fail_file} - just re-run the script to retry them.")


if __name__ == "__main__":
    main()

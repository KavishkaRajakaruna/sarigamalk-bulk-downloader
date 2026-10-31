# Song Downloader

Don't waste time clicking download on every single song — download an artist's entire discography from [sarigama.lk](https://sarigama.lk) with one command.

## How it works

1. Scrapes the artist page for every song link (via `requests` + `BeautifulSoup`).
2. Opens each song page in a real headless browser (Playwright/Chromium) and clicks the actual download button, because sarigama.lk serves a decoy HTML page to plain HTTP requests (anti-bot protection) — only a real browser gets the audio file.
3. Saves each file to disk, skipping anything already downloaded.

## Setup

```bash
python3 -m venv .env
source .env/bin/activate
pip install -r requirements.txt
playwright install chromium   # one-time browser download, ~150MB
```

## Usage

```bash
python sarigama_downloader.py "https://sarigama.lk/artist/milton-mallawarachchi/9ce1e4cf-7b8a-4242-a47f-c99d80b6239f"
```

Files are saved to `downloads/<artist-slug>/` by default.

### Options

| Flag | Description |
|---|---|
| `-o, --out DIR` | Output folder (default: `./downloads/<artist-slug>`) |
| `--versions` | Also download "Different Versions" (instrumental, remix, etc.) of each song |
| `--delay SECONDS` | Pause between downloads (default: `1.5`) — be polite to the server |
| `--limit N` | Only download the first N songs (handy for a test run) |
| `--headed` | Show the browser window instead of running headless (useful for debugging) |

### Examples

Test with just the first 2 songs:
```bash
python sarigama_downloader.py "<artist-url>" --limit 2
```

Download everything including alternate versions:
```bash
python sarigama_downloader.py "<artist-url>" --versions
```

## Notes

- Re-running is safe — files that already exist are skipped.
- Failed downloads are logged to `failed.txt` in the output folder; just re-run the same command to retry them.
- For personal use only — be mindful of the site's terms of service and don't hammer the server (keep the default delay).

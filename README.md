# Crate Builder

A free, local alternative to services like cratehackers.com: paste a CSV, a
Spotify playlist URL, or a plain track list, and it fuzzy-matches those
tracks against your local music library and writes a new Serato crate.

Everything runs on your own machine — your music files, your Serato
database, and the matching all stay local. Nothing is uploaded anywhere
except the one Spotify API call needed to read a playlist's track list (if
you use that input method).

## How it works

1. **Scan** — recursively walks a music folder and reads ID3/tag metadata
   (title/artist/album) via `mutagen`, falling back to parsing the filename
   when tags are missing.
2. **Parse input** — auto-detects whether your pasted text is a Spotify
   playlist URL, a CSV (with or without a header row), or a plain
   `Artist - Title` list.
3. **Match** — fuzzy-matches each input track against your library using
   `rapidfuzz`, stripping noise like "(Official Audio)" / "feat. ..." before
   scoring. Anything below the match threshold is flagged for manual review
   with a "Find match" search box instead of being silently dropped.
4. **Build** — writes a new `.crate` file into your Serato
   `_Serato_/Subcrates` folder, so it shows up as a new crate next time you
   open Serato.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Optional: Spotify playlist support

Pasting plain text or CSV works with no setup. To paste a Spotify playlist
URL directly:

1. Create a free app at https://developer.spotify.com/dashboard.
2. In the app's **Settings**, add this exact Redirect URI:
   `http://127.0.0.1:5001/callback`
3. Copy its Client ID and Client Secret:
   ```bash
   cp .env.example .env
   # edit .env and fill in SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
   ```
4. Run the app and click **Connect Spotify** in the page — it'll send you to
   Spotify to log in once, then bring you back.

This uses a real (one-time) Spotify login rather than app-only auth,
because Spotify's API no longer allows app-only tokens to read playlists
they don't own — even public ones. Logging in lets it read any playlist you
can see in the Spotify app. Your login token is cached locally in
`.spotify_token_cache` (gitignored) so you won't need to log in every run.

## Running it

**Easiest: double-click `start.command`** in Finder (after the one-time
setup above). It activates the virtual environment, starts the server, and
opens your browser automatically — no Terminal typing needed. If macOS
warns about an unidentified developer the first time, right-click
`start.command` → **Open** instead of double-clicking, and confirm once.

Or manually:

```bash
python app.py
```

Open http://127.0.0.1:5001 in your browser.

(Port 5001, not 5000 — macOS reserves 5000 for AirPlay Receiver and will
return a confusing 403 if you try to use it. If you'd rather free up 5000
instead, turn off AirPlay Receiver in System Settings → General → AirDrop &
Handoff.)

1. Set your **music library folder** (defaults to `~/Music`) and click
   **Scan Library**.
2. Set your **Serato folder** — the one containing `_Serato_`
   (defaults to `~/Music/_Serato_`; change it if yours lives elsewhere,
   e.g. a different drive).
3. Enter a **crate name**. Use `Parent > Child` to build it as a subcrate
   nested under an existing crate.
4. Paste your CSV / Spotify playlist URL / track list into the text box and
   click **Preview Matches**.
5. Review the match table — uncheck anything wrong, or click **Find match**
   on unmatched rows to manually search and pick the right file.
6. Click **Build Crate**.
7. Restart Serato (or use its "rescan" option) to see the new crate.

## Notes on the `.crate` format

Serato doesn't publish the `.crate` file format; this tool writes it based
on community reverse-engineering (a simple tag/length/value binary format).
It's worked reliably in testing, but as with any tool that writes into a
DJ database:

- **Back up your `_Serato_` folder** before your first run.
- This tool only ever *creates new* `.crate` files — it never modifies your
  existing crates or the main Serato database — but it will refuse to
  silently overwrite a crate with the same name (it'll ask first).
- Verify a freshly built crate opens correctly in Serato before relying on
  it during a set.

## Running tests

```bash
pip install pytest
pytest
```

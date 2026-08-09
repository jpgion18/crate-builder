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

## Discover tab

A separate **Discover** page (nav link at the top) for finding new music
from what other working DJs are actually playing — useful for breaking out
of a rut. Paste in a tracklist copied from 1001tracklists, a Beatport chart,
a Mixcloud/SoundCloud mix description, or a Spotify playlist URL, tag it
with a source (e.g. "Solomun @ Tomorrowland 2026"), and it checks each
track against your library. Anything you don't already have gets added to
a persistent **Discovery Log** — a running "to check out" list stored
locally in `discovery_log.json` (gitignored) that survives across
sessions, dedupes overlapping tracklists automatically, and lets you mark
each entry as new / acquired / dismissed as you work through it. Export it
to CSV anytime.

This is paste-based rather than a live crawler — sites like
1001tracklists and Beatport don't offer public APIs, and scraping them
would be a ToS/legal gray area, so you bring the tracklist and this tool
does the cross-referencing.

## Desktop app (recommended for most users)

Most people don't need to touch Python or a terminal at all: download the
prebuilt app for your OS from the
[latest release](https://github.com/jpgion18/crate-builder/releases) —
`CrateBuilder.app` (macOS) or `CrateBuilder.exe` (Windows) — and double-click
it. It opens as a normal desktop window; there's no browser tab, no
`localhost` URL, nothing to run separately.

These builds are unsigned (no Apple Developer / Windows code-signing
certificate), so the OS will warn you the first time you open one:
- **macOS**: right-click the app → **Open** → **Open** (instead of
  double-clicking) to bypass Gatekeeper.
- **Windows**: click **More info** → **Run anyway** on the SmartScreen prompt.

The sections below (Setup, Running it) are for running from source instead —
useful for development, or if you'd rather build/run it yourself.

### Building the desktop app yourself

A GitHub Actions workflow (`.github/workflows/build-desktop.yml`) builds
macOS and Windows binaries via PyInstaller. Push a `v*` tag, or trigger it
manually from the Actions tab, then download the artifacts from that run. To
build locally instead:

```bash
pip install -r requirements-desktop.txt
pyinstaller desktop_app.spec
```

The build lands in `dist/CrateBuilder.app` (macOS) or `dist/CrateBuilder/`
(Windows/Linux).

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

### Optional: Showfile playlist sync

If you use [Showfile](https://github.com/jpgion18/showfile) to manage DJ
gigs, crate-builder can push a matched playlist straight to an event's
timeline so the couple sees song suggestions there. Set it up:

```bash
cp .env.example .env
# edit .env and fill in SHOWFILE_API_URL / SHOWFILE_API_KEY
```

Get your API key from the Showfile dashboard's "Playlist sync
(crate-builder)" panel. After previewing and selecting matches below, enter
the event's code (e.g. `KATIE-DREW-1004`) in the **Sync to Showfile** field
and click the button — it sends the selected, matched tracks' artist/title
to Showfile, replacing that event's synced playlist each time. This is
additive to building a Serato crate, not a replacement for it; you can do
either, both, or neither per session.

## Running it

If you'd rather not use the packaged desktop app above, run from source:

**Easiest: double-click `start.command`** in Finder (after the one-time
setup above). It activates the virtual environment, starts the server, and
opens your browser automatically — no Terminal typing needed. If macOS
warns about an unidentified developer the first time, right-click
`start.command` → **Open** instead of double-clicking, and confirm once.

Or as a local web app (browser), manually:

```bash
python app.py
```

Open http://127.0.0.1:5001 in your browser.

(Port 5001, not 5000 — macOS reserves 5000 for AirPlay Receiver and will
return a confusing 403 if you try to use it. If you'd rather free up 5000
instead, turn off AirPlay Receiver in System Settings → General → AirDrop &
Handoff.)

Or as a native window, without building the packaged app:

```bash
pip install -r requirements-desktop.txt
python desktop_app.py
```

Either way, the workflow is the same:

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

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

## Library Tools tab

Housekeeping for your local library, separate from matching/building a
crate:

- **Duplicate finder** — scans your library for tracks that look like the
  same song: exact matches after normalizing case/punctuation/noise words,
  plus close variants (like a missing featured-artist credit) that share
  the same title. It only *finds* duplicates and shows you each file's
  path — nothing gets deleted automatically. Remove files yourself in
  Finder/Explorer once you've reviewed a group.
- **Metadata editor** — search your library, pick a track, and edit its
  title/artist/album/genre/year/track number. This is the one part of
  crate-builder that changes your actual music files rather than only
  reading them (or, like crate-building, writing new files elsewhere) —
  so every save backs up the original file first
  (`~/.crate_builder/tag_backups/`, keyed by file path, one backup per
  edit — not just the first one, so you can step back through a history of
  changes). The **Recent backups** list on the same page can restore any
  of them with one click.

Not currently pulled from Spotify: release year and other metadata could
in principle come from a matched Spotify track, but that's not wired up
yet. Spotify's "audio features" data (danceability, energy, etc.) isn't an
option at all — Spotify deprecated that whole API for new apps in late
2024, which includes crate-builder's shared app.

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
macOS and Windows binaries via PyInstaller.

- **Push a `v*` tag** (e.g. `v0.1.0`) to publish a proper
  [Release](https://github.com/jpgion18/crate-builder/releases) with
  `CrateBuilder-macos.zip` / `CrateBuilder-windows.zip` attached — this is
  what the download link above points to.
- **Trigger it manually** from the Actions tab to just build and sanity-check
  without publishing a release; grab the zips from that run's artifacts
  instead (these expire after 90 days).

To build locally instead:

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

### Spotify playlist support

Pasting plain text or CSV works with no setup. To paste a Spotify playlist
URL directly, just click **Connect Spotify** — it opens your browser to log
into Spotify once, then brings you back. No developer account, no API keys,
nothing to configure; every crate-builder download shares one built-in
Spotify app for this ("Log in with Spotify" works the same way as "Log in
with Showfile" elsewhere in the app). Your login is cached locally in
`~/.crate_builder/spotify_token_cache` so you won't need to log in every run.

This uses a real (one-time) Spotify login rather than app-only auth,
because Spotify's API no longer allows app-only tokens to read playlists
they don't own — even public ones. Logging in lets it read any playlist you
can see in the Spotify app, and doesn't give crate-builder (or its shared
app) any access beyond what your own account already has.

Prefer to use your own Spotify app instead of the shared one? Create a free
one at https://developer.spotify.com/dashboard, add
`http://127.0.0.1:5001/callback` as a Redirect URI, then:
```bash
cp .env.example .env
# edit .env and fill in SPOTIFY_CLIENT_ID
```
No client secret needed either way — this uses PKCE (Authorization Code
with Proof Key for Code Exchange), the flow Spotify recommends for apps
that can't keep a secret confidential, which a distributed desktop binary
can't.

### Optional: connect Showfile (Playlist Sync + Community)

If you use [Showfile](https://github.com/jpgion18/showfile) to manage DJ
gigs, open crate-builder's own **Settings** page and click **"Log in with
Showfile"** — it opens your browser to log into your existing Showfile
account and sends both credentials back automatically, no copy-pasting.
(Manual entry — pasting the site URL, API key, and Community access code
from Showfile's own Settings page — still works too, as a fallback; both
save to the same place on your machine, not a file you have to hand-edit.)
Connecting Showfile unlocks two independent features:

- **Playlist Sync** — after previewing and selecting matches, enter an
  event's code (e.g. `KATIE-DREW-1004`) in the **Sync to Showfile** field
  and click the button — it sends the selected, matched tracks'
  artist/title to that event's timeline, so the couple sees song
  suggestions there. Replaces that event's synced playlist each time.
- **Crate Builder Community** — a free perk for DJs with an active
  Showfile subscription: publish and browse crate track lists on the
  **Community** tab, for sharing and education, not audio. Only
  artist/title metadata ever leaves your machine. To publish your own:
  check **"Also publish this crate to the Community feed"** before
  clicking Build Crate.

Both are additive to building a local Serato crate, not a replacement for
it, and crate-builder's core matching/crate-building stays fully free
either way — Settings only gates these two Showfile-connected extras.
`.env` still works as a fallback (`SHOWFILE_API_URL` / `SHOWFILE_API_KEY` /
`COMMUNITY_API_URL`) if you'd rather not use the Settings page, but
whatever's saved in Settings takes priority.

### MyEvents tab (automated Playlist Sync, once connected)

Once Showfile's connected, crate-builder polls it every few minutes for
songs your couples have entered on their timelines — no manual
paste/export needed. **MyEvents** shows one tile per event with songs
waiting, each with a count of what's new since the last check and a
**"Match this event's songs"** button.

There's really only one "Crate Builder" in this app — the match/review
table, Build Crate, Sync to Showfile, and Publish to Community on the main
page. MyEvents, Discover, and Community are all just *sources* that feed
it: MyEvents' "Match this event's songs," Discover's "Build a Crate from
this," and Community's "Send to Crate Builder" all land you on the main
page with that source's tracklist already pasted in and matched, ready to
review — nothing about matching or building is duplicated per-tab.

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

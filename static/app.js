const $ = (id) => document.getElementById(id);

const thresholdInput = $("threshold");
const thresholdValue = $("threshold_value");
thresholdInput.addEventListener("input", () => {
  thresholdValue.textContent = thresholdInput.value;
});

let lastMatches = [];

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

const previewBar = $("preview_player_bar");
const previewAudio = $("preview_audio");

function playPreview(track) {
  const library_dir = $("library_dir").value.trim();
  const serato_dir = $("serato_dir").value.trim();
  const url = `/api/audio?path=${encodeURIComponent(track.path)}&library_dir=${encodeURIComponent(library_dir)}&serato_dir=${encodeURIComponent(serato_dir)}`;

  $("preview_label").textContent = `${track.title} — ${track.artist}`;
  setStatus($("preview_player_status"), "");
  previewAudio.src = url;
  previewBar.classList.remove("hidden");
  document.body.classList.add("has-preview-player");
  previewAudio.play().catch(() => {
    setStatus($("preview_player_status"), "Couldn't play this file — format may not be supported.", true);
  });
}

function makePreviewButton(track) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "preview-btn";
  btn.textContent = "▶";
  btn.title = "Preview this track";
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    playPreview(track);
  });
  return btn;
}

$("preview_close_btn").addEventListener("click", () => {
  previewAudio.pause();
  previewAudio.removeAttribute("src");
  previewAudio.load();
  previewBar.classList.add("hidden");
  document.body.classList.remove("has-preview-player");
});

async function refreshSpotifyStatus() {
  try {
    const res = await fetch("/api/spotify-status");
    const data = await res.json();
    const statusEl = $("spotify_status");
    const btnEl = $("spotify_connect_btn");
    if (data.connected) {
      statusEl.textContent = "Connected";
      btnEl.textContent = "Reconnect Spotify";
    } else {
      statusEl.textContent = "Not connected — required only for Spotify playlist URLs";
      btnEl.textContent = "Connect Spotify";
    }
  } catch (err) {
    // Spotify status is best-effort; ignore failures here.
  }
}

$("spotify_connect_btn").addEventListener("click", () => {
  window.location.href = "/login";
});

async function pollSpotifyUntilConnected() {
  setStatus($("spotify_status"), "Waiting for you to finish logging in (opened in your browser)...");
  const deadline = Date.now() + 2 * 60 * 1000; // 2 minutes
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const res = await fetch("/api/spotify-status");
    const data = await res.json();
    if (data.connected) {
      refreshSpotifyStatus();
      return;
    }
  }
  setStatus($("spotify_status"), "Still waiting — try again if the browser tab didn't open.", true);
}

refreshSpotifyStatus();

const spotifyParams = new URLSearchParams(window.location.search);
const spotifyPending = spotifyParams.get("spotify_pending");
const spotifyError = spotifyParams.get("spotify_error");
if (spotifyPending || spotifyError) {
  window.history.replaceState({}, "", "/");
}
if (spotifyError) {
  setStatus($("spotify_status"), `Spotify login failed: ${spotifyError}`, true);
} else if (spotifyPending) {
  pollSpotifyUntilConnected();
}

async function refreshCommunityStatus() {
  const el = $("community_status");
  if (el.dataset.communityConfigured !== "true") return; // Community URL isn't configured yet; keep that message.
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (!data.community_access_code) {
      setStatus(el, "Add your Showfile access code in Settings to enable publishing.");
    }
  } catch (err) {
    // Best-effort; ignore failures here.
  }
}

refreshCommunityStatus();

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

$("scan_btn").addEventListener("click", async () => {
  const library_dir = $("library_dir").value.trim();
  const serato_dir = $("serato_dir").value.trim();
  setStatus($("scan_status"), "Scanning...");
  try {
    const data = await postJSON("/api/scan", { library_dir, serato_dir });
    setStatus($("scan_status"), `Found ${data.track_count} tracks.`);
  } catch (err) {
    setStatus($("scan_status"), err.message, true);
  }
});

$("preview_btn").addEventListener("click", async () => {
  const library_dir = $("library_dir").value.trim();
  const serato_dir = $("serato_dir").value.trim();
  const input_text = $("input_text").value;
  const threshold = Number(thresholdInput.value);

  setStatus($("preview_status"), "Matching...");
  $("build_status").textContent = "";
  try {
    const data = await postJSON("/api/preview", { library_dir, serato_dir, input_text, threshold });
    lastMatches = data.matches;
    renderResults(data);
    setStatus(
      $("preview_status"),
      `${data.matched_count}/${data.input_count} matched against ${data.library_count} library tracks.`
    );
  } catch (err) {
    setStatus($("preview_status"), err.message, true);
    $("results_panel").classList.add("hidden");
  }
});

function renderResults(data) {
  const panel = $("results_panel");
  panel.classList.remove("hidden");
  $("results_summary").textContent = `${data.matched_count} of ${data.input_count} tracks matched`;

  const tbody = document.querySelector("#results_table tbody");
  tbody.innerHTML = "";

  data.matches.forEach((m, i) => {
    const tr = document.createElement("tr");
    if (!m.matched) tr.classList.add("unmatched");
    if (m.ambiguous) tr.classList.add("ambiguous");

    const checkboxTd = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = m.matched;
    checkbox.dataset.index = i;
    checkboxTd.appendChild(checkbox);
    tr.appendChild(checkboxTd);

    const inputTd = document.createElement("td");
    inputTd.innerHTML = `<span class="track-line">${escapeHtml(m.input_title || m.raw)}</span><span class="track-sub">${escapeHtml(m.input_artist)}</span>`;
    tr.appendChild(inputTd);

    const matchTd = document.createElement("td");
    matchTd.dataset.role = "match-cell";
    renderMatchCell(matchTd, m, i);
    tr.appendChild(matchTd);

    const scoreTd = document.createElement("td");
    scoreTd.textContent = m.score;
    tr.appendChild(scoreTd);

    const actionTd = document.createElement("td");
    if (!m.matched) {
      const searchBtn = document.createElement("button");
      searchBtn.type = "button";
      searchBtn.textContent = "Find match";
      searchBtn.addEventListener("click", () => showManualSearch(actionTd, i, m));
      actionTd.appendChild(searchBtn);
    }
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });
}

function renderMatchCell(td, m, index) {
  td.innerHTML = "";
  m.extras = m.extras || [];
  const track = m.track;

  if (!track) {
    const noMatch = document.createElement("span");
    noMatch.className = "track-sub";
    noMatch.textContent = "no match found";
    td.appendChild(noMatch);
  } else if (m.ambiguous && m.candidates && m.candidates.length > 1) {
    const list = document.createElement("div");
    list.className = "candidate-list";
    m.candidates.forEach((c) => {
      const row = document.createElement("div");
      row.className = "candidate-row";

      const label = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `candidates_${index}`;
      radio.checked = c.path === track.path;
      radio.addEventListener("change", () => {
        lastMatches[index].track = { path: c.path, artist: c.artist, title: c.title, album: c.album };
      });
      label.appendChild(radio);
      label.appendChild(document.createTextNode(` ${c.title} — ${c.artist} (${c.score})`));
      row.appendChild(label);
      row.appendChild(makePreviewButton(c));

      list.appendChild(row);
    });
    td.appendChild(list);
    const hint = document.createElement("span");
    hint.className = "track-sub";
    hint.textContent = "multiple close matches — verify";
    td.appendChild(hint);
  } else {
    const row = document.createElement("div");
    row.className = "match-row";
    const info = document.createElement("span");
    info.innerHTML = `<span class="track-line">${escapeHtml(track.title)}</span><span class="track-sub">${escapeHtml(track.artist)} — ${escapeHtml(track.path)}</span>`;
    row.appendChild(info);
    row.appendChild(makePreviewButton(track));
    td.appendChild(row);
  }

  if (m.extras.length > 0) {
    const extrasList = document.createElement("div");
    extrasList.className = "extras-list";
    m.extras.forEach((extra, ei) => {
      const row = document.createElement("div");
      row.className = "extra-row";

      const info = document.createElement("span");
      info.className = "track-sub";
      info.textContent = `+ ${extra.title} — ${extra.artist}`;
      row.appendChild(info);
      row.appendChild(makePreviewButton(extra));

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "preview-btn";
      removeBtn.title = "Remove this extra track";
      removeBtn.textContent = "✕";
      removeBtn.addEventListener("click", () => {
        lastMatches[index].extras.splice(ei, 1);
        renderMatchCell(td, lastMatches[index], index);
      });
      row.appendChild(removeBtn);

      extrasList.appendChild(row);
    });
    td.appendChild(extrasList);
  }

  // Lets the same input line add more than one library track to the crate
  // — e.g. a Jump Off edit AND the Extended Version of the same song, to
  // mix one into the other. Available regardless of match state, since two
  // versions of a track don't always score close enough to trigger the
  // "ambiguous" ties above.
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "add-extra-btn";
  addBtn.textContent = "+ Add another version";
  addBtn.addEventListener("click", () => showAddExtraSearch(td, index));
  td.appendChild(addBtn);
}

function createSearchBox(container, defaultQuery, onSelect) {
  const existing = container.querySelector(".manual-search");
  if (existing) {
    existing.remove();
    container.querySelector(".manual-results")?.remove();
    return;
  }

  const box = document.createElement("div");
  box.className = "manual-search";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "search library...";
  input.value = defaultQuery;
  box.appendChild(input);
  container.appendChild(box);

  const resultsDiv = document.createElement("div");
  resultsDiv.className = "manual-results";
  container.appendChild(resultsDiv);

  const runSearch = async () => {
    const library_dir = $("library_dir").value.trim();
    const serato_dir = $("serato_dir").value.trim();
    const q = input.value.trim();
    if (!q) return;
    const res = await fetch(
      `/api/search?library_dir=${encodeURIComponent(library_dir)}&serato_dir=${encodeURIComponent(serato_dir)}&q=${encodeURIComponent(q)}`
    );
    const data = await res.json();
    resultsDiv.innerHTML = "";
    (data.results || []).forEach((r) => {
      const div = document.createElement("div");
      div.className = "manual-result";
      const label = document.createElement("span");
      label.textContent = `${r.title} — ${r.artist} (${r.score})`;
      div.appendChild(label);

      const playBtn = makePreviewButton({ path: r.path, artist: r.artist, title: r.title });
      playBtn.addEventListener("click", (e) => e.stopPropagation());
      div.appendChild(playBtn);

      div.addEventListener("click", () => {
        onSelect({ path: r.path, artist: r.artist, title: r.title, album: "" });
        box.remove();
        resultsDiv.remove();
      });
      resultsDiv.appendChild(div);
    });
  };

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch();
  });
  runSearch();
}

function showManualSearch(actionTd, index, matchObj) {
  createSearchBox(actionTd, `${matchObj.input_artist} ${matchObj.input_title}`.trim(), (track) => {
    lastMatches[index].track = track;
    lastMatches[index].matched = true;
    lastMatches[index].ambiguous = false;
    lastMatches[index].candidates = [];
    const row = actionTd.closest("tr");
    row.classList.remove("unmatched");
    row.querySelector('input[type="checkbox"]').checked = true;
    renderMatchCell(row.querySelector('[data-role="match-cell"]'), lastMatches[index], index);
  });
}

function showAddExtraSearch(matchTd, index) {
  const m = lastMatches[index];
  createSearchBox(matchTd, `${m.input_artist} ${m.input_title}`.trim(), (track) => {
    lastMatches[index].extras.push(track);
    renderMatchCell(matchTd, lastMatches[index], index);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function selectedMatchedTracks() {
  const checkboxes = document.querySelectorAll('#results_table input[type="checkbox"]');
  const tracks = [];
  checkboxes.forEach((cb) => {
    const m = lastMatches[Number(cb.dataset.index)];
    if (cb.checked && m.track) tracks.push(m.track);
    // Extra versions (e.g. a Jump Off edit alongside the Extended Version)
    // were explicitly added by the user via "+ Add another version", so
    // they're included regardless of the row's own checkbox state.
    if (m.extras && m.extras.length) tracks.push(...m.extras);
  });
  return tracks;
}

async function publishToCommunity(crate_name, selected) {
  const tag = $("community_tag").value.trim();
  const display_name = $("community_display_name").value.trim();
  const tracks = selected.map((t) => ({ artist: t.artist, title: t.title }));

  setStatus($("community_status"), "Publishing...");
  try {
    await postJSON("/api/publish_crate", { crate_name, tracks, tag, display_name });
    setStatus($("community_status"), "Published to the Community feed.");
  } catch (err) {
    setStatus($("community_status"), err.message, true);
  }
}

async function buildCrate(overwrite = false) {
  const serato_dir = $("serato_dir").value.trim();
  const crate_name = $("crate_name").value.trim();
  const selected = selectedMatchedTracks();
  const track_paths = selected.map((t) => t.path);

  if (!crate_name) {
    setStatus($("build_status"), "Enter a crate name first.", true);
    return;
  }
  if (track_paths.length === 0) {
    setStatus($("build_status"), "No tracks selected.", true);
    return;
  }

  setStatus($("build_status"), "Building...");
  try {
    const data = await postJSON("/api/build", { serato_dir, crate_name, track_paths, overwrite });
    setStatus($("build_status"), `Crate written: ${data.path} (${data.track_count} tracks). Restart Serato (or rescan) to see it.`);
    if ($("community_publish").checked) {
      await publishToCommunity(crate_name, selected);
    }
  } catch (err) {
    if (err.message === "exists") {
      if (confirm("A crate with that name already exists. Overwrite it?")) {
        buildCrate(true);
      } else {
        setStatus($("build_status"), "Cancelled.");
      }
    } else {
      setStatus($("build_status"), err.message, true);
    }
  }
}

$("build_btn").addEventListener("click", () => buildCrate(false));

function downloadMissingLog() {
  const checkboxes = document.querySelectorAll('#results_table input[type="checkbox"]');
  const missing = [];
  checkboxes.forEach((cb) => {
    if (!cb.checked) {
      const m = lastMatches[Number(cb.dataset.index)];
      missing.push({ artist: m.input_artist, title: m.input_title, raw: m.raw });
    }
  });

  if (missing.length === 0) {
    setStatus($("build_status"), "Nothing unchecked — no missing tracks to log.");
    return;
  }

  // A real <form> POST (not fetch()+blob+synthetic click), so the
  // response's Content-Disposition: attachment header triggers a genuine
  // browser/webview-native download. The packaged desktop app's embedded
  // webview doesn't reliably handle a blob: URL clicked via JS — it just
  // displays the raw CSV in place instead of downloading it. Submitting
  // into the hidden "download_frame" iframe (rather than the top-level
  // window) keeps that navigation contained there too, so even a webview
  // that renders the CSV instead of downloading it does so off-screen —
  // the main page, your matches, and your selections never move.
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/api/missing-log";
  form.target = "download_frame";
  form.style.display = "none";

  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "tracks_json";
  input.value = JSON.stringify(missing);
  form.appendChild(input);

  document.body.appendChild(form);
  form.submit();
  form.remove();

  setStatus($("build_status"), `Logged ${missing.length} missing track(s).`);
}

$("missing_log_btn").addEventListener("click", downloadMissingLog);

const SPOTIFY_PLAYLIST_URL_PATTERN = /open\.spotify\.com\/playlist\/[a-zA-Z0-9]+|spotify:playlist:[a-zA-Z0-9]+/;

$("year_genre_btn").addEventListener("click", async () => {
  const input_text = $("input_text").value.trim();
  if (!SPOTIFY_PLAYLIST_URL_PATTERN.test(input_text)) {
    setStatus($("year_genre_status"), "Paste a Spotify playlist URL first — year/genre data only comes from Spotify.", true);
    return;
  }

  // Genre means one Spotify API call per unique artist in the playlist —
  // slow enough for a big playlist that this is worth its own status
  // message rather than looking hung.
  setStatus($("year_genre_status"), "Fetching from Spotify — checking every artist individually, can take a bit for a big playlist...");
  try {
    const data = await postJSON("/api/spotify/year-genre", { input_text });
    setStatus($("year_genre_status"), `Fetched ${data.count} track(s). Downloading...`);
    downloadYearGenreCsv(data.tracks);
  } catch (err) {
    setStatus($("year_genre_status"), err.message, true);
  }
});

function downloadYearGenreCsv(tracks) {
  // Same hidden-iframe <form> POST pattern as downloadMissingLog() above —
  // the data's already fetched, this step just turns it into a real
  // native file download without navigating the main page.
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/api/spotify/year-genre-log";
  form.target = "download_frame";
  form.style.display = "none";

  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "tracks_json";
  input.value = JSON.stringify(tracks);
  form.appendChild(input);

  document.body.appendChild(form);
  form.submit();
  form.remove();
}

$("sync_showfile_btn").addEventListener("click", async () => {
  const event_code = $("showfile_code").value.trim();
  const tracks = selectedMatchedTracks().map((t) => ({ artist: t.artist, title: t.title }));

  if (!event_code) {
    setStatus($("sync_showfile_status"), "Enter a Showfile event code first.", true);
    return;
  }
  if (tracks.length === 0) {
    setStatus($("sync_showfile_status"), "No matched tracks selected.", true);
    return;
  }

  setStatus($("sync_showfile_status"), "Syncing...");
  try {
    const data = await postJSON("/api/sync_showfile", { event_code, tracks });
    setStatus($("sync_showfile_status"), `Synced ${data.count} tracks to Showfile.`);
  } catch (err) {
    setStatus($("sync_showfile_status"), err.message, true);
  }
});

// MyEvents/Discover/Community are just sources — they hand off a tracklist
// (and optionally which Showfile event it belongs to) here rather than
// each having their own matching UI.
const handoff = consumeCrateBuilderHandoff();
if (handoff && handoff.input_text) {
  $("input_text").value = handoff.input_text;
  if (handoff.showfile_event_code) {
    $("showfile_code").value = handoff.showfile_event_code;
  }
  $("preview_btn").click();
}

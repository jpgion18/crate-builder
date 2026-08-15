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
  setStatus($("scan_status"), "Scanning...");
  try {
    const data = await postJSON("/api/scan", { library_dir });
    setStatus($("scan_status"), `Found ${data.track_count} tracks.`);
  } catch (err) {
    setStatus($("scan_status"), err.message, true);
  }
});

$("preview_btn").addEventListener("click", async () => {
  const library_dir = $("library_dir").value.trim();
  const input_text = $("input_text").value;
  const threshold = Number(thresholdInput.value);

  setStatus($("preview_status"), "Matching...");
  $("build_status").textContent = "";
  try {
    const data = await postJSON("/api/preview", { library_dir, input_text, threshold });
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
    renderMatchCell(matchTd, m.track);
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

function renderMatchCell(td, track) {
  if (!track) {
    td.innerHTML = `<span class="track-sub">no match found</span>`;
    return;
  }
  td.innerHTML = `<span class="track-line">${escapeHtml(track.title)}</span><span class="track-sub">${escapeHtml(track.artist)} — ${escapeHtml(track.path)}</span>`;
}

async function showManualSearch(actionTd, index, matchObj) {
  let box = actionTd.querySelector(".manual-search");
  if (box) {
    box.remove();
    return;
  }
  box = document.createElement("div");
  box.className = "manual-search";
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "search library...";
  input.value = `${matchObj.input_artist} ${matchObj.input_title}`.trim();
  box.appendChild(input);
  actionTd.appendChild(box);

  const resultsDiv = document.createElement("div");
  resultsDiv.className = "manual-results";
  actionTd.appendChild(resultsDiv);

  const runSearch = async () => {
    const library_dir = $("library_dir").value.trim();
    const q = input.value.trim();
    if (!q) return;
    const res = await fetch(
      `/api/search?library_dir=${encodeURIComponent(library_dir)}&q=${encodeURIComponent(q)}`
    );
    const data = await res.json();
    resultsDiv.innerHTML = "";
    (data.results || []).forEach((r) => {
      const div = document.createElement("div");
      div.className = "manual-result";
      div.textContent = `${r.title} — ${r.artist} (${r.score})`;
      div.addEventListener("click", () => {
        lastMatches[index].track = { path: r.path, artist: r.artist, title: r.title, album: "" };
        lastMatches[index].matched = true;
        const row = actionTd.closest("tr");
        row.classList.remove("unmatched");
        row.querySelector('input[type="checkbox"]').checked = true;
        renderMatchCell(row.querySelector('[data-role="match-cell"]'), lastMatches[index].track);
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

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function selectedMatchedTracks() {
  const checkboxes = document.querySelectorAll('#results_table input[type="checkbox"]');
  const tracks = [];
  checkboxes.forEach((cb) => {
    if (cb.checked) {
      const m = lastMatches[Number(cb.dataset.index)];
      if (m.track) tracks.push(m.track);
    }
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
  // displays the raw CSV in place instead of downloading it, with no way
  // back. Same reasoning as Discover's "Download Log" button, which
  // already uses a real navigation (a GET, since it needs no request body)
  // and works correctly.
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/api/missing-log";
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

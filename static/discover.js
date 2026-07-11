const $ = (id) => document.getElementById(id);

const thresholdInput = $("threshold");
const thresholdValue = $("threshold_value");
thresholdInput.addEventListener("input", () => {
  thresholdValue.textContent = thresholdInput.value;
});

let lastCandidates = [];
let lastLogEntries = [];

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

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
    // best-effort
  }
}

$("spotify_connect_btn").addEventListener("click", () => {
  window.location.href = "/login";
});

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

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

$("preview_btn").addEventListener("click", async () => {
  const library_dir = $("library_dir").value.trim();
  const input_text = $("input_text").value;
  const threshold = Number(thresholdInput.value);

  setStatus($("preview_status"), "Checking against your library...");
  $("add_status").textContent = "";
  try {
    const data = await postJSON("/api/discover/preview", { library_dir, input_text, threshold });
    lastCandidates = data.candidates;
    renderCandidates();
    const newCount = lastCandidates.filter((c) => !c.in_library && !c.already_logged).length;
    setStatus($("preview_status"), `${newCount} new (not in library, not already logged) of ${lastCandidates.length} parsed.`);
  } catch (err) {
    setStatus($("preview_status"), err.message, true);
    $("results_panel").classList.add("hidden");
  }
});

function renderCandidates() {
  const panel = $("results_panel");
  panel.classList.remove("hidden");
  $("results_summary").textContent = `${lastCandidates.length} tracks parsed`;

  const tbody = document.querySelector("#results_table tbody");
  tbody.innerHTML = "";

  lastCandidates.forEach((c, i) => {
    const tr = document.createElement("tr");
    const isNew = !c.in_library && !c.already_logged;
    if (!isNew) tr.classList.add("unmatched");

    const checkboxTd = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = isNew;
    checkbox.dataset.index = i;
    checkboxTd.appendChild(checkbox);
    tr.appendChild(checkboxTd);

    const trackTd = document.createElement("td");
    trackTd.innerHTML = `<span class="track-line">${escapeHtml(c.title || c.raw)}</span><span class="track-sub">${escapeHtml(c.artist)}</span>`;
    tr.appendChild(trackTd);

    const statusTd = document.createElement("td");
    if (c.in_library) statusTd.textContent = "Already in library";
    else if (c.already_logged) statusTd.textContent = "Already logged";
    else statusTd.textContent = "New";
    tr.appendChild(statusTd);

    tbody.appendChild(tr);
  });
}

$("add_btn").addEventListener("click", async () => {
  const source = $("source_label").value.trim();
  const checkboxes = document.querySelectorAll('#results_table input[type="checkbox"]');
  const entries = [];
  checkboxes.forEach((cb) => {
    if (cb.checked) {
      const c = lastCandidates[Number(cb.dataset.index)];
      entries.push({ artist: c.artist, title: c.title, raw: c.raw });
    }
  });

  if (entries.length === 0) {
    setStatus($("add_status"), "Nothing selected.", true);
    return;
  }

  setStatus($("add_status"), "Adding...");
  try {
    const data = await postJSON("/api/discover/add", { entries, source });
    setStatus($("add_status"), `Added ${data.added_count}, skipped ${data.skipped_count} duplicate(s).`);
    loadLog();
  } catch (err) {
    setStatus($("add_status"), err.message, true);
  }
});

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

async function loadLog() {
  const res = await fetch("/api/discover/list");
  const data = await res.json();
  lastLogEntries = data.entries || [];
  renderLog();
}

function renderLog() {
  const tbody = document.querySelector("#log_table tbody");
  tbody.innerHTML = "";

  lastLogEntries.forEach((entry) => {
    const tr = document.createElement("tr");

    const trackTd = document.createElement("td");
    trackTd.innerHTML = `<span class="track-line">${escapeHtml(entry.title)}</span><span class="track-sub">${escapeHtml(entry.artist)}</span>`;
    tr.appendChild(trackTd);

    const sourceTd = document.createElement("td");
    sourceTd.textContent = entry.source;
    tr.appendChild(sourceTd);

    const dateTd = document.createElement("td");
    dateTd.textContent = formatDate(entry.date_added);
    tr.appendChild(dateTd);

    const statusTd = document.createElement("td");
    const select = document.createElement("select");
    ["new", "acquired", "dismissed"].forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      if (s === entry.status) opt.selected = true;
      select.appendChild(opt);
    });
    select.addEventListener("change", async () => {
      try {
        await postJSON("/api/discover/status", { id: entry.id, status: select.value });
      } catch (err) {
        setStatus($("log_status"), err.message, true);
      }
    });
    statusTd.appendChild(select);
    tr.appendChild(statusTd);

    const actionTd = document.createElement("td");
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async () => {
      const res = await fetch(`/api/discover/${entry.id}`, { method: "DELETE" });
      if (res.ok) loadLog();
    });
    actionTd.appendChild(deleteBtn);
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });
}

$("export_btn").addEventListener("click", () => {
  if (lastLogEntries.length === 0) {
    setStatus($("log_status"), "Discovery log is empty.", true);
    return;
  }
  window.location.href = "/api/discover/export";
});

refreshSpotifyStatus();
loadLog();

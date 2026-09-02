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
  $("log_select_all").checked = false;

  lastLogEntries.forEach((entry) => {
    const tr = document.createElement("tr");

    const checkboxTd = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "log_sel";
    checkbox.dataset.id = entry.id;
    checkbox.checked = entry.status === "new";
    checkboxTd.appendChild(checkbox);
    tr.appendChild(checkboxTd);

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
  // Loaded into the hidden "download_frame" iframe rather than navigating
  // the page itself — a top-level window.location.href here would leave
  // no way back to the log/Sources state if the packaged app's webview
  // doesn't treat the CSV response as a download. See app.js's
  // downloadMissingLog() for the same reasoning.
  document.getElementById("download_frame").src = "/api/discover/export";
});

$("log_select_all").addEventListener("change", () => {
  const checked = $("log_select_all").checked;
  document.querySelectorAll(".log_sel").forEach((cb) => (cb.checked = checked));
});

$("build_crate_from_log_btn").addEventListener("click", () => {
  const ids = Array.from(document.querySelectorAll(".log_sel:checked")).map((cb) => cb.dataset.id);
  const selected = lastLogEntries.filter((e) => ids.includes(e.id));
  if (selected.length === 0) {
    setStatus($("log_status"), "Select at least one track from the log first.", true);
    return;
  }
  const text = selected.map((e) => (e.artist ? `${e.artist} - ${e.title}` : e.title)).join("\n");
  sendToCrateBuilder(text);
});

$("build_crate_btn").addEventListener("click", () => {
  const input_text = $("input_text").value.trim();
  if (!input_text) {
    setStatus($("preview_status"), "Paste a tracklist first.", true);
    return;
  }
  sendToCrateBuilder(input_text);
});

// ---- Sources (bookmarked, organized by gig-type category) ----

let categories = [];
let sources = [];
let suggested = [];
let activeCategory = null;

function renderCategoryTabs() {
  const el = $("category_tabs");
  el.innerHTML = categories
    .map((c) => `<div class="tab ${c === activeCategory ? "active" : ""}" data-category="${escapeHtml(c)}">${escapeHtml(c)}</div>`)
    .join("");
  el.querySelectorAll("[data-category]").forEach((tab) => {
    tab.addEventListener("click", () => {
      activeCategory = tab.dataset.category;
      renderCategoryTabs();
      renderSourcesList();
      renderSuggestedList();
      renderSavedSourceSelect();
    });
  });
}

function renderSourcesList() {
  const el = $("sources_list");
  const list = sources.filter((s) => s.category === activeCategory);
  if (!list.length) {
    el.innerHTML = `<p class="subtitle">No sources saved for ${escapeHtml(activeCategory || "")} yet.</p>`;
    return;
  }
  el.innerHTML = list
    .map(
      (s) => `
    <div class="source-row">
      <span class="source-name">${escapeHtml(s.name)}</span>
      <span class="source-type">${escapeHtml(s.type)}</span>
      ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">open</a>` : ""}
      <button type="button" class="secondary" data-remove-source="${s.id}">Remove</button>
    </div>`
    )
    .join("");
  el.querySelectorAll("[data-remove-source]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/discover/sources/${btn.dataset.removeSource}`, { method: "DELETE" });
      loadSources();
    });
  });
}

function renderSuggestedList() {
  const el = $("suggested_list");
  const list = suggested.filter((s) => s.category === activeCategory);
  el.innerHTML = list
    .map((s) => `<span class="suggested-chip" data-suggested-index="${suggested.indexOf(s)}">+ ${escapeHtml(s.name)}</span>`)
    .join("");
  el.querySelectorAll("[data-suggested-index]").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const s = suggested[Number(chip.dataset.suggestedIndex)];
      try {
        await postJSON("/api/discover/sources", { name: s.name, url: s.url, type: s.type, category: s.category });
        loadSources();
      } catch (err) {
        setStatus($("source_status"), err.message, true);
      }
    });
  });
}

function renderSavedSourceSelect() {
  const sel = $("saved_source_select");
  const list = sources.filter((s) => s.category === activeCategory);
  sel.innerHTML =
    `<option value="">— pick a saved source —</option>` +
    list.map((s) => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}</option>`).join("");
}

$("saved_source_select").addEventListener("change", () => {
  if ($("saved_source_select").value) {
    $("source_label").value = $("saved_source_select").value;
  }
});

$("add_source_btn").addEventListener("click", async () => {
  const name = $("new_source_name").value.trim();
  const url = $("new_source_url").value.trim();
  const type = $("new_source_type").value;
  if (!name) {
    setStatus($("source_status"), "Name your source first.", true);
    return;
  }
  try {
    await postJSON("/api/discover/sources", { name, url, type, category: activeCategory });
    $("new_source_name").value = "";
    $("new_source_url").value = "";
    setStatus($("source_status"), "Source added.");
    loadSources();
  } catch (err) {
    setStatus($("source_status"), err.message, true);
  }
});

async function loadSources() {
  const res = await fetch("/api/discover/sources");
  const data = await res.json();
  sources = data.sources || [];
  suggested = data.suggested || [];
  categories = data.categories || [];
  if (!activeCategory || !categories.includes(activeCategory)) {
    activeCategory = categories[0] || null;
  }
  renderCategoryTabs();
  renderSourcesList();
  renderSuggestedList();
  renderSavedSourceSelect();
}

refreshSpotifyStatus();
loadLog();
loadSources();

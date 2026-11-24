const $ = (id) => document.getElementById(id);

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function libraryDir() {
  return $("library_dir").value.trim();
}

function seratoDir() {
  return $("serato_dir").value.trim();
}

// ---- Duplicate finder ----

$("scan_dupes_btn").addEventListener("click", async () => {
  const serato_dir = seratoDir();
  if (!serato_dir) {
    setStatus($("dupes_status"), "Set your Serato folder first.", true);
    return;
  }
  setStatus($("dupes_status"), "Scanning...");
  setStatus($("dupes_remove_status"), "");
  $("dupes_results").innerHTML = "";
  try {
    const res = await fetch("/api/duplicates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serato_dir }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Scan failed");
    renderDuplicateGroups(data.groups || []);
    setStatus(
      $("dupes_status"),
      data.groups.length ? `${data.groups.length} possible duplicate group(s) found.` : "No duplicates found."
    );
  } catch (err) {
    setStatus($("dupes_status"), err.message, true);
  }
});

function trackAnnotation(t) {
  const bits = [t.year || "no year", t.key || "no key", `energy ${t.energy ?? "—"}`];
  if (t.source) bits.push(t.source);
  return bits.join(" · ");
}

function formatSize(bytes) {
  if (bytes == null) return "file missing";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// One entry per rendered group: { group, selected, keep }.
let dupeChoices = [];

function renderDuplicateGroups(groups) {
  const container = $("dupes_results");
  container.innerHTML = "";
  hideDupesConfirm();
  // Exact matches start ticked; "likely" (fuzzy) matches start unticked so
  // nothing a human hasn't looked at gets queued for removal by default.
  dupeChoices = groups.map((group) => ({
    group,
    selected: group.reason === "exact",
    keep: group.suggested_keep || group.tracks[0].path,
  }));
  $("dupes_actions").classList.toggle("hidden", groups.length === 0);

  dupeChoices.forEach((choice, gi) => {
    const { group } = choice;
    const div = document.createElement("div");
    div.className = "crate";

    const header = document.createElement("div");
    header.className = "crate-header";
    header.innerHTML = `
      <label>
        <input type="checkbox" data-group="${gi}" ${choice.selected ? "checked" : ""} />
        <span class="crate-tag">${group.reason === "exact" ? "exact match" : "likely match"}</span>
        <span class="crate-title">${escapeHtml(group.tracks[0].artist)} – ${escapeHtml(group.tracks[0].title)}</span>
      </label>
      <span class="crate-meta">${group.tracks.length} copies</span>
    `;
    div.appendChild(header);

    const list = document.createElement("div");
    list.className = "crate-tracks";
    group.tracks.forEach((t, ti) => {
      const row = document.createElement("label");
      row.className = "dupe-row";
      row.innerHTML = `
        <input type="radio" name="keep_${gi}" value="${ti}" ${t.path === choice.keep ? "checked" : ""} title="Keep this copy" />
        <span>
          <span class="dupe-path">${escapeHtml(t.path)}</span><br />
          <span class="dupe-meta">${escapeHtml(trackAnnotation(t))} · ${formatSize(t.file_size)} · in ${t.crate_count} crate(s)</span>
        </span>
      `;
      row.querySelector("input").addEventListener("change", () => {
        choice.keep = t.path;
        refreshGroupRows(div, choice);
        hideDupesConfirm();
      });
      list.appendChild(row);
    });
    div.appendChild(list);

    header.querySelector("input[type=checkbox]").addEventListener("change", (e) => {
      choice.selected = e.target.checked;
      refreshGroupRows(div, choice);
      hideDupesConfirm();
    });

    refreshGroupRows(div, choice);
    container.appendChild(div);
  });
}

function refreshGroupRows(div, choice) {
  div.querySelectorAll(".dupe-row").forEach((row, ti) => {
    const t = choice.group.tracks[ti];
    row.classList.toggle("removing", choice.selected && t.path !== choice.keep);
  });
}

function selectedPlans() {
  return dupeChoices
    .filter((c) => c.selected)
    .map((c) => ({ keep: c.keep, remove: c.group.tracks.map((t) => t.path).filter((p) => p !== c.keep) }))
    .filter((p) => p.remove.length);
}

function hideDupesConfirm() {
  $("dupes_confirm").classList.add("hidden");
}

$("dupes_review_btn").addEventListener("click", () => {
  const plans = selectedPlans();
  if (!plans.length) {
    setStatus($("dupes_remove_status"), "Tick at least one group first.", true);
    return;
  }
  setStatus($("dupes_remove_status"), "");
  const removeCount = plans.reduce((n, p) => n + p.remove.length, 0);
  const moving = $("dupes_file_action").value === "move";
  const lines = [
    `${removeCount} track(s) will be removed from Serato across ${plans.length} group(s).`,
    "Crates that had a removed copy will get the kept copy instead.",
    moving
      ? "Their files will be moved to the Crate Builder Removed Duplicates folder (not deleted)."
      : "Their files will stay where they are on disk.",
    "Your Serato database and crates are backed up first; undo from Past cleanups.",
    "Make sure Serato DJ is closed.",
    "",
    ...plans.flatMap((p) => [`KEEP    ${p.keep}`, ...p.remove.map((r) => `REMOVE  ${r}`), ""]),
  ];
  $("dupes_summary").textContent = lines.join("\n");
  $("dupes_confirm").classList.remove("hidden");
});

$("dupes_cancel_btn").addEventListener("click", hideDupesConfirm);

$("dupes_confirm_btn").addEventListener("click", async () => {
  const plans = selectedPlans();
  $("dupes_confirm_btn").disabled = true;
  setStatus($("dupes_remove_status"), "Backing up and removing...");
  try {
    const res = await fetch("/api/duplicates/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serato_dir: seratoDir(), file_action: $("dupes_file_action").value, groups: plans }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Removal failed");
    hideDupesConfirm();
    let msg = `Removed ${data.removed_from_database} track(s) from Serato, updated ${data.crates_updated.length} crate(s)`;
    if (data.files_moved.length) msg += `, moved ${data.files_moved.length} file(s) to ${data.removed_folder}`;
    msg += ".";
    if (data.file_errors.length) msg += ` ${data.file_errors.length} file problem(s): ${data.file_errors.join("; ")}`;
    setStatus($("dupes_remove_status"), msg, data.file_errors.length > 0);
    $("dupes_results").innerHTML = "";
    setStatus($("dupes_status"), "Scan again to check what's left.");
    dupeChoices = [];
    loadSeratoBackups();
  } catch (err) {
    setStatus($("dupes_remove_status"), err.message, true);
  } finally {
    $("dupes_confirm_btn").disabled = false;
  }
});

function formatBackupId(id) {
  // 20261124-013000-123456 -> 2026-11-24 01:30
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id || "");
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : id;
}

async function loadSeratoBackups() {
  const res = await fetch("/api/duplicates/backups");
  const data = await res.json();
  const tbody = document.querySelector("#serato_backups_table tbody");
  tbody.innerHTML = "";
  const backups = data.backups || [];
  backups.forEach((b) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(formatBackupId(b.backup_id))}</td><td>${b.removed_count}</td><td>${b.moved_count}</td><td></td>`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary";
    btn.textContent = b.restored ? "Undone" : "Undo";
    btn.disabled = b.restored;
    btn.addEventListener("click", async () => {
      setStatus($("serato_backups_status"), "Restoring Serato library...");
      try {
        const res = await fetch("/api/duplicates/undo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ backup_id: b.backup_id }),
        });
        const out = await res.json();
        if (!res.ok) throw new Error(out.error || "Undo failed");
        const problems = out.file_errors || [];
        setStatus(
          $("serato_backups_status"),
          problems.length ? `Restored, but: ${problems.join("; ")}` : "Restored. Open Serato to check.",
          problems.length > 0
        );
        loadSeratoBackups();
      } catch (err) {
        setStatus($("serato_backups_status"), err.message, true);
      }
    });
    tr.lastElementChild.appendChild(btn);
    tbody.appendChild(tr);
  });
  if (!backups.length) setStatus($("serato_backups_status"), "No cleanups yet.");
  else if ($("serato_backups_status").textContent === "No cleanups yet.") setStatus($("serato_backups_status"), "");
}

$("refresh_serato_backups_btn").addEventListener("click", loadSeratoBackups);
loadSeratoBackups();

// ---- Metadata editor ----

let currentEditPath = null;

$("metadata_search_btn").addEventListener("click", async () => {
  const library_dir = libraryDir();
  const q = $("metadata_search").value.trim();
  const container = $("metadata_search_results");
  container.innerHTML = "";
  if (!library_dir || !q) return;

  const res = await fetch(`/api/search?library_dir=${encodeURIComponent(library_dir)}&q=${encodeURIComponent(q)}`);
  const data = await res.json();
  const resultsDiv = document.createElement("div");
  resultsDiv.className = "manual-results";
  (data.results || []).forEach((r) => {
    const row = document.createElement("div");
    row.className = "manual-result";
    row.textContent = `${r.artist} – ${r.title}`;
    row.addEventListener("click", () => loadTrackForEditing(r.path, `${r.artist} – ${r.title}`));
    resultsDiv.appendChild(row);
  });
  container.appendChild(resultsDiv);
});

async function loadTrackForEditing(path, label) {
  const res = await fetch(`/api/metadata?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!res.ok) {
    setStatus($("save_tags_status"), data.error || "Couldn't load tags", true);
    return;
  }
  currentEditPath = path;
  $("metadata_edit_title").textContent = label;
  $("tag_title").value = data.tags.title || "";
  $("tag_artist").value = data.tags.artist || "";
  $("tag_album").value = data.tags.album || "";
  $("tag_genre").value = data.tags.genre || "";
  $("tag_date").value = data.tags.date || "";
  $("tag_tracknumber").value = data.tags.tracknumber || "";
  setStatus($("save_tags_status"), "");
  $("metadata_edit_panel").classList.remove("hidden");
}

$("save_tags_btn").addEventListener("click", async () => {
  if (!currentEditPath) return;
  setStatus($("save_tags_status"), "Saving...");
  try {
    const res = await fetch("/api/metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: currentEditPath,
        fields: {
          title: $("tag_title").value,
          artist: $("tag_artist").value,
          album: $("tag_album").value,
          genre: $("tag_genre").value,
          date: $("tag_date").value,
          tracknumber: $("tag_tracknumber").value,
        },
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save failed");
    setStatus($("save_tags_status"), "Saved — original backed up.");
    loadBackups();
  } catch (err) {
    setStatus($("save_tags_status"), err.message, true);
  }
});

// ---- Backups ----

async function loadBackups() {
  setStatus($("backups_status"), "");
  const res = await fetch("/api/metadata/backups");
  const data = await res.json();
  const tbody = document.querySelector("#backups_table tbody");
  tbody.innerHTML = "";
  (data.backups || []).forEach((b) => {
    const tr = document.createElement("tr");

    const whenTd = document.createElement("td");
    whenTd.textContent = b.backed_up_at;
    tr.appendChild(whenTd);

    const fileTd = document.createElement("td");
    fileTd.textContent = b.original_path;
    tr.appendChild(fileTd);

    const actionTd = document.createElement("td");
    const restoreBtn = document.createElement("button");
    restoreBtn.type = "button";
    restoreBtn.className = "secondary";
    restoreBtn.textContent = "Restore";
    restoreBtn.addEventListener("click", async () => {
      setStatus($("backups_status"), "Restoring...");
      try {
        const res = await fetch("/api/metadata/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ backup_path: b.backup_path }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Restore failed");
        setStatus($("backups_status"), "Restored.");
      } catch (err) {
        setStatus($("backups_status"), err.message, true);
      }
    });
    actionTd.appendChild(restoreBtn);
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });
  if (!(data.backups || []).length) {
    setStatus($("backups_status"), "No backups yet.");
  }
}

$("refresh_backups_btn").addEventListener("click", loadBackups);

loadBackups();

// ---- Year check ----

let yearcheckPollHandle = null;
let yearcheckResults = [];

function statusBadge(status) {
  if (status === "match") return `<span class="badge match">match</span>`;
  if (status === "mismatch") return `<span class="badge mismatch">mismatch</span>`;
  return `<span class="badge notfound">${escapeHtml(status)}</span>`;
}

function renderYearCheckResults() {
  const container = $("yearcheck_results");
  if (yearcheckResults.length === 0) {
    container.innerHTML = "";
    return;
  }
  let html = `<table><thead><tr>
    <th>Artist</th><th>Title</th><th>Tag Year</th><th>MB Year</th><th>Score</th><th>Status</th><th></th><th></th>
  </tr></thead><tbody>`;
  yearcheckResults
    .slice()
    .sort((a, b) => (a.status === "mismatch" ? -1 : 1) - (b.status === "mismatch" ? -1 : 1))
    .forEach((r) => {
      const linkCell = r.mb_link ? `<a href="${r.mb_link}" target="_blank" style="color:var(--accent);">view</a>` : "";
      const fixCell =
        r.status === "mismatch"
          ? `<button type="button" class="secondary" data-fix-path="${escapeHtml(r.path)}" data-fix-label="${escapeHtml(`${r.artist} – ${r.title}`)}">Fix in editor</button>`
          : "";
      html += `<tr>
        <td>${escapeHtml(r.artist)}</td>
        <td>${escapeHtml(r.title)}</td>
        <td>${escapeHtml(r.tag_year || "—")}</td>
        <td>${escapeHtml(r.mb_year || "—")}</td>
        <td>${r.score != null ? r.score : "—"}</td>
        <td>${statusBadge(r.status)}</td>
        <td>${linkCell}</td>
        <td>${fixCell}</td>
      </tr>`;
    });
  html += `</tbody></table>`;
  container.innerHTML = html;

  container.querySelectorAll("[data-fix-path]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const path = btn.dataset.fixPath;
      if (!path) {
        setStatus($("yearcheck_status"), "No file path recorded for this track — can't jump to the editor.", true);
        return;
      }
      loadTrackForEditing(path, btn.dataset.fixLabel);
      $("metadata_edit_panel").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });
}

async function loadYearCheckResults() {
  const res = await fetch("/api/yearcheck/results");
  const data = await res.json();
  yearcheckResults = data.results || [];
  renderYearCheckResults();
}

function stopPollingYearCheck() {
  if (yearcheckPollHandle) {
    clearInterval(yearcheckPollHandle);
    yearcheckPollHandle = null;
  }
}

async function pollYearCheckStatus() {
  const res = await fetch("/api/yearcheck/status");
  const data = await res.json();

  const running = data.status === "running";
  $("yearcheck_start_btn").disabled = running;
  $("yearcheck_stop_btn").disabled = !running;

  const pct = data.total ? Math.round((data.checked / data.total) * 100) : 0;
  $("yearcheck_progress").style.width = `${pct}%`;

  if (running) {
    setStatus($("yearcheck_status"), `Checking ${data.checked} / ${data.total}: ${data.current}`);
  } else {
    stopPollingYearCheck();
    setStatus(
      $("yearcheck_status"),
      data.status === "stopped" ? `Stopped after ${data.checked} track(s).` : data.total ? `Done — checked ${data.checked} track(s).` : ""
    );
    loadYearCheckResults();
  }
}

function startPollingYearCheck() {
  if (yearcheckPollHandle) return;
  pollYearCheckStatus();
  yearcheckPollHandle = setInterval(pollYearCheckStatus, 1500);
}

$("yearcheck_start_btn").addEventListener("click", async () => {
  const serato_dir = seratoDir();
  if (!serato_dir) {
    setStatus($("yearcheck_status"), "Set your Serato folder first.", true);
    return;
  }
  const limit = parseInt($("yearcheck_limit").value, 10) || 25;
  try {
    const res = await fetch("/api/yearcheck/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serato_dir, limit }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Couldn't start the check");
    startPollingYearCheck();
  } catch (err) {
    setStatus($("yearcheck_status"), err.message, true);
  }
});

$("yearcheck_stop_btn").addEventListener("click", async () => {
  await fetch("/api/yearcheck/stop", { method: "POST" });
});

// A check might already be running from before this page load (it's a
// server-side background job, not tied to any one browser tab) — pick up
// live progress immediately instead of showing a blank/stale state.
async function initYearCheck() {
  await loadYearCheckResults();
  const res = await fetch("/api/yearcheck/status");
  const data = await res.json();
  if (data.status === "running") {
    startPollingYearCheck();
  }
}

initYearCheck();

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

// ---- Duplicate finder ----

$("scan_dupes_btn").addEventListener("click", async () => {
  const library_dir = libraryDir();
  if (!library_dir) {
    setStatus($("dupes_status"), "Set your music library folder first.", true);
    return;
  }
  setStatus($("dupes_status"), "Scanning...");
  $("dupes_results").innerHTML = "";
  try {
    const res = await fetch("/api/duplicates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ library_dir }),
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

function renderDuplicateGroups(groups) {
  const container = $("dupes_results");
  container.innerHTML = "";
  groups.forEach((group) => {
    const div = document.createElement("div");
    div.className = "crate";

    const header = document.createElement("div");
    header.className = "crate-header";
    header.innerHTML = `
      <div>
        <span class="crate-tag">${group.reason === "exact" ? "exact match" : "likely match"}</span>
        <span class="crate-title">${escapeHtml(group.tracks[0].artist)} – ${escapeHtml(group.tracks[0].title)}</span>
      </div>
      <span class="crate-meta">${group.tracks.length} files</span>
    `;
    div.appendChild(header);

    const list = document.createElement("div");
    list.className = "crate-tracks";
    list.textContent = group.tracks.map((t) => t.path).join("\n");
    div.appendChild(list);

    container.appendChild(div);
  });
}

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

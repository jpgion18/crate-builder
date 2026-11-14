function $(id) {
  return document.getElementById(id);
}

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

let lastReportText = "";

// ---------------------------------------------------------------- help

$("rb_help_btn").addEventListener("click", () => {
  const panel = $("rb_help");
  const open = panel.classList.toggle("hidden") === false;
  $("rb_help_btn").setAttribute("aria-expanded", String(open));
});

// ---------------------------------------------------------------- crate tree

function renderNode(node) {
  const li = document.createElement("li");
  const label = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  if (node.ref) box.dataset.ref = node.ref;
  box.addEventListener("change", () => {
    // Ticking a crate ticks everything nested in it; children can still be unticked alone.
    li.querySelectorAll("ul input[type=checkbox]").forEach((child) => {
      child.checked = box.checked;
    });
  });
  label.appendChild(box);
  label.appendChild(document.createTextNode(" " + node.name));
  if (node.ref) {
    const count = document.createElement("span");
    count.className = "track-count";
    count.textContent = `${node.track_count}`;
    label.appendChild(count);
  }
  li.appendChild(label);
  if (node.children.length) {
    const ul = document.createElement("ul");
    node.children.forEach((child) => ul.appendChild(renderNode(child)));
    li.appendChild(ul);
  }
  return li;
}

async function loadCrates() {
  const serato_dir = $("serato_dir").value.trim();
  const tree = $("rb_crate_tree");
  tree.innerHTML = "";
  setStatus($("rb_crates_status"), "Loading crates...");
  try {
    const res = await fetch(`/api/rekordbox/crates?serato_dir=${encodeURIComponent(serato_dir)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    if (data.count === 0) {
      setStatus($("rb_crates_status"), "No crates found in this Serato folder's Subcrates.", true);
      return;
    }
    const ul = document.createElement("ul");
    data.crates.forEach((node) => ul.appendChild(renderNode(node)));
    tree.appendChild(ul);
    const warn = data.warnings.length ? ` (${data.warnings.join("; ")})` : "";
    setStatus($("rb_crates_status"), `${data.count} crates.${warn}`);
  } catch (err) {
    setStatus($("rb_crates_status"), err.message, true);
  }
}

function setAllChecked(checked) {
  $("rb_crate_tree").querySelectorAll("input[type=checkbox]").forEach((box) => {
    box.checked = checked;
  });
}

function selectedCrates() {
  return Array.from($("rb_crate_tree").querySelectorAll("input[type=checkbox][data-ref]:checked")).map(
    (box) => box.dataset.ref,
  );
}

$("rb_load_btn").addEventListener("click", loadCrates);
$("rb_all_btn").addEventListener("click", () => setAllChecked(true));
$("rb_none_btn").addEventListener("click", () => setAllChecked(false));

// ---------------------------------------------------------------- options

$("rb_mp3_mode").addEventListener("change", () => {
  $("rb_mp3_ms").disabled = $("rb_mp3_mode").value !== "custom";
});

function exportRequest() {
  const mode = $("rb_mp3_mode").value;
  return {
    serato_dir: $("serato_dir").value.trim(),
    crates: selectedCrates(),
    cue_mode: $("rb_cue_mode").value,
    mp3_offset: mode === "custom" ? Number($("rb_mp3_ms").value || 0) : mode,
  };
}

// ---------------------------------------------------------------- results

function cell(text, numeric = false) {
  const td = document.createElement("td");
  td.textContent = text;
  if (numeric) td.className = "num";
  return td;
}

function renderReport(data, saved) {
  const report = data.report;
  lastReportText = data.text;
  const found = report.tracks.filter((t) => t.found);
  const sum = (key) => found.reduce((n, t) => n + t[key], 0);
  const grids = found.filter((t) => t.grid_markers > 0).length;
  const missing = report.tracks.length - found.length;
  $("rb_summary").textContent =
    `${saved ? "Exported" : "Preview (nothing saved yet)"}: ${found.length} of ${report.tracks.length} tracks, ` +
    `${sum("hot_cues")} hot cues, ${sum("memory_cues")} memory cues, ${sum("loops")} loops, ${grids} beatgrids.` +
    (missing ? ` ${missing} missing.` : "");

  const tbody = $("rb_table").querySelector("tbody");
  tbody.innerHTML = "";
  report.tracks.forEach((t) => {
    const tr = document.createElement("tr");
    const label = [t.artist, t.title].filter(Boolean).join(" – ") || t.stored_path.split("/").pop();
    tr.appendChild(cell(!t.found ? "✗" : t.warnings.length ? "!" : "✓"));
    tr.appendChild(cell(t.format || ""));
    tr.appendChild(cell(label));
    tr.appendChild(cell(t.found ? String(t.hot_cues) : "", true));
    tr.appendChild(cell(t.found ? String(t.memory_cues) : "", true));
    tr.appendChild(cell(t.found ? String(t.loops) : "", true));
    tr.appendChild(cell(t.bpm ? t.bpm.toFixed(2) : "", true));
    tr.title = [t.resolved_path || t.stored_path, ...t.warnings, t.mp3_framing ? `MP3: ${t.mp3_framing}` : ""]
      .filter(Boolean)
      .join("\n");
    tbody.appendChild(tr);
  });

  const notes = $("rb_notes");
  notes.innerHTML = "";
  report.tracks.forEach((t) =>
    t.warnings.forEach((w) => {
      const li = document.createElement("li");
      li.textContent = `${t.title || t.stored_path.split("/").pop()}: ${w}`;
      notes.appendChild(li);
    }),
  );
  report.warnings.forEach((w) => {
    const li = document.createElement("li");
    li.textContent = w;
    notes.appendChild(li);
  });
  $("rb_results_panel").classList.remove("hidden");
}

function setBusy(busy) {
  $("rb_preview_btn").disabled = busy;
  $("rb_export_btn").disabled = busy;
}

$("rb_preview_btn").addEventListener("click", async () => {
  setBusy(true);
  setStatus($("rb_status"), "Reading crates and tags...");
  try {
    const data = await window.rekordboxExport.preview(exportRequest());
    renderReport(data, false);
    setStatus($("rb_status"), "Preview ready. Nothing saved yet.");
  } catch (err) {
    setStatus($("rb_status"), err.message, true);
  } finally {
    setBusy(false);
  }
});

$("rb_export_btn").addEventListener("click", async () => {
  setBusy(true);
  setStatus($("rb_status"), "Reading crates and tags...");
  try {
    const data = await window.rekordboxExport.exportCrates(exportRequest());
    renderReport(data, true);
    setStatus($("rb_status"), `${window.crateDownload.describe(data.download, "the XML file")} Press ? for the Rekordbox import steps.`);
  } catch (err) {
    setStatus($("rb_status"), err.message, true);
  } finally {
    setBusy(false);
  }
});

$("rb_copy_btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(lastReportText);
  } catch {
    // Fallback for webviews without the async clipboard API.
    const area = document.createElement("textarea");
    area.value = lastReportText;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  setStatus($("rb_status"), "Report copied.");
});

loadCrates();

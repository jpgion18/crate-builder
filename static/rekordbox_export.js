// Shared by the Rekordbox tab and Build Crate's "Also export to Rekordbox":
// check the export with a dry run first (errors show up as a message instead
// of vanishing), then save the XML (see download.js).

window.rekordboxExport = (() => {
  async function preview(request) {
    const res = await fetch("/api/rekordbox/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
  }

  // Resolves to crateDownload's result ({ saved } / { cancelled } / { started }).
  function download(request) {
    return window.crateDownload("/api/rekordbox/export", {
      serato_dir: request.serato_dir,
      crates_json: JSON.stringify(request.crates),
      cue_mode: request.cue_mode || "both",
      mp3_offset: String(request.mp3_offset ?? "auto"),
    });
  }

  // Returns the preview data, so callers can show what was exported.
  async function exportCrates(request) {
    const data = await preview(request);
    const found = data.report.tracks.filter((t) => t.found).length;
    if (found === 0) {
      throw new Error("None of the tracks in these crates were found on disk, so there's nothing to export.");
    }
    data.download = await download(request);
    return data;
  }

  return { preview, download, exportCrates };
})();

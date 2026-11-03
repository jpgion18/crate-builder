// Shared by the Rekordbox tab and Build Crate's "Also export to Rekordbox":
// check the export with a dry run first (errors show up as a message instead
// of vanishing into the hidden download frame), then download the XML.

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

  function download(request) {
    // Same hidden-iframe <form> POST as the Missing Tracks Log in app.js, so
    // the packaged app's webview shows a real Save dialog.
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/api/rekordbox/export";
    form.target = "download_frame";
    form.style.display = "none";
    const fields = {
      serato_dir: request.serato_dir,
      crates_json: JSON.stringify(request.crates),
      cue_mode: request.cue_mode || "both",
      mp3_offset: String(request.mp3_offset ?? "auto"),
    };
    for (const [name, value] of Object.entries(fields)) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
    form.remove();
  }

  // Returns the preview data, so callers can show what was exported.
  async function exportCrates(request) {
    const data = await preview(request);
    const found = data.report.tracks.filter((t) => t.found).length;
    if (found === 0) {
      throw new Error("None of the tracks in these crates were found on disk, so there's nothing to export.");
    }
    download(request);
    return data;
  }

  return { preview, download, exportCrates };
})();

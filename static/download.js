// Shared by every POST-built download (Rekordbox XML, Missing Tracks Log,
// Year/Genre Breakdown).
//
// The server builds the file and hands back a token. In the packaged app the
// Python side then shows the native Save dialog and writes the file itself
// (desktop_app.SaveApi.save_download), so it never goes through the
// webview's own download handling. On macOS that handling re-fetched the URL
// behind our back and saved a "405 Method Not Allowed" page as the .xml.
// In a plain browser (python app.py) the file is loaded into the hidden
// download_frame, which the browser saves as usual.
//
// Resolves to { saved: path } | { cancelled: true } | { started: true }.
// Throws with the server's message if the file couldn't be built.

window.crateDownload = async function crateDownload(url, fields) {
  const body = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    body.append(name, value);
  }
  const res = await fetch(url, { method: "POST", body, headers: { Accept: "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.token) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }

  const api = window.pywebview && window.pywebview.api;
  if (api && typeof api.save_download === "function") {
    const result = await api.save_download(data.token);
    if (result && result.error) {
      throw new Error(result.error);
    }
    return result || { cancelled: true };
  }

  document.querySelector('iframe[name="download_frame"]').src = data.url;
  return { started: true };
};

// A short status line for the result above.
window.crateDownload.describe = function describe(result, what) {
  if (result.saved) return `Saved ${what} to ${result.saved}.`;
  if (result.cancelled) return `Didn't save ${what}.`;
  return `Downloading ${what}.`;
};

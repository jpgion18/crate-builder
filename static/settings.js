const $ = (id) => document.getElementById(id);

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

document.querySelectorAll("[data-toggle-for]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = $(btn.dataset.toggleFor);
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    btn.textContent = showing ? "Show" : "Hide";
  });
});

function renderConnectionStatus(data) {
  if (data.showfile_business_name) {
    $("connected_view").classList.remove("hidden");
    $("login_view").classList.add("hidden");
    $("connected_label").textContent = `Connected as ${data.showfile_business_name}`;
  } else {
    $("connected_view").classList.add("hidden");
    $("login_view").classList.remove("hidden");
  }
}

async function load() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    $("showfile_url").value = data.showfile_url || "https://www.showfile.events";
    $("showfile_api_key").value = data.showfile_api_key || "";
    $("community_access_code").value = data.community_access_code || "";
    $("community_url").value = data.community_url || "https://crate.showfile.events";
    $("app_version").textContent = `Crate Builder ${data.app_version}`;
    renderConnectionStatus(data);
  } catch (err) {
    setStatus($("save_status"), "Couldn't load current settings.", true);
  }
}

$("save_btn").addEventListener("click", async () => {
  setStatus($("save_status"), "Saving...");
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        showfile_url: $("showfile_url").value.trim(),
        showfile_api_key: $("showfile_api_key").value.trim(),
        community_access_code: $("community_access_code").value.trim(),
        community_url: $("community_url").value.trim(),
      }),
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || "Save failed");
    }
    setStatus($("save_status"), "Saved.");
    load();
  } catch (err) {
    setStatus($("save_status"), err.message, true);
  }
});

$("reconnect_btn").addEventListener("click", () => {
  window.location.href = "/showfile/login";
});

$("disconnect_btn").addEventListener("click", async () => {
  setStatus($("login_status"), "Disconnecting...");
  try {
    const res = await fetch("/api/showfile/disconnect", { method: "POST" });
    if (!res.ok) throw new Error("Disconnect failed");
    setStatus($("login_status"), "Disconnected.");
    load();
  } catch (err) {
    setStatus($("login_status"), err.message, true);
  }
});

async function pollUntilConnected() {
  setStatus($("login_status"), "Waiting for you to finish logging in (opened in your browser)...");
  const deadline = Date.now() + 2 * 60 * 1000; // 2 minutes
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data.showfile_business_name) {
      setStatus($("login_status"), "");
      renderConnectionStatus(data);
      load();
      return;
    }
  }
  setStatus($("login_status"), "Still waiting — try again if the browser tab didn't open.", true);
}

const params = new URLSearchParams(window.location.search);
const loginError = params.get("showfile_error");
const loginPending = params.get("showfile_pending");
window.history.replaceState({}, "", "/settings");

if (loginError) {
  setStatus($("login_status"), `Showfile login failed: ${loginError}`, true);
} else if (loginPending) {
  pollUntilConnected();
}

async function checkForUpdate() {
  try {
    const res = await fetch("/api/update-check");
    const data = await res.json();
    if (!data.update_available) return;
    const btn = $("update_btn");
    // download_url is the direct zip for this OS; falls back to the release
    // page on a platform without a published build (shouldn't normally
    // happen for the packaged app, but keeps the button working either way).
    const url = data.download_url || data.release_url;
    btn.textContent = data.download_url ? `Download update: ${data.latest_version}` : `Update available: ${data.latest_version}`;
    btn.classList.remove("hidden");
    btn.addEventListener("click", () => {
      fetch("/api/open-release", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
    });
  } catch (err) {
    // Best-effort — no banner if the check fails, nothing to show the user.
  }
}

checkForUpdate();

load();

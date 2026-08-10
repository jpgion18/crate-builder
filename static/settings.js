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

async function load() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    $("showfile_url").value = data.showfile_url || "https://www.showfile.events";
    $("showfile_api_key").value = data.showfile_api_key || "";
    $("community_access_code").value = data.community_access_code || "";
    $("community_url").value = data.community_url || "https://crate.showfile.events";
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
  } catch (err) {
    setStatus($("save_status"), err.message, true);
  }
});

load();

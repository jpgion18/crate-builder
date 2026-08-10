const $ = (id) => document.getElementById(id);

const PAGE_SIZE = 20;
let offset = 0;
let total = 0;
let currentQuery = "";
let crates = [];
const expanded = {};

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function trackListText(tracks) {
  return tracks.map((t) => (t.artist ? `${t.artist} - ${t.title}` : t.title)).join("\n");
}

function showNotReady(message) {
  $("not_ready_message").textContent = message;
  $("not_ready_panel").classList.remove("hidden");
  $("search_panel").classList.add("hidden");
}

function showBrowse() {
  $("not_ready_panel").classList.add("hidden");
  $("search_panel").classList.remove("hidden");
}

async function load(nextOffset, query, append) {
  setStatus($("list_status"), "Loading...");
  try {
    const params = new URLSearchParams({ limit: PAGE_SIZE, offset: nextOffset });
    if (query) params.set("q", query);
    const res = await fetch(`/api/community/list?${params}`);
    const data = await res.json();

    if (res.status === 401) {
      showNotReady(`${data.error || "Invalid access code"} — update it in Settings.`);
      return;
    }
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);

    crates = append ? crates.concat(data.crates) : data.crates;
    total = data.total;
    offset = nextOffset;
    currentQuery = query;
    render();
    setStatus($("list_status"), total === 0 ? "No crates published yet." : "");
  } catch (err) {
    setStatus($("list_status"), err.message, true);
  }
}

function render() {
  const panel = $("crates_panel");
  panel.innerHTML = "";

  crates.forEach((crate) => {
    const div = document.createElement("div");
    div.className = "crate";

    const header = document.createElement("div");
    header.className = "crate-header";
    header.innerHTML = `
      <div>
        ${crate.tag ? `<span class="crate-tag">${escapeHtml(crate.tag)}</span>` : ""}
        <span class="crate-title">${escapeHtml(crate.crate_name)}</span>
      </div>
      <span class="crate-meta">${crate.tracks.length} tracks · ${escapeHtml(crate.display_name || "Anonymous")} · ${new Date(crate.created_at).toLocaleDateString()}</span>
    `;
    header.addEventListener("click", () => {
      expanded[crate.id] = !expanded[crate.id];
      render();
    });
    div.appendChild(header);

    if (expanded[crate.id]) {
      const list = document.createElement("div");
      list.className = "crate-tracks";
      list.textContent = trackListText(crate.tracks);
      div.appendChild(list);

      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.textContent = "Copy track list";
      copyBtn.style.marginTop = "0.6rem";
      copyBtn.addEventListener("click", () => navigator.clipboard.writeText(trackListText(crate.tracks)));
      div.appendChild(copyBtn);
    }

    panel.appendChild(div);
  });

  $("load_more_btn").classList.toggle("hidden", crates.length >= total);
}

$("search_btn").addEventListener("click", () => load(0, $("search_input").value.trim(), false));
$("search_input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") load(0, $("search_input").value.trim(), false);
});
$("load_more_btn").addEventListener("click", () => load(offset + PAGE_SIZE, currentQuery, true));

async function init() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  if (!data.community_configured) {
    showNotReady("Connect Showfile in Settings to enable Crate Builder Community.");
  } else if (!data.community_access_code) {
    showNotReady("Add your Showfile access code in Settings to unlock Crate Builder Community.");
  } else {
    showBrowse();
    load(0, "", false);
  }
}

init();

const $ = (id) => document.getElementById(id);

let events = [];
const expanded = {};

function setStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function songsToText(songs) {
  // Free text a couple typed into Showfile's timeline — no guaranteed
  // "Artist - Title" shape, but crate-builder's matcher scores the
  // combined normalized string (order-insensitive), so passing it through
  // as-is works fine without trying to parse artist/title out of it.
  return songs.map((s) => s.song).join("\n");
}

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function render() {
  const container = $("tiles");
  container.innerHTML = "";

  if (events.length === 0) {
    const empty = document.createElement("p");
    empty.className = "status";
    empty.textContent = "No events with songs entered yet.";
    container.appendChild(empty);
    return;
  }

  events.forEach((event) => {
    const newCount = event.songs.filter((s) => s.is_new).length;

    const div = document.createElement("div");
    div.className = "crate";

    const header = document.createElement("div");
    header.className = "crate-header";
    header.innerHTML = `
      <div>
        ${newCount > 0 ? `<span class="crate-tag">${newCount} new</span>` : ""}
        <span class="crate-title">${escapeHtml(event.couple || event.code)}</span>
      </div>
      <span class="crate-meta">${event.songs.length} songs · ${escapeHtml(event.code)} · ${formatDate(event.date)}</span>
    `;
    header.addEventListener("click", () => {
      expanded[event.code] = !expanded[event.code];
      render();
    });
    div.appendChild(header);

    if (expanded[event.code]) {
      const list = document.createElement("div");
      list.className = "crate-tracks";
      list.textContent = event.songs.map((s) => `${s.moment}: ${s.song}${s.is_new ? "  (new)" : ""}`).join("\n");
      div.appendChild(list);

      const matchBtn = document.createElement("button");
      matchBtn.type = "button";
      matchBtn.textContent = "Match this event's songs";
      matchBtn.style.marginTop = "0.6rem";
      matchBtn.addEventListener("click", () => sendToCrateBuilder(songsToText(event.songs), event.code));
      div.appendChild(matchBtn);
    }

    container.appendChild(div);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function showNotReady(message) {
  $("not_ready_message").textContent = message;
  $("not_ready_panel").classList.remove("hidden");
  $("events_panel").classList.add("hidden");
}

function showEvents() {
  $("not_ready_panel").classList.add("hidden");
  $("events_panel").classList.remove("hidden");
}

async function loadCached() {
  const res = await fetch("/api/myevents");
  const data = await res.json();
  events = data.events || [];
  render();
}

$("refresh_btn").addEventListener("click", async () => {
  setStatus($("refresh_status"), "Refreshing...");
  try {
    const res = await fetch("/api/myevents/refresh", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Refresh failed");
    events = data.events || [];
    render();
    setStatus($("refresh_status"), "");
  } catch (err) {
    setStatus($("refresh_status"), err.message, true);
  }
});

async function init() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  if (!data.showfile_configured) {
    showNotReady("Connect Showfile in Settings to see your events.");
    return;
  }
  showEvents();
  await loadCached();
}

init();

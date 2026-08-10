// Shared "send this tracklist to Crate Builder" hand-off, used by MyEvents,
// Discover, and Community — all three are sources that feed the one real
// Crate Builder (the match/review table + Build Crate + Sync to Showfile +
// Publish to Community on the main page), not separate matching engines.
const CRATE_BUILDER_HANDOFF_KEY = "cb_handoff";

function sendToCrateBuilder(inputText, showfileEventCode) {
  localStorage.setItem(
    CRATE_BUILDER_HANDOFF_KEY,
    JSON.stringify({ input_text: inputText, showfile_event_code: showfileEventCode || "" })
  );
  window.location.href = "/";
}

function consumeCrateBuilderHandoff() {
  const raw = localStorage.getItem(CRATE_BUILDER_HANDOFF_KEY);
  if (!raw) return null;
  localStorage.removeItem(CRATE_BUILDER_HANDOFF_KEY);
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

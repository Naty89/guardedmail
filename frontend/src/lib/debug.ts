/** True when the page was opened with ?debug=1 (shows the Judge panel). */
export function isDebug(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  } catch {
    return false;
  }
}

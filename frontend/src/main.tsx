import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";
import { applyPrefs, loadPrefs } from "./lib/prefs";

// Apply the saved text size and contrast before the first paint: no flash of the wrong size.
applyPrefs(loadPrefs());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// The one stylesheet, imported at the entry point so Vite emits it as a
// single CSS asset rather than leaving the app unstyled.
import "@/app/styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Shell } from "@/app/shell";
import { connectCoach, readHandshake } from "@/lib/connection";
import { $connection } from "@/store/session";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

createRoot(root).render(
  <StrictMode>
    <Shell />
  </StrictMode>,
);

// Render first, connect second: the shell shows its own degraded notice while
// this runs, and a failed handshake leaves a usable page rather than a blank
// one.
$connection.set("connecting");
try {
  await connectCoach(readHandshake(window.location));
  $connection.set("online");
} catch {
  $connection.set("offline");
}

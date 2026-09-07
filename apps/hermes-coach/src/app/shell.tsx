/**
 * App shell: landmarks, navigation, and the current route.
 *
 * Accessibility is structural here rather than retrofitted — a skip link, real
 * `nav`/`main` landmarks, `aria-current` on the active link, and a focus target
 * on the main region so keyboard navigation lands somewhere sensible after a
 * route change.
 */

import { useEffect, useRef, useState } from "react";
import { useStore } from "@nanostores/react";

import { $connection, $generationAvailable } from "@/store/session";
import { ROUTES, currentPath, routeFor } from "./routes";

export function Shell() {
  const [path, setPath] = useState(() => currentPath(window.location.hash));
  const mainRef = useRef<HTMLElement>(null);
  const connection = useStore($connection);
  const generationAvailable = useStore($generationAvailable);

  useEffect(() => {
    const onHashChange = () => setPath(currentPath(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const route = routeFor(path);
  const Body = route.component;

  return (
    <div className="coach-shell">
      <a href="#coach-main" className="coach-skip-link">
        Bỏ qua điều hướng
      </a>

      <nav aria-label="Điều hướng chính">
        <ul>
          {ROUTES.map((entry) => (
            <li key={entry.path}>
              <a
                href={`#${entry.path}`}
                aria-current={entry.path === route.path ? "page" : undefined}
              >
                {entry.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {!generationAvailable && (
        // Stated, not implied by a disabled button: local data stays usable,
        // only the coaching turn cannot run.
        <p role="status" data-testid="degraded-notice">
          {connection === "online"
            ? "Phiên coaching tạm dừng."
            : "Chưa kết nối được backend. Dữ liệu đã lưu vẫn xem được; chưa tạo được lượt coaching mới."}
        </p>
      )}

      <main id="coach-main" ref={mainRef} tabIndex={-1}>
        <h1>{route.label}</h1>
        <Body />
      </main>
    </div>
  );
}

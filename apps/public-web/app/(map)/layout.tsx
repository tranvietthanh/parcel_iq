import type { ReactNode } from "react";

/**
 * Full-screen map layout — no header/footer chrome.
 * The global disclaimer footer from root layout is still visible.
 */
export default function MapLayout({ children }: { children: ReactNode }) {
  return <div className="h-[calc(100vh-32px)] w-screen overflow-auto">{children}</div>;
}

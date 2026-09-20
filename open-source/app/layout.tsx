import type { Metadata, Viewport } from "next";
import "./globals.css";

const ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%230b0f14'/%3E%3Ccircle cx='16' cy='16' r='4' fill='%23fff'/%3E%3Ccircle cx='16' cy='16' r='9' fill='none' stroke='%23fff' stroke-width='2' opacity='.5'/%3E%3C/svg%3E";

export const metadata: Metadata = {
  title: "Keiko",
  description: "Live whale detections from the Keiko acoustic buoys.",
  icons: { icon: ICON },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

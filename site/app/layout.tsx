import type { Metadata, Viewport } from "next";
import { Geist, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const display = Geist({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-display", display: "swap" }); // landing page only
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

const ICON = "data:image/svg+xml," + encodeURIComponent(
  "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='16' fill='#0a1420'/><text x='16' y='23' font-size='19' text-anchor='middle'>🐋</text></svg>"
);

export const metadata: Metadata = {
  title: "Keiko",
  description: "Live whale detections from the Keiko acoustic buoys.",
  icons: { icon: ICON },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#0a1420" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable + " " + mono.variable + " " + display.variable}>
      <body>{children}</body>
    </html>
  );
}

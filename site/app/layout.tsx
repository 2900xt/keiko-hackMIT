import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

const ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%230a1420'/%3E%3Ccircle cx='16' cy='16' r='4' fill='%2357b8ec'/%3E%3Ccircle cx='16' cy='16' r='9' fill='none' stroke='%2357b8ec' stroke-width='2' opacity='.5'/%3E%3C/svg%3E";

export const metadata: Metadata = {
  title: "Keiko",
  description: "Live whale detections from the Keiko acoustic buoys.",
  icons: { icon: ICON },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#0a1420" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable + " " + mono.variable}>
      <body>{children}</body>
    </html>
  );
}

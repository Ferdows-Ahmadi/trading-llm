import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Analyst",
  description: "AI-assisted crypto/forex research dashboard (informational only)"
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

/**
 * Root Next.js layout: HTML shell, site metadata, and dashboard chrome.
 */

import type { Metadata } from "next";
import DashboardShell from "@/components/DashboardShell";
import "./globals.css";

/** Default document title and description for the application. */
export const metadata: Metadata = {
  title: "Food Recall Monitor",
  description: "Proof-of-Concept project for monitoring multinational food recall alerts",
};

/**
 * Root layout wrapping all pages with the dashboard shell.
 *
 * @param props.children - Nested route content.
 * @returns HTML document structure.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <DashboardShell>{children}</DashboardShell>
      </body>
    </html>
  );
}

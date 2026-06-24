import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Food Recall Monitor",
  description: "Proof-of-Concept project for monitoring multinational food recall alerts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

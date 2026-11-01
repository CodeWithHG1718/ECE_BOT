import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Signal — ECE study assistant",
  description:
    "A source-led study assistant for IIT Roorkee ECE courses, schedules, exams, and study resources.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

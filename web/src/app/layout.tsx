import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Codeharness",
  description: "Multi-user agent platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning translate="no">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

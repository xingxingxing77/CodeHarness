import type { Metadata } from "next";
import "./globals.css";

import { AppShell } from "@/components/shell/AppShell";

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
      <body className="min-h-full flex flex-col">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

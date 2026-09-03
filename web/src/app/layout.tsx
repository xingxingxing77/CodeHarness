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
  const themeInit = "try{if(localStorage.getItem('codeharness_theme')==='dark')document.documentElement.classList.add('dark')}catch(e){}";

  return (
    <html lang="en" className="h-full antialiased">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import { IBM_Plex_Mono, Source_Sans_3, Source_Serif_4 } from "next/font/google";

import "./globals.css";

const display = Source_Serif_4({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const body = Source_Sans_3({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Cursor Predict",
  description: "Select screen and keyboard extraction ranges across tutorial videos",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable} h-full`}>
      <body className="min-h-full font-[family-name:var(--font-body)] antialiased">
        {children}
      </body>
    </html>
  );
}

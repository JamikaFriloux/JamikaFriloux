import type { Metadata } from "next";
import "./globals.css";
import { PaperBanner } from "@/components/paper-banner";

export const metadata: Metadata = {
  title: "ATLAS · Paper",
  description: "ATLAS autonomous trading research system — paper trading console",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">
        <PaperBanner />
        {children}
      </body>
    </html>
  );
}

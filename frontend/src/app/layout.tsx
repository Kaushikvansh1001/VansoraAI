import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { PearlCanvas } from "@/components/pearl-canvas";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "VansoraAI",
  description: "Intelligence. Automation. Evolution.",
};

const themeScript = `
try {
  if (localStorage.getItem("vansora.theme") === "dark") {
    document.documentElement.classList.add("dark");
  }
} catch (error) {}
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} antialiased`}>
        <SessionProvider>
          <PearlCanvas>{children}</PearlCanvas>
        </SessionProvider>
      </body>
    </html>
  );
}

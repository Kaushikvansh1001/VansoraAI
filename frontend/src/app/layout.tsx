import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import { GeistSans } from "geist/font/sans";
import { PearlCanvas } from "@/components/pearl-canvas";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
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
    <html lang="en" className={`${GeistSans.variable} ${manrope.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="antialiased">
        <SessionProvider>
          <PearlCanvas>{children}</PearlCanvas>
        </SessionProvider>
      </body>
    </html>
  );
}

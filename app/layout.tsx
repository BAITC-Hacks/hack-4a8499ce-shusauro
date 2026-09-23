import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Аким на 5 часов — Qala",
  description: "AI-симулятор управления качеством жизни в районах Астаны.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}

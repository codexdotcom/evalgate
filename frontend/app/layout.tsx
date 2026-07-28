import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { Badge, NavLink } from "@/components/ui";
import { api } from "@/lib/api";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "EvalGate",
  description: "LLM evaluation and governance harness",
};

async function pendingReviewCount(): Promise<number | null> {
  // The nav must still render when the API is down, so a failure here is not
  // allowed to take the page with it.
  try {
    return (await api.listReview("pending")).length;
  } catch {
    return null;
  }
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pending = await pendingReviewCount();

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-6xl items-center gap-1 px-6 py-3">
            <Link href="/" className="mr-4 flex items-center gap-2">
              <span className="text-base font-semibold tracking-tight">
                Eval<span className="text-sky-600">Gate</span>
              </span>
            </Link>
            <NavLink href="/">Runs</NavLink>
            <NavLink href="/datasets">Datasets</NavLink>
            <Link
              href="/review"
              className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
            >
              Review
              {pending ? <Badge tone="amber">{pending}</Badge> : null}
            </Link>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
        <footer className="border-t border-line px-6 py-4 text-center text-xs text-muted">
          Low-confidence judgments are escalated, not averaged away.
        </footer>
      </body>
    </html>
  );
}

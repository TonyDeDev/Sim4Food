"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { slug: "setup", label: "Setup" },
  { slug: "upload", label: "Upload" },
  { slug: "waste", label: "Waste" },
  { slug: "planner", label: "Planner" },
  { slug: "results", label: "Results" },
  { slug: "backtest", label: "Backtest" },
] as const;

export function WorkspaceTabs({ businessId }: { businessId: string }) {
  const pathname = usePathname();

  return (
    <nav className="mb-8 flex gap-6 border-b border-press-black">
      {TABS.map((tab) => {
        const href = `/businesses/${businessId}/${tab.slug}`;
        const active = pathname === href;
        return (
          <Link
            key={tab.slug}
            href={href}
            className={`-mb-px border-b py-3 font-sans text-body font-medium tracking-[0.04em] text-press-black ${
              active ? "border-press-black" : "border-transparent text-press-black/50 hover:text-press-black"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

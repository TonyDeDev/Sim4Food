import Link from "next/link";
import type { Business } from "@/lib/auth-context";
import { swatchPalette } from "@/lib/helpers";
import { Tag } from "@/components/ui/Tag";

type Props = {
  biz: Business;
  index: number;
};

export function BusinessCard({ biz, index }: Props) {
  const color = swatchPalette[index % swatchPalette.length];
  const initial = biz.name.trim().slice(0, 2).toUpperCase();

  return (
    <Link
      href={`/businesses/${biz.id}/setup`}
      className="flex flex-col gap-4 rounded-xl border border-press-black bg-manuscript-cream p-5 transition-shadow hover:shadow-sm"
    >
      <div className="flex items-center gap-3">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-press-black font-sans text-body font-bold text-press-black"
          style={{ background: `${color}33` }}
        >
          {initial}
        </div>
        <div>
          <h3 className="font-serif text-subheading font-normal text-press-black">{biz.name}</h3>
          <p className="font-sans text-caption text-press-black/60">Added just now</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Tag accent="lime">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" className="h-3 w-3">
            <path d="M5 13l4 4L19 7" />
          </svg>
          Inventory
        </Tag>
        <Tag accent="cornflower">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" className="h-3 w-3">
            <path d="M5 13l4 4L19 7" />
          </svg>
          Recipes
        </Tag>
        <Tag>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" className="h-3 w-3">
            <path d="M5 13l4 4L19 7" />
          </svg>
          Sales
        </Tag>
      </div>
    </Link>
  );
}

import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  accent?: "lime" | "cornflower";
};

const accentClasses: Record<NonNullable<Props["accent"]>, string> = {
  lime: "bg-highlighter-lime hover:bg-highlighter-lime/80",
  cornflower: "bg-cornflower-wash hover:bg-cornflower-wash/80",
};

export function AccentButton({ accent = "lime", className = "", ...props }: Props) {
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-md border border-press-black px-5 py-3 font-sans text-body font-medium tracking-[0.04em] text-press-black transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${accentClasses[accent]} ${className}`}
      {...props}
    />
  );
}

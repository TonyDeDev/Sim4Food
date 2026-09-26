import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLSpanElement> & {
  accent?: "lime" | "cornflower" | "none";
};

const accentClasses: Record<NonNullable<Props["accent"]>, string> = {
  lime: "bg-highlighter-lime border-press-black",
  cornflower: "bg-cornflower-wash border-press-black",
  none: "bg-transparent border-press-black",
};

export function Tag({ accent = "none", className = "", ...props }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 font-sans text-caption font-bold uppercase tracking-[0.067em] text-press-black ${accentClasses[accent]} ${className}`}
      {...props}
    />
  );
}

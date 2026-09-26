import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLDivElement> & {
  accent?: "lime" | "cornflower" | "spring";
};

const accentClasses: Record<NonNullable<Props["accent"]>, string> = {
  lime: "bg-highlighter-lime",
  cornflower: "bg-cornflower-wash",
  spring: "bg-spring-green",
};

export function AccentCard({ accent = "lime", className = "", ...props }: Props) {
  return (
    <div
      className={`rounded-xl border border-press-black p-5 ${accentClasses[accent]} ${className}`}
      {...props}
    />
  );
}

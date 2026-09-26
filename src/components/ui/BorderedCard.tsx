import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLDivElement>;

export function BorderedCard({ className = "", ...props }: Props) {
  return (
    <div
      className={`rounded-xl border border-press-black bg-manuscript-cream p-5 ${className}`}
      {...props}
    />
  );
}

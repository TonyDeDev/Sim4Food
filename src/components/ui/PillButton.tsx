import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
};

export function PillButton({ active = false, className = "", ...props }: Props) {
  return (
    <button
      className={`inline-flex w-full items-center gap-3 rounded-3xl border border-press-black px-5 py-2 text-left font-sans text-body font-medium tracking-[0.04em] text-press-black transition-colors ${
        active ? "bg-cornflower-wash" : "bg-manuscript-cream hover:bg-paper-shadow"
      } ${className}`}
      {...props}
    />
  );
}

import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement>;

export function OutlinedButton({ className = "", ...props }: Props) {
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-md border border-press-black bg-transparent px-5 py-3 font-sans text-body font-medium tracking-[0.04em] text-press-black transition-colors hover:bg-paper-shadow disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    />
  );
}

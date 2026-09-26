import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement>;

export function GhostButton({ className = "", ...props }: Props) {
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-sm border-none bg-transparent px-1 py-1 font-sans text-body font-medium tracking-[0.04em] text-press-black underline-offset-4 hover:underline ${className}`}
      {...props}
    />
  );
}

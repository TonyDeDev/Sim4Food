import type { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement>;

export function InputField({ className = "", ...props }: Props) {
  return (
    <input
      className={`w-full rounded-md border border-press-black bg-manuscript-cream px-3 py-3 font-sans text-body-lg text-press-black placeholder:text-mist-green focus:border-2 focus:px-[11px] focus:py-[11px] focus:outline-none ${className}`}
      {...props}
    />
  );
}

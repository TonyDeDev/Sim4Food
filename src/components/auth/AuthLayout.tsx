import type { ReactNode } from "react";

type Props = {
  quote: string;
  cite: string;
  children: ReactNode;
};

export function AuthLayout({ quote, cite, children }: Props) {
  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-press-black p-14 text-manuscript-cream md:flex">
        <span className="font-sans text-body font-bold tracking-[0.04em]">SwarmStock</span>
        <div>
          <blockquote className="mb-5 max-w-[22ch] font-serif text-heading-sm font-light leading-tight text-manuscript-cream">
            &ldquo;{quote}&rdquo;
          </blockquote>
          <cite className="font-sans text-body not-italic text-manuscript-cream/70">— {cite}</cite>
        </div>
        <p className="font-sans text-caption text-manuscript-cream/60">© 2026 SwarmStock</p>
      </aside>
      <main className="flex items-center justify-center p-8 md:p-10">
        <div className="w-full max-w-[400px]">{children}</div>
      </main>
    </div>
  );
}

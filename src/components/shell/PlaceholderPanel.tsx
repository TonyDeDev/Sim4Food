type Props = {
  title: string;
  description: string;
};

export function PlaceholderPanel({ title, description }: Props) {
  return (
    <div className="rounded-xl border border-dashed border-press-black p-14 text-center">
      <p className="mb-2 font-serif text-heading-sm font-normal text-press-black">{title}</p>
      <p className="mx-auto max-w-[52ch] font-sans text-body text-press-black/70">{description}</p>
      <p className="mt-6 inline-block rounded-md border border-press-black bg-paper-shadow px-3 py-1 font-sans text-caption font-bold uppercase tracking-[0.067em] text-press-black">
        Coming soon
      </p>
    </div>
  );
}

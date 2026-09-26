"use client";

import { useRef, useState, type FormEvent } from "react";
import { InputField } from "@/components/ui/InputField";
import { OutlinedButton } from "@/components/ui/OutlinedButton";
import { AccentButton } from "@/components/ui/AccentButton";

type FileKey = "inventory" | "recipe" | "sales";

const FIELDS: { key: FileKey; label: string; hint: string }[] = [
  { key: "inventory", label: "Inventory", hint: "Current stock on hand, as a spreadsheet or document." },
  { key: "recipe", label: "Recipes", hint: "Dish names, ingredients, and quantities used." },
  { key: "sales", label: "Sales history", hint: "Sales records since the business opened." },
];

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (fields: { name: string; inventoryFile: string; recipeFile: string; salesFile: string }) => void;
};

export function AddBusinessModal({ open, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<FileKey, File | null>>({
    inventory: null,
    recipe: null,
    sales: null,
  });
  const fileInputRefs = useRef<Record<FileKey, HTMLInputElement | null>>({
    inventory: null,
    recipe: null,
    sales: null,
  });

  if (!open) return null;

  const ready = name.trim() && files.inventory && files.recipe && files.sales;

  function reset() {
    setName("");
    setFiles({ inventory: null, recipe: null, sales: null });
  }

  function handleClose() {
    reset();
    onClose();
  }

  function handleFileChange(key: FileKey, fileList: FileList | null) {
    const file = fileList?.[0] ?? null;
    setFiles((prev) => ({ ...prev, [key]: file }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ready || !files.inventory || !files.recipe || !files.sales) return;
    onSubmit({
      name: name.trim(),
      inventoryFile: files.inventory.name,
      recipeFile: files.recipe.name,
      salesFile: files.sales.name,
    });
    reset();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-press-black/35 p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="max-h-[90vh] w-full max-w-[480px] overflow-y-auto rounded-xl border border-press-black bg-manuscript-cream p-7">
        <h2 className="mb-1 font-serif text-heading-sm font-normal text-press-black">Add a business</h2>
        <p className="mb-6 font-sans text-body text-press-black/70">
          Give it a name and attach its records. You can add more businesses later.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div>
            <label htmlFor="biz-name-input" className="mb-2 block font-sans text-body font-medium text-press-black">
              Business name
            </label>
            <InputField
              id="biz-name-input"
              type="text"
              placeholder="e.g. Millbrook Cafe"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>

          {FIELDS.map(({ key, label, hint }) => (
            <div key={key}>
              <label className="mb-1 block font-sans text-body font-medium text-press-black">{label}</label>
              <p className="mb-2 font-sans text-caption text-press-black/60">{hint}</p>
              <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-press-black/40 bg-paper-shadow p-3">
                <span
                  className={`truncate font-sans text-caption ${
                    files[key] ? "font-medium text-press-black" : "text-press-black/50"
                  }`}
                >
                  {files[key]?.name ?? "No file selected"}
                </span>
                <OutlinedButton
                  type="button"
                  className="shrink-0 px-3! py-2! text-caption!"
                  onClick={() => fileInputRefs.current[key]?.click()}
                >
                  Choose file
                </OutlinedButton>
              </div>
              <input
                type="file"
                className="hidden"
                ref={(el) => {
                  fileInputRefs.current[key] = el;
                }}
                onChange={(e) => handleFileChange(key, e.target.files)}
              />
            </div>
          ))}

          <div className="mt-1 flex justify-end gap-3">
            <OutlinedButton type="button" onClick={handleClose}>
              Cancel
            </OutlinedButton>
            <AccentButton type="submit" disabled={!ready}>
              Add business
            </AccentButton>
          </div>
        </form>
      </div>
    </div>
  );
}

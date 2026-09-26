"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { BusinessCard } from "@/components/businesses/BusinessCard";
import { AddBusinessModal } from "@/components/businesses/AddBusinessModal";
import { AccentButton } from "@/components/ui/AccentButton";

export default function BusinessesPage() {
  const { businesses, addBusiness } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div className="mx-auto max-w-[1200px]">
      <div className="mb-9 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-serif text-heading font-normal leading-none text-press-black">Your businesses</h1>
          <p className="mt-2 font-sans text-body text-press-black/70">
            Add a business to start estimating its food waste.
          </p>
        </div>
        <AccentButton type="button" onClick={() => setModalOpen(true)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add business
        </AccentButton>
      </div>

      {businesses.length === 0 ? (
        <div className="mx-auto mt-10 max-w-[460px] rounded-xl border border-dashed border-press-black p-16 text-center">
          <p className="mb-2 font-serif text-heading-sm font-normal text-press-black">No businesses yet</p>
          <p className="mb-7 font-sans text-body text-press-black/70">
            Add your first business and upload its inventory, recipes, and sales history to get a waste estimate.
          </p>
          <AccentButton type="button" onClick={() => setModalOpen(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Add a business
          </AccentButton>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {businesses.map((biz, i) => (
            <BusinessCard key={biz.id} biz={biz} index={i} />
          ))}
        </div>
      )}

      <AddBusinessModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSubmit={(fields) => {
          addBusiness(fields);
          setModalOpen(false);
        }}
      />
    </div>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { initials, swatchPalette } from "@/lib/helpers";
import { PillButton } from "@/components/ui/PillButton";
import { OutlinedButton } from "@/components/ui/OutlinedButton";
import { AddBusinessModal } from "@/components/businesses/AddBusinessModal";

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, businesses, signOut, addBusiness } = useAuth();
  const [modalOpen, setModalOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;

  function handleSignOut() {
    signOut();
    router.push("/login");
  }

  function goTo(href: string) {
    setMobileOpen(false);
    router.push(href);
  }

  return (
    <>
      <button
        type="button"
        aria-label="Open menu"
        onClick={() => setMobileOpen(true)}
        className="fixed top-5 left-5 z-30 flex h-10 w-10 items-center justify-center rounded-md border border-press-black bg-manuscript-cream md:hidden"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="h-5 w-5">
          <path d="M3 6h18M3 12h18M3 18h18" />
        </svg>
      </button>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-press-black/35 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex h-screen w-72 shrink-0 flex-col border-r border-press-black bg-manuscript-cream p-5 transition-transform duration-200 md:static md:z-auto md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-press-black bg-highlighter-lime font-sans text-body font-medium text-press-black">
            {initials(user.firstName, user.lastName)}
          </div>
          <div className="min-w-0">
            <p className="truncate font-sans text-body font-medium text-press-black">
              {user.firstName} {user.lastName}
            </p>
            <p className="truncate font-sans text-caption text-press-black/60">{user.email}</p>
          </div>
        </div>

        <p className="mb-3 font-sans text-caption font-bold uppercase tracking-[0.067em] text-press-black/50">
          Your businesses
        </p>

        {businesses.length > 0 && (
          <ul className="mb-3 flex max-h-[150px] flex-col gap-2 overflow-y-auto">
            {businesses.map((biz, i) => {
              const color = swatchPalette[i % swatchPalette.length];
              const active = pathname?.startsWith(`/businesses/${biz.id}`);
              return (
                <li key={biz.id}>
                  <PillButton active={active} onClick={() => goTo(`/businesses/${biz.id}/setup`)}>
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-press-black text-[11px] font-bold"
                      style={{ background: `${color}33` }}
                    >
                      {biz.name.trim().slice(0, 2).toUpperCase()}
                    </span>
                    <span className="truncate">{biz.name}</span>
                  </PillButton>
                </li>
              );
            })}
          </ul>
        )}

        <OutlinedButton
          type="button"
          className="mb-6 w-full justify-center"
          onClick={() => setModalOpen(true)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add business
        </OutlinedButton>

        <div className="mt-auto border-t border-sage-border pt-4">
          <Link
            href="/settings"
            onClick={() => setMobileOpen(false)}
            className={`mb-1 flex items-center gap-2 rounded-md px-2 py-2 font-sans text-body text-press-black hover:bg-paper-shadow ${
              pathname === "/settings" ? "underline underline-offset-4" : ""
            }`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4 shrink-0">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 008.6 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H2a2 2 0 010-4h.09A1.65 1.65 0 003.6 8.6a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H8a1.65 1.65 0 001-1.51V2a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V8c.36.18.68.43.94.73" />
            </svg>
            Settings
          </Link>
          <button
            type="button"
            onClick={handleSignOut}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 font-sans text-body text-press-black/70 hover:bg-paper-shadow hover:text-press-black"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-4 w-4 shrink-0">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
              <path d="M16 17l5-5-5-5" />
              <path d="M21 12H9" />
            </svg>
            Sign out
          </button>
        </div>

        <AddBusinessModal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          onSubmit={(fields) => {
            addBusiness(fields);
            setModalOpen(false);
          }}
        />
      </aside>
    </>
  );
}

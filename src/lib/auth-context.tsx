"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { nameFromEmail } from "./helpers";

export type User = {
  firstName: string;
  lastName: string;
  email: string;
};

export type PendingSignup = {
  first: string;
  last: string;
  email: string;
};

export type Business = {
  id: string;
  name: string;
  inventoryFile: string;
  recipeFile: string;
  salesFile: string;
};

type AuthContextValue = {
  user: User | null;
  pendingSignup: PendingSignup | null;
  businesses: Business[];
  login: (email: string) => void;
  signup: (fields: { first: string; last: string; email: string }) => void;
  completeSignup: () => void;
  signOut: () => void;
  addBusiness: (fields: Omit<Business, "id">) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [pendingSignup, setPendingSignup] = useState<PendingSignup | null>(null);
  const [businesses, setBusinesses] = useState<Business[]>([]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      pendingSignup,
      businesses,
      login(email) {
        // No backend yet — derive a placeholder name from the email so the
        // dashboard has something to show. Replace with a real session lookup.
        const derived = nameFromEmail(email);
        setUser({ firstName: derived.first, lastName: derived.last, email });
        setBusinesses([]);
      },
      signup(fields) {
        setPendingSignup(fields);
      },
      completeSignup() {
        setPendingSignup((pending) => {
          if (pending) {
            setUser({ firstName: pending.first, lastName: pending.last, email: pending.email });
            setBusinesses([]);
          }
          return null;
        });
      },
      signOut() {
        setUser(null);
        setBusinesses([]);
        setPendingSignup(null);
      },
      addBusiness(fields) {
        setBusinesses((prev) => [...prev, { id: `biz-${Date.now()}`, ...fields }]);
      },
    }),
    [user, pendingSignup, businesses],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

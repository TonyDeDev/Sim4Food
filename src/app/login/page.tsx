"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { InputField } from "@/components/ui/InputField";
import { GhostButton } from "@/components/ui/GhostButton";
import { AccentButton } from "@/components/ui/AccentButton";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    login(email);
    router.push("/businesses");
  }

  return (
    <AuthLayout
      quote="We finally know where the food was actually going."
      cite="Dana Wu, Millbrook Cafe"
    >
      <h1 className="mb-2 font-serif text-heading-sm font-normal text-press-black">Welcome back</h1>
      <p className="mb-8 font-sans text-body text-press-black/70">
        New to SwarmStock?{" "}
        <Link href="/signup" className="font-medium text-press-black underline underline-offset-4">
          Create an account
        </Link>
      </p>

      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="login-email" className="mb-2 block font-sans text-body font-medium text-press-black">
            Email
          </label>
          <InputField
            id="login-email"
            type="email"
            placeholder="you@business.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <label htmlFor="login-password" className="block font-sans text-body font-medium text-press-black">
              Password
            </label>
            <a href="#" className="font-sans text-caption font-medium text-press-black underline underline-offset-4">
              Forgot password?
            </a>
          </div>
          <InputField
            id="login-password"
            type="password"
            placeholder="Enter your password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div className="-mt-1 flex items-center gap-2">
          <input
            type="checkbox"
            id="login-remember"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="h-4 w-4 accent-press-black"
          />
          <label htmlFor="login-remember" className="font-sans text-body text-press-black/70">
            Stay signed in on this device
          </label>
        </div>

        <AccentButton type="submit" className="mt-1 w-full justify-center py-3! text-body-lg! shadow-sm">
          Sign in
        </AccentButton>
      </form>

      <div className="my-6 flex items-center gap-4">
        <div className="h-px flex-1 bg-sage-border" />
        <span className="whitespace-nowrap font-sans text-caption text-press-black/50">or continue with</span>
        <div className="h-px flex-1 bg-sage-border" />
      </div>

      <div className="mb-6 grid grid-cols-3 gap-3">
        <button
          type="button"
          aria-label="Continue with Google"
          className="flex items-center justify-center rounded-md border border-press-black bg-manuscript-cream p-3 hover:bg-paper-shadow"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5">
            <path fill="#4285F4" d="M23.49 12.27c0-.82-.07-1.6-.2-2.36H12v4.47h6.47c-.28 1.5-1.13 2.77-2.4 3.62v3h3.88c2.27-2.09 3.54-5.17 3.54-8.73z" />
            <path fill="#34A853" d="M12 24c3.24 0 5.95-1.07 7.93-2.9l-3.88-3c-1.08.72-2.45 1.15-4.05 1.15-3.12 0-5.76-2.1-6.7-4.93H1.3v3.09C3.26 21.3 7.31 24 12 24z" />
            <path fill="#FBBC05" d="M5.3 14.32c-.24-.72-.38-1.49-.38-2.32s.14-1.6.38-2.32V6.59H1.3A11.98 11.98 0 000 12c0 1.94.46 3.77 1.3 5.41z" />
            <path fill="#EA4335" d="M12 4.75c1.76 0 3.35.6 4.6 1.8l3.44-3.44C17.94 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.3 6.59l4 3.09c.94-2.83 3.58-4.93 6.7-4.93z" />
          </svg>
        </button>
        <button
          type="button"
          aria-label="Continue with Apple"
          className="flex items-center justify-center rounded-md border border-press-black bg-manuscript-cream p-3 hover:bg-paper-shadow"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5">
            <path
              fill="#000000"
              d="M16.36 1c.1 1.14-.32 2.24-1 3.06-.7.84-1.87 1.5-2.98 1.4-.13-1.1.4-2.26 1.05-3.02C14.13 1.55 15.3.94 16.36 1zm3.9 16.6c-.53 1.18-.78 1.7-1.46 2.75-.95 1.45-2.28 3.25-3.93 3.27-1.47.02-1.85-.96-3.84-.95-1.99.01-2.4.97-3.87.95-1.65-.02-2.9-1.65-3.85-3.1-2.64-4.02-2.92-8.73-1.29-11.24 1.16-1.78 2.99-2.83 4.71-2.83 1.75 0 2.85 1 4.3 1 1.4 0 2.26-1 4.3-1 1.53 0 3.15.83 4.3 2.27-3.78 2.07-3.17 7.45.63 8.88z"
            />
          </svg>
        </button>
        <button
          type="button"
          aria-label="Continue with email link"
          className="flex items-center justify-center rounded-md border border-press-black bg-manuscript-cream p-3 hover:bg-paper-shadow"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="#000000" strokeWidth="1.6" className="h-5 w-5">
            <rect x="2.5" y="5" width="19" height="14" rx="2" />
            <path d="M3 6.5l9 6.5 9-6.5" />
          </svg>
        </button>
      </div>

      <p className="text-center font-sans text-body text-press-black/70">
        Don&apos;t have an account?{" "}
        <GhostButton type="button" onClick={() => router.push("/signup")} className="px-0! py-0!">
          Sign up for free
        </GhostButton>
      </p>
    </AuthLayout>
  );
}

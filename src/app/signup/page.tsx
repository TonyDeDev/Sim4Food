"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { InputField } from "@/components/ui/InputField";
import { AccentButton } from "@/components/ui/AccentButton";
import { useAuth } from "@/lib/auth-context";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (password !== password2) {
      setError("Passwords don't match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setError("");
    signup({ first, last, email });
    router.push("/otp");
  }

  return (
    <AuthLayout
      quote="Set up in an afternoon. We had our first waste report by Friday."
      cite="Marcus Idowu, The Green Table"
    >
      <h1 className="mb-2 font-serif text-heading-sm font-normal text-press-black">Create your account</h1>
      <p className="mb-8 font-sans text-body text-press-black/70">
        Already have one?{" "}
        <Link href="/login" className="font-medium text-press-black underline underline-offset-4">
          Sign in
        </Link>
      </p>

      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="signup-first" className="mb-2 block font-sans text-body font-medium text-press-black">
              First name
            </label>
            <InputField
              id="signup-first"
              type="text"
              placeholder="Jordan"
              autoComplete="given-name"
              required
              value={first}
              onChange={(e) => setFirst(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="signup-last" className="mb-2 block font-sans text-body font-medium text-press-black">
              Last name
            </label>
            <InputField
              id="signup-last"
              type="text"
              placeholder="Ellis"
              autoComplete="family-name"
              required
              value={last}
              onChange={(e) => setLast(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label htmlFor="signup-email" className="mb-2 block font-sans text-body font-medium text-press-black">
            Email
          </label>
          <InputField
            id="signup-email"
            type="email"
            placeholder="you@business.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="signup-password" className="mb-2 block font-sans text-body font-medium text-press-black">
            Create password
          </label>
          <InputField
            id="signup-password"
            type="password"
            placeholder="At least 8 characters"
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="signup-password2" className="mb-2 block font-sans text-body font-medium text-press-black">
            Verify password
          </label>
          <InputField
            id="signup-password2"
            type="password"
            placeholder="Re-enter your password"
            autoComplete="new-password"
            required
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
          />
          <p className="mt-1 min-h-[16px] font-sans text-caption text-red-700">{error}</p>
        </div>

        <AccentButton type="submit" className="mt-1 w-full justify-center py-3! text-body-lg! shadow-sm">
          Create account
        </AccentButton>
      </form>
    </AuthLayout>
  );
}

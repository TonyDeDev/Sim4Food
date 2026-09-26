"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { generateOtp } from "@/lib/helpers";
import { useAuth } from "@/lib/auth-context";
import { AccentButton } from "@/components/ui/AccentButton";

export default function OtpPage() {
  const router = useRouter();
  const { pendingSignup, completeSignup } = useAuth();
  const [email] = useState(() => pendingSignup?.email ?? "");
  const [otp, setOtp] = useState(() => generateOtp());
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [error, setError] = useState("");
  const [verified, setVerified] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (!pendingSignup && !verified) {
      router.replace("/signup");
      return;
    }
    inputRefs.current[0]?.focus();
  }, [pendingSignup, verified, router]);

  if (!pendingSignup && !verified) return null;

  function handleChange(index: number, value: string) {
    const clean = value.replace(/[^0-9]/g, "").slice(0, 1);
    const next = [...digits];
    next[index] = clean;
    setDigits(next);
    if (clean && inputRefs.current[index + 1]) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[index] && inputRefs.current[index - 1]) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handleResend() {
    setOtp(generateOtp());
    setDigits(Array(6).fill(""));
    setError("");
    inputRefs.current[0]?.focus();
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const entered = digits.join("");
    if (entered.length < 6) {
      setError("Enter all 6 digits.");
      return;
    }
    if (entered !== otp) {
      setError("That code doesn't match. Try again.");
      return;
    }
    setError("");
    setVerified(true);
    completeSignup();
    router.push("/businesses");
  }

  return (
    <AuthLayout quote="One quick check and we were in — no fuss." cite="Priya Anand, Anand & Sons">
      <h1 className="mb-2 font-serif text-heading-sm font-normal text-press-black">Confirm your email</h1>
      <p className="mb-6 font-sans text-body text-press-black/70">
        We&apos;ve sent a 6-digit code to {email}.
      </p>

      <div className="mb-6 rounded-xl border border-press-black bg-spring-green/40 p-4 font-sans text-body leading-relaxed text-press-black">
        This is a demo, so no email actually goes out — your code is <strong className="tracking-[0.06em]">{otp}</strong>.
      </div>

      <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
        <div className="mb-1 flex gap-2">
          {digits.map((digit, i) => (
            <input
              key={i}
              ref={(el) => {
                inputRefs.current[i] = el;
              }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              onChange={(e) => handleChange(i, e.target.value)}
              onKeyDown={(e) => handleKeyDown(i, e)}
              className="h-14 w-12 rounded-md border border-press-black bg-manuscript-cream text-center font-sans text-heading-sm text-press-black focus:border-2 focus:outline-none"
            />
          ))}
        </div>
        <p className="min-h-[16px] font-sans text-caption text-red-700">{error}</p>
        <AccentButton type="submit" className="mt-1 w-full justify-center py-3! text-body-lg! shadow-sm">
          Verify and continue
        </AccentButton>
      </form>

      <p className="mt-6 font-sans text-body text-press-black/70">
        Didn&apos;t get a code?{" "}
        <button
          type="button"
          onClick={handleResend}
          className="font-medium text-press-black underline underline-offset-4"
        >
          Send a new one
        </button>
      </p>
    </AuthLayout>
  );
}

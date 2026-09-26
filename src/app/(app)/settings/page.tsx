"use client";

import { useAuth } from "@/lib/auth-context";
import { initials } from "@/lib/helpers";
import { InputField } from "@/components/ui/InputField";
import { OutlinedButton } from "@/components/ui/OutlinedButton";

export default function SettingsPage() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="mx-auto max-w-[600px]">
      <h1 className="mb-2 font-serif text-heading-sm font-normal text-press-black">Settings</h1>
      <p className="mb-8 font-sans text-body text-press-black/70">Manage your account details.</p>

      <div className="mb-8 flex items-center gap-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-press-black bg-highlighter-lime font-sans text-subheading font-medium text-press-black">
          {initials(user.firstName, user.lastName)}
        </div>
        <div>
          <p className="font-sans text-body-lg font-medium text-press-black">
            {user.firstName} {user.lastName}
          </p>
          <p className="font-sans text-body text-press-black/60">{user.email}</p>
        </div>
      </div>

      <form className="flex flex-col gap-4">
        <div>
          <label htmlFor="settings-first" className="mb-2 block font-sans text-body font-medium text-press-black">
            First name
          </label>
          <InputField id="settings-first" defaultValue={user.firstName} />
        </div>
        <div>
          <label htmlFor="settings-last" className="mb-2 block font-sans text-body font-medium text-press-black">
            Last name
          </label>
          <InputField id="settings-last" defaultValue={user.lastName} />
        </div>
        <div>
          <label htmlFor="settings-email" className="mb-2 block font-sans text-body font-medium text-press-black">
            Email
          </label>
          <InputField id="settings-email" type="email" defaultValue={user.email} disabled />
        </div>
        <OutlinedButton type="button" className="mt-2 w-fit">
          Save changes
        </OutlinedButton>
      </form>
    </div>
  );
}

"use client";

import { FormEvent, useState } from "react";
import { AuthCard, buttonClass, fieldClass } from "@/components/auth-card";
import { getSupabase } from "@/lib/supabase";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const { error: resetError } = await getSupabase().auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (resetError) {
        setError(resetError.message);
        return;
      }
      setSent(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start the reset.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Reset password">
      {sent ? (
        <p className="text-sm">If an account exists for {email}, Supabase sent a reset link. Open it on this computer.</p>
      ) : (
        <form className="grid gap-3" onSubmit={onSubmit}>
          <input className={fieldClass} type="email" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button className={buttonClass} disabled={pending} type="submit">
            {pending ? "Sending…" : "Send reset link"}
          </button>
        </form>
      )}
    </AuthCard>
  );
}

"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { AuthCard, buttonClass, fieldClass } from "@/components/auth-card";
import { getSupabase } from "@/lib/supabase";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const { error: signUpError } = await getSupabase().auth.signUp({
        email,
        password,
        options: {
          data: { full_name: fullName },
          emailRedirectTo: `${window.location.origin}/login`,
        },
      });
      if (signUpError) {
        setError(signUpError.message);
        return;
      }
      setSent(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the account.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Create account">
      {sent ? (
        <p className="text-sm">
          Check {email} for a confirmation message from Supabase. The account is stored in the shared project, so you
          can finish signing in from either computer.
        </p>
      ) : (
        <form className="grid gap-3" onSubmit={onSubmit}>
          <input className={fieldClass} placeholder="Full name" value={fullName} onChange={(event) => setFullName(event.target.value)} required />
          <input className={fieldClass} type="email" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <input className={fieldClass} type="password" placeholder="Password (8+ characters)" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button className={buttonClass} disabled={pending} type="submit">
            {pending ? "Creating…" : "Create account"}
          </button>
          <Link href="/login" className="text-sm text-muted">
            Already have an account
          </Link>
        </form>
      )}
    </AuthCard>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AuthCard, buttonClass, fieldClass } from "@/components/auth-card";
import { getSupabase } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    getSupabase()
      .auth.getSession()
      .then(({ data }) => setReady(Boolean(data.session)))
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "Supabase is not configured.");
      });
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const { error: updateError } = await getSupabase().auth.updateUser({ password });
      if (updateError) {
        setError(updateError.message);
        return;
      }
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reset the password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Choose a new password">
      {ready ? (
        <form className="grid gap-3" onSubmit={onSubmit}>
          <input className={fieldClass} type="password" placeholder="New password" value={password} minLength={8} onChange={(event) => setPassword(event.target.value)} required />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button className={buttonClass} disabled={pending} type="submit">
            {pending ? "Saving…" : "Update password"}
          </button>
        </form>
      ) : (
        <p className="text-sm">{error ?? "Open the reset link from your email. Supabase attaches the session to this page."}</p>
      )}
    </AuthCard>
  );
}

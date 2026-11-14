"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthCard, buttonClass, fieldClass } from "@/components/auth-card";
import { api } from "@/lib/api";
import { getSupabase, setAccessToken } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const { data, error: signInError } = await getSupabase().auth.signInWithPassword({ email, password });
      if (signInError || !data.session) {
        setError(signInError?.message ?? "Could not sign in.");
        return;
      }
      setAccessToken(data.session.access_token);
      await api("/auth/me", { token: data.session.access_token });
      router.push("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthCard title="Sign in">
      <form className="grid gap-3" onSubmit={onSubmit}>
        <input className={fieldClass} type="email" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <input className={fieldClass} type="password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button className={buttonClass} disabled={pending} type="submit">
          {pending ? "Signing in…" : "Sign in"}
        </button>
        <div className="flex justify-between text-sm text-muted">
          <Link href="/register">Create account</Link>
          <Link href="/forgot-password">Forgot password</Link>
        </div>
      </form>
    </AuthCard>
  );
}

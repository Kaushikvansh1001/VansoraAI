import { AuthCard } from "@/components/auth-card";

export default function VerifyEmailPage() {
  return (
    <AuthCard title="Confirm your email">
      <p className="text-sm">
        Supabase sends the confirmation message. After you open it, sign in. The account lives in the shared Supabase
        project, so the same email works on your office laptop and your personal laptop.
      </p>
    </AuthCard>
  );
}

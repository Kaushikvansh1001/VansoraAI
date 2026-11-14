"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSupabase, setAccessToken } from "@/lib/supabase";
import type { Organization, User } from "@/lib/types";

const ORG_KEY = "vansora.orgId";

type SessionValue = {
  user: User | null;
  ready: boolean;
  organizations: Organization[];
  organizationId: string | null;
  organization: Organization | null;
  logout: () => Promise<void>;
  refreshOrganizations: () => Promise<Organization[]>;
  selectOrganization: (organizationId: string) => void;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  async function refreshOrganizations() {
    const rows = await api<Organization[]>("/organizations");
    setOrganizations(rows);
    const saved = window.localStorage.getItem(ORG_KEY);
    const selected = rows.find((row) => row.id === saved)?.id ?? rows[0]?.id ?? null;
    if (selected) {
      window.localStorage.setItem(ORG_KEY, selected);
    } else {
      window.localStorage.removeItem(ORG_KEY);
    }
    setOrganizationId(selected);
    return rows;
  }

  useEffect(() => {
    let supabase;
    try {
      supabase = getSupabase();
    } catch {
      setReady(true);
      return;
    }

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setAccessToken(session?.access_token ?? null);
      if (!session) {
        setUser(null);
        setOrganizations([]);
        setOrganizationId(null);
        setReady(true);
        return;
      }
      api<User>("/auth/me", { token: session.access_token })
        .then(async (me) => {
          setUser(me);
          await refreshOrganizations();
        })
        .catch(() => {
          setUser(null);
        })
        .finally(() => setReady(true));
    });

    return () => subscription.subscription.unsubscribe();
  }, []);

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // The Supabase session is cleared even if the API is unreachable.
    }
    try {
      await getSupabase().auth.signOut();
    } catch {
      // The browser session is cleared even if Supabase is unreachable.
    }
    setAccessToken(null);
    window.localStorage.removeItem(ORG_KEY);
    setUser(null);
    setOrganizations([]);
    setOrganizationId(null);
  }

  function selectOrganization(nextId: string) {
    window.localStorage.setItem(ORG_KEY, nextId);
    setOrganizationId(nextId);
  }

  const organization = organizations.find((row) => row.id === organizationId) ?? null;

  return (
    <SessionContext.Provider
      value={{
        user,
        ready,
        organizations,
        organizationId,
        organization,
        logout,
        refreshOrganizations,
        selectOrganization,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return value;
}

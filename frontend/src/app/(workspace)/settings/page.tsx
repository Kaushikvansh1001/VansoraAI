"use client";

import { FormEvent, useEffect, useState } from "react";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Member, Organization } from "@/lib/types";

const roleLabel: Record<Organization["role"], string> = {
  org_admin: "Admin",
  manager: "Manager",
  member: "Member",
};

export default function SettingsPage() {
  const { organization, organizationId, organizations, refreshOrganizations, selectOrganization } = useSession();
  const [name, setName] = useState("");
  const [rename, setRename] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Organization["role"]>("member");
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId) {
      setMembers([]);
      return;
    }
    api<Member[]>(`/organizations/${organizationId}/members`)
      .then(setMembers)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load members."));
  }, [organizationId]);

  useEffect(() => {
    setRename(organization?.name ?? "");
  }, [organization]);

  async function createOrganization(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    try {
      const created = await api<Organization>("/organizations", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      await refreshOrganizations();
      selectOrganization(created.id);
      setName("");
      setMessage(`Created ${created.name}.`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the organization.");
    }
  }

  async function saveName(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) return;
    setError(null);
    setMessage(null);
    try {
      await api(`/organizations/${organizationId}`, {
        method: "PATCH",
        body: JSON.stringify({ name: rename }),
      });
      await refreshOrganizations();
      setMessage("Organization name saved.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not rename the organization.");
    }
  }

  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) return;
    setError(null);
    setMessage(null);
    try {
      await api(`/organizations/${organizationId}/members`, {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      setMembers(await api<Member[]>(`/organizations/${organizationId}/members`));
      setEmail("");
      setMessage("Member added.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not add that member.");
    }
  }

  return (
    <section className="max-w-2xl">
      <h1 className="text-2xl font-semibold">Organization</h1>
      <p className="mt-1 text-sm text-muted">Members only see records inside the organizations they belong to.</p>
      {message ? <p className="mt-4 text-sm">{message}</p> : null}
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

      <form className="mt-6 grid gap-3" onSubmit={createOrganization}>
        <h2 className="font-medium">Create</h2>
        <input className={fieldClass} placeholder="Organization name" value={name} onChange={(event) => setName(event.target.value)} minLength={2} required />
        <button className={buttonClass} type="submit">Create organization</button>
      </form>

      {organizations.length > 0 ? (
        <div className="mt-8 grid gap-3">
          <h2 className="font-medium">Switch</h2>
          <select
            className={fieldClass}
            value={organizationId ?? ""}
            onChange={(event) => selectOrganization(event.target.value)}
          >
            {organizations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({roleLabel[item.role]})
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {organization?.role === "org_admin" ? (
        <form className="mt-8 grid gap-3" onSubmit={saveName}>
          <h2 className="font-medium">Rename</h2>
          <input className={fieldClass} value={rename} onChange={(event) => setRename(event.target.value)} minLength={2} required />
          <button className={buttonClass} type="submit">Save name</button>
        </form>
      ) : null}

      {organization ? (
        <div className="mt-8">
          <h2 className="font-medium">Members</h2>
          <ul className="surface-card mt-3 divide-y divide-line rounded-lg border border-line">
            {members.map((member) => (
              <li key={member.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>
                  {member.full_name}
                  <span className="text-muted"> · {member.email}</span>
                </span>
                <span>{roleLabel[member.role]}</span>
              </li>
            ))}
          </ul>
          {organization.role === "org_admin" ? (
            <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_140px_auto]" onSubmit={addMember}>
              <input className={fieldClass} type="email" placeholder="Existing user email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              <select className={fieldClass} value={role} onChange={(event) => setRole(event.target.value as Organization["role"])}>
                <option value="member">Member</option>
                <option value="manager">Manager</option>
                <option value="org_admin">Admin</option>
              </select>
              <button className={buttonClass} type="submit">Add</button>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

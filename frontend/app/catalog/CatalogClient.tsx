"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type Area = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  vector_collection: string;
  access_level: string;
};

type Agent = {
  id: string;
  slug: string;
  display_name: string;
  agent_type: string;
  area_slugs: string[];
  fallback_agent_slug: string | null;
};

type Role = {
  id: string;
  slug: string;
  name: string;
  level: number;
  agent_slugs: string[];
};

const readJson = async (response: Response) => {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
};

const defaultPrompt = [
  "You are a specialist agent.",
  "Answer concisely and cite sources when available.",
  "If the provided context is insufficient, explain what is missing.",
].join("\n");

export default function CatalogClient() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [areaForm, setAreaForm] = useState({
    slug: "",
    name: "",
    description: "",
    accessLevel: "restricted",
  });

  const [agentForm, setAgentForm] = useState({
    slug: "",
    displayName: "",
    description: "",
    agentType: "specialist",
    areaSlugs: "",
    fallbackSlug: "",
    systemPrompt: defaultPrompt,
  });

  const [roleForm, setRoleForm] = useState({
    name: "",
    slug: "",
    description: "",
    level: 10,
    agentSlugs: "",
  });

  const [userRoleForm, setUserRoleForm] = useState({
    userId: "",
    roleSlugs: "",
  });

  const resetMessages = () => {
    setMessage(null);
    setError(null);
  };

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    resetMessages();
    try {
      const [areasRes, agentsRes, rolesRes] = await Promise.all([
        fetch("/api/catalog/areas", { cache: "no-store" }),
        fetch("/api/catalog/agents", { cache: "no-store" }),
        fetch("/api/catalog/roles", { cache: "no-store" }),
      ]);

      if (!areasRes.ok || !agentsRes.ok || !rolesRes.ok) {
        const detail = !areasRes.ok
          ? await readJson(areasRes)
          : !agentsRes.ok
            ? await readJson(agentsRes)
            : await readJson(rolesRes);
        throw new Error(
          (detail as { detail?: string })?.detail ?? "Failed to load catalog data",
        );
      }

      setAreas((await areasRes.json()) as Area[]);
      setAgents((await agentsRes.json()) as Agent[]);
      setRoles((await rolesRes.json()) as Role[]);
      setMessage("Catalog data refreshed.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const submitArea = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setSaving(true);
    try {
      const payload = {
        slug: areaForm.slug.trim(),
        name: areaForm.name.trim(),
        description: areaForm.description.trim() || null,
        access_level: areaForm.accessLevel,
        is_active: true,
      };
      const response = await fetch("/api/catalog/areas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await readJson(response);
        throw new Error((detail as { detail?: string })?.detail ?? "Failed to create area");
      }
      setAreaForm({ slug: "", name: "", description: "", accessLevel: areaForm.accessLevel });
      setMessage(`Area '${payload.slug}' created.`);
      await loadCatalog();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const submitAgent = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setSaving(true);
    try {
      const areaSlugs = agentForm.areaSlugs
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const payload = {
        slug: agentForm.slug.trim(),
        display_name: agentForm.displayName.trim(),
        description: agentForm.description.trim() || null,
        agent_type: agentForm.agentType,
        system_prompt: agentForm.systemPrompt,
        temperature: 0.2,
        max_tokens: 2048,
        execution_order: 100,
        fallback_agent_slug: agentForm.fallbackSlug.trim() || null,
        area_slugs: areaSlugs,
        role_slugs: [],
        resource_permissions: {
          allow: {
            areas: areaSlugs,
            mcps: ["google-drive-mcp", "fetch-mcp"],
          },
        },
        capabilities: areaSlugs.length
          ? { primary_area: areaSlugs[0] }
          : {},
      };
      const response = await fetch("/api/catalog/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await readJson(response);
        throw new Error((detail as { detail?: string })?.detail ?? "Failed to create agent");
      }
      setAgentForm({
        slug: "",
        displayName: "",
        description: "",
        agentType: agentForm.agentType,
        areaSlugs: "",
        fallbackSlug: "",
        systemPrompt: defaultPrompt,
      });
      setMessage(`Agent '${payload.slug}' created.`);
      await loadCatalog();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const submitRole = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setSaving(true);
    try {
      const agentSlugs = roleForm.agentSlugs
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const payload = {
        name: roleForm.name.trim(),
        slug: roleForm.slug.trim() || null,
        description: roleForm.description.trim() || null,
        level: Number(roleForm.level),
        is_system_role: false,
        inherits_from_slug: null,
        permissions: {
          agents: agentSlugs,
          areas: agentSlugs,
        },
        agent_slugs: agentSlugs,
      };
      const response = await fetch("/api/catalog/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await readJson(response);
        throw new Error((detail as { detail?: string })?.detail ?? "Failed to create role");
      }
      setRoleForm({
        name: "",
        slug: "",
        description: "",
        level: roleForm.level,
        agentSlugs: "",
      });
      setMessage(`Role '${payload.name}' created.`);
      await loadCatalog();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const submitUserRoles = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    resetMessages();
    setSaving(true);
    try {
      const roleSlugs = userRoleForm.roleSlugs
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const response = await fetch(
        `/api/catalog/users/${userRoleForm.userId.trim()}/roles`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role_slugs: roleSlugs }),
        },
      );
      if (!response.ok) {
        const detail = await readJson(response);
        throw new Error((detail as { detail?: string })?.detail ?? "Failed to update user roles");
      }
      setMessage("Roles updated for user.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-10">
        <header className="space-y-3 border-b border-white/10 pb-4">
          <h1 className="text-2xl font-semibold text-blue-200">Catalog Manager</h1>
          <p className="text-sm text-slate-300">
            Bootstrap and maintain areas, agents, and roles before enabling the chatbot interface.
          </p>
          <div className="flex gap-3">
            <button
              className="rounded bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:bg-blue-900"
              onClick={() => void loadCatalog()}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Refresh data"}
            </button>
          </div>
          {message && (
            <div className="rounded border border-emerald-400/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
              {message}
            </div>
          )}
          {error && (
            <div className="rounded border border-rose-400/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
              {error}
            </div>
          )}
        </header>

        <section className="grid gap-6 md:grid-cols-2">
          <article className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-5">
            <h2 className="text-lg font-semibold text-blue-200">Create Area</h2>
            <form className="space-y-3 text-sm" onSubmit={submitArea}>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Slug</span>
                <input
                  required
                  value={areaForm.slug}
                  onChange={(event) =>
                    setAreaForm((prev) => ({ ...prev, slug: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="area5"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Name</span>
                <input
                  required
                  value={areaForm.name}
                  onChange={(event) =>
                    setAreaForm((prev) => ({ ...prev, name: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="Nueva área"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Description</span>
                <textarea
                  value={areaForm.description}
                  onChange={(event) =>
                    setAreaForm((prev) => ({ ...prev, description: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                  rows={3}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Access level</span>
                <select
                  value={areaForm.accessLevel}
                  onChange={(event) =>
                    setAreaForm((prev) => ({ ...prev, accessLevel: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                >
                  <option value="public">public</option>
                  <option value="restricted">restricted</option>
                  <option value="admin-only">admin-only</option>
                </select>
              </label>
              <button
                type="submit"
                className="rounded bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:bg-emerald-900"
                disabled={saving}
              >
                {saving ? "Saving..." : "Add area"}
              </button>
            </form>
          </article>

          <article className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-5">
            <h2 className="text-lg font-semibold text-blue-200">Create Agent</h2>
            <form className="space-y-3 text-sm" onSubmit={submitAgent}>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Slug</span>
                <input
                  required
                  value={agentForm.slug}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, slug: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="agent5"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Display name</span>
                <input
                  required
                  value={agentForm.displayName}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, displayName: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="Especialista Demanda"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Description</span>
                <textarea
                  value={agentForm.description}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, description: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                  rows={2}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Agent type</span>
                <select
                  value={agentForm.agentType}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, agentType: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                >
                  <option value="orchestrator">orchestrator</option>
                  <option value="specialist">specialist</option>
                  <option value="tool">tool</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Area slugs (comma separated)</span>
                <input
                  value={agentForm.areaSlugs}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, areaSlugs: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="area1, area2"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Fallback agent slug</span>
                <input
                  value={agentForm.fallbackSlug}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, fallbackSlug: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="agent0"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">System prompt</span>
                <textarea
                  required
                  value={agentForm.systemPrompt}
                  onChange={(event) =>
                    setAgentForm((prev) => ({ ...prev, systemPrompt: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                  rows={4}
                />
              </label>
              <button
                type="submit"
                className="rounded bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:bg-emerald-900"
                disabled={saving}
              >
                {saving ? "Saving..." : "Add agent"}
              </button>
            </form>
          </article>
        </section>

        <section className="grid gap-6 md:grid-cols-2">
          <article className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-5">
            <h2 className="text-lg font-semibold text-blue-200">Create Role</h2>
            <form className="space-y-3 text-sm" onSubmit={submitRole}>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Name</span>
                <input
                  required
                  value={roleForm.name}
                  onChange={(event) =>
                    setRoleForm((prev) => ({ ...prev, name: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="Agent1"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Slug (optional)</span>
                <input
                  value={roleForm.slug}
                  onChange={(event) =>
                    setRoleForm((prev) => ({ ...prev, slug: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="agent1"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Description</span>
                <textarea
                  value={roleForm.description}
                  onChange={(event) =>
                    setRoleForm((prev) => ({ ...prev, description: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                  rows={2}
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Level</span>
                <input
                  type="number"
                  value={roleForm.level}
                  onChange={(event) =>
                    setRoleForm((prev) => ({ ...prev, level: Number(event.target.value) }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Agent slugs (comma separated)</span>
                <input
                  value={roleForm.agentSlugs}
                  onChange={(event) =>
                    setRoleForm((prev) => ({ ...prev, agentSlugs: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="agent1"
                />
              </label>
              <button
                type="submit"
                className="rounded bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:bg-emerald-900"
                disabled={saving}
              >
                {saving ? "Saving..." : "Add role"}
              </button>
            </form>
          </article>

          <article className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-5">
            <h2 className="text-lg font-semibold text-blue-200">Assign Roles to User</h2>
            <form className="space-y-3 text-sm" onSubmit={submitUserRoles}>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">User ID (UUID)</span>
                <input
                  required
                  value={userRoleForm.userId}
                  onChange={(event) =>
                    setUserRoleForm((prev) => ({ ...prev, userId: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="00000000-0000-0000-0000-000000000000"
                />
              </label>
              <label className="space-y-1">
                <span className="text-xs uppercase text-slate-400">Role slugs (comma separated)</span>
                <input
                  value={userRoleForm.roleSlugs}
                  onChange={(event) =>
                    setUserRoleForm((prev) => ({ ...prev, roleSlugs: event.target.value }))
                  }
                  className="w-full rounded border border-white/10 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  placeholder="administrator, agent1"
                />
              </label>
              <button
                type="submit"
                className="rounded bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:bg-emerald-900"
                disabled={saving}
              >
                {saving ? "Saving..." : "Apply roles"}
              </button>
            </form>
            <p className="text-xs text-slate-400">
              Tip: you can retrieve your user ID via the <code className="font-mono text-slate-200">/users/me</code> endpoint.
            </p>
          </article>
        </section>

        <section className="grid gap-6 md:grid-cols-3">
          <article className="rounded-xl border border-white/10 bg-slate-900/70 p-4">
            <h3 className="text-sm font-semibold text-blue-200">Areas</h3>
            <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs text-slate-300">
              {JSON.stringify(areas, null, 2)}
            </pre>
          </article>
          <article className="rounded-xl border border-white/10 bg-slate-900/70 p-4">
            <h3 className="text-sm font-semibold text-blue-200">Agents</h3>
            <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs text-slate-300">
              {JSON.stringify(agents, null, 2)}
            </pre>
          </article>
          <article className="rounded-xl border border-white/10 bg-slate-900/70 p-4">
            <h3 className="text-sm font-semibold text-blue-200">Roles</h3>
            <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap text-xs text-slate-300">
              {JSON.stringify(roles, null, 2)}
            </pre>
          </article>
        </section>
      </section>
    </main>
  );
}


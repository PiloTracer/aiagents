"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

type TokenSample = {
  chunk_index?: number;
  token_count?: number;
  invalid_characters?: number;
  sample_tokens?: number[];
  sample_text?: string;
  validation_note?: string;
};

type TokenSummary = {
  total_tokens: number;
  valid_tokens?: number;
  invalid_tokens: number;
  removed_characters?: number;
  fallback_chunks?: number[];
  dropped_chunks?: number;
  samples?: TokenSample[];
};

type JobSummary = {
  id: string;
  area_slug: string;
  agent_slug: string;
  source_uri: string;
  status: string;
  total_artifacts: number;
  processed_artifacts: number;
  error_message: string | null;
  created_at: string;
  updated_at: string | null;
  token_summary: TokenSummary | null;
};

type IngestionResponsePayload = {
  job: JobSummary;
  artifacts: unknown[];
};

const defaultLocation = {
  uri: "area1",
  area_slug: "area1",
  agent_slug: "agent1",
  recursive: true,
};

export default function MenuClient() {
  const [uri, setUri] = useState(defaultLocation.uri);
  const [areaSlug, setAreaSlug] = useState(defaultLocation.area_slug);
  const [agentSlug, setAgentSlug] = useState(defaultLocation.agent_slug);
  const [recursive, setRecursive] = useState(defaultLocation.recursive);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [logs, setLogs] = useState<string>("");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);

  const requestPayload = useMemo(
    () => ({
      force_reprocess: forceReprocess,
      locations: [
        {
          uri,
          area_slug: areaSlug,
          agent_slug: agentSlug,
          recursive,
        },
      ],
    }),
    [agentSlug, areaSlug, forceReprocess, recursive, uri],
  );

  const execIngest = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/rag/ingest`, {
        method: "POST",
        body: JSON.stringify(requestPayload),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      const data = (await res.json()) as IngestionResponsePayload[];
      const jobsInfo = data
        .map((item) => `${item.job.id} [${item.job.status}]`)
        .join(", ");
      const messageLines = [
        "Signal sent - processing...",
        jobsInfo ? `Jobs: ${jobsInfo}` : "Jobs: backend accepted payload.",
        'Use "Load job history" to monitor progress.',
      ];
      setLogs(messageLines.join("\n"));
    } catch (error) {
      setLogs(`Ingest failed: ${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [requestPayload]);

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const res = await fetch(`/api/rag/jobs`, { cache: "no-store" });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || res.statusText);
      }
      const data = (await res.json()) as { jobs: JobSummary[] };
      setJobs(data.jobs);
      const tokenNotes = data.jobs
        .slice(0, 3)
        .map((job) =>
          job.token_summary
            ? `${job.id}: tokens=${job.token_summary.total_tokens} (valid=${job.token_summary.valid_tokens ?? 0}, invalid=${job.token_summary.invalid_tokens}, removed=${job.token_summary.removed_characters ?? 0}, dropped=${job.token_summary.dropped_chunks ?? 0})`
            : `${job.id}: no token summary`,
        )
        .join("\n");
      setLogs([`Loaded ${data.jobs.length} jobs.`, tokenNotes].filter(Boolean).join("\n"));
    } catch (error) {
      setLogs(`Job fetch failed: ${(error as Error).message}`);
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 px-6 py-12">
      <section className="mx-auto max-w-5xl space-y-10">
        <header className="space-y-4">
          <h1 className="text-4xl font-semibold tracking-tight">Operations Menu</h1>
          <p className="text-sm text-slate-300">
            Configure the payload, run ingestion, review jobs, or jump to the Qdrant dashboard.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-blue-200">Ingest Documents</h2>
            <div className="grid gap-3 text-sm">
              <label className="grid gap-1">
                <span className="text-xs uppercase tracking-wide text-slate-400">Area slug</span>
                <input
                  className="rounded border border-white/10 bg-slate-900 px-3 py-2"
                  value={areaSlug}
                  onChange={(event) => setAreaSlug(event.target.value)}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs uppercase tracking-wide text-slate-400">Agent slug</span>
                <input
                  className="rounded border border-white/10 bg-slate-900 px-3 py-2"
                  value={agentSlug}
                  onChange={(event) => setAgentSlug(event.target.value)}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs uppercase tracking-wide text-slate-400">Source URI or path</span>
                <input
                  className="rounded border border-white/10 bg-slate-900 px-3 py-2"
                  value={uri}
                  onChange={(event) => setUri(event.target.value)}
                  placeholder="area1 or D:/data/area1"
                />
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={recursive}
                  onChange={(event) => setRecursive(event.target.checked)}
                />
                Recursive (include subfolders)
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={forceReprocess}
                  onChange={(event) => setForceReprocess(event.target.checked)}
                />
                Force reprocess (ignore existing hashes)
              </label>
            </div>
            <button
              className="w-full rounded-lg bg-blue-500 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:bg-blue-900"
              onClick={execIngest}
              disabled={loading}
            >
              {loading ? "Submitting..." : "Execute ingest"}
            </button>
            <details className="text-xs text-slate-300">
              <summary className="cursor-pointer text-blue-200">Preview payload</summary>
              <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-[11px] leading-tight">
                {JSON.stringify(requestPayload, null, 2)}
              </pre>
            </details>
          </article>

          <article className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-blue-200">Manage Jobs</h2>
            <p className="text-sm text-slate-300">
              Refresh recent runs and inspect their status. Use this after each ingestion to verify completion.
            </p>
            <button
              className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:bg-emerald-900"
              onClick={loadJobs}
              disabled={loadingJobs}
            >
              {loadingJobs ? "Loading..." : "Load job history"}
            </button>
            <ul className="max-h-72 overflow-y-auto space-y-3 text-xs">
              {jobs.map((job) => {
                const sampleTokens = job.token_summary?.samples?.[0]?.sample_tokens?.slice(0, 10);
                const sampleText = job.token_summary?.samples?.[0]?.sample_text;
                const validationNote = job.token_summary?.samples?.[0]?.validation_note;

                return (
                  <li key={job.id} className="rounded border border-white/10 bg-slate-900/70 p-3">
                    <div className="flex justify-between font-semibold text-blue-200">
                      <span>{job.area_slug}</span>
                      <span>{job.status}</span>
                    </div>
                    <div className="mt-1 text-slate-300">
                      {job.processed_artifacts}/{job.total_artifacts} files - Agent {job.agent_slug}
                    </div>
                    <div className="mt-1 text-slate-400">Source: {job.source_uri}</div>
                    {job.token_summary && (
                      <div className="mt-1 text-slate-400">
                        Tokens: {job.token_summary.total_tokens} (valid {job.token_summary.valid_tokens ?? 0}, invalid {job.token_summary.invalid_tokens})
                      </div>
                    )}
                    {job.token_summary?.removed_characters ? (
                      <div className="mt-1 text-slate-400">
                        Removed chars: {job.token_summary.removed_characters}
                      </div>
                    ) : null}
                    {job.token_summary?.dropped_chunks ? (
                      <div className="mt-1 text-slate-400">
                        Dropped chunks: {job.token_summary.dropped_chunks}
                      </div>
                    ) : null}
                    {job.token_summary?.fallback_chunks?.length ? (
                      <div className="mt-1 text-slate-500">
                        ASCII fallback chunks: {job.token_summary.fallback_chunks.slice(0, 5).join(", ")}
                      </div>
                    ) : null}
                    {sampleTokens ? (
                      <div className="mt-1 text-slate-500">
                        Sample tokens: {sampleTokens.map((token) => token?.toString() ?? "").join(", ")}
                      </div>
                    ) : null}
                    {sampleText ? <div className="mt-1 text-slate-500 italic">Sample text: {sampleText}</div> : null}
                    {validationNote ? <div className="mt-1 text-slate-500">Validation: {validationNote}</div> : null}
                    {job.error_message && <div className="mt-1 text-rose-300">{job.error_message}</div>}
                    <div className="mt-1 text-slate-500 text-[11px]">Started: {new Date(job.created_at).toLocaleString()}</div>
                  </li>
                );
              })}
              {!jobs.length && <li className="text-slate-400">No jobs loaded yet.</li>}
            </ul>
          </article>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-3 text-sm text-slate-300">
            <h2 className="text-lg font-semibold text-blue-200">Qdrant Dashboard</h2>
            <p>Open the built-in UI to confirm collection growth and payload distribution.</p>
            <Link
              href="http://localhost:16433/dashboard"
              target="_blank"
              className="inline-block rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400"
            >
              Open dashboard
            </Link>
          </article>

          <article className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-3 text-sm text-slate-300">
            <h2 className="text-lg font-semibold text-blue-200">Agent Refresh (Roadmap)</h2>
            <p>Notify downstream agents when new embeddings land. Hook your automation here.</p>
            <button
              className="w-full rounded-lg bg-slate-700 px-4 py-2 text-sm font-semibold text-slate-300"
              disabled
              title="Coming soon"
            >
              Trigger agent sync
            </button>
          </article>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-3">
          <h2 className="text-lg font-semibold text-blue-200">Activity Log</h2>
          <textarea
            className="h-40 w-full rounded border border-white/10 bg-slate-900 p-3 text-xs text-slate-200"
            value={logs}
            onChange={(event) => setLogs(event.target.value)}
          />
        </section>
      </section>
    </main>
  );
}

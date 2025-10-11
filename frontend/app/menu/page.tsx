import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

type Action = {
  title: string;
  description: string;
  endpoint: string;
  method: "GET" | "POST";
  docs?: string;
};

const ACTIONS: Action[] = [
  {
    title: "Execute Ingest",
    description:
      "Trigger the backend to scan configured document areas, extract content, chunk, embed, and upsert vectors into Qdrant.",
    endpoint: "POST /rag/ingest",
    method: "POST",
    docs: "Use the sample payload or cURL command below once authenticated.",
  },
  {
    title: "Review Ingestion Jobs",
    description:
      "Inspect the job ledger to confirm processed artifacts, execution timestamps, and any failures that require attention.",
    endpoint: "GET /rag/jobs",
    method: "GET",
  },
  {
    title: "Monitor Qdrant Collections",
    description:
      "Open the embedded dashboard to verify per-area vector collections, point counts, and payload distribution.",
    endpoint: "http://localhost:16433/dashboard",
    method: "GET",
  },
  {
    title: "Stage Agent Refresh",
    description:
      "Planned hook to notify retrieval agents that fresh context is available after a successful ingestion cycle.",
    endpoint: "POST /agents/sync (roadmap)",
    method: "POST",
  },
];

const SAMPLE_PAYLOAD = `POST /rag/ingest
Authorization: Bearer <token>
Content-Type: application/json

{
  "force_reprocess": false,
  "locations": [
    {
      "uri": "area1",
      "area_slug": "area1",
      "agent_slug": "agent1",
      "recursive": true
    }
  ]
}`;

const CURL_COMMAND = `curl -X POST http://localhost:18001/rag/ingest \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{
        "force_reprocess": false,
        "locations": [
          { "uri": "area1", "area_slug": "area1", "agent_slug": "agent1", "recursive": true }
        ]
      }'`;

export default async function MenuPage() {
  const token = (await cookies()).get("access_token")?.value;
  if (!token) {
    redirect("/auth");
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100 px-6 py-12">
      <section className="mx-auto max-w-5xl space-y-10">
        <header className="space-y-4">
          <h1 className="text-4xl font-semibold tracking-tight">Operations Menu</h1>
          <p className="text-sm text-slate-300 leading-relaxed">
            Use these actions to orchestrate document ingestion and retrieval hygiene. Update{" "}
            <code>RAG_DOCUMENT_ROOT</code> to point to the desired corpus, then run an ingest to populate Qdrant.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-2">
          {ACTIONS.map((action) => (
            <article
              key={action.title}
              className="rounded-xl border border-white/10 bg-white/5 p-6 shadow-lg shadow-blue-500/10 backdrop-blur transition hover:border-blue-400/40"
            >
              <h2 className="text-xl font-semibold text-blue-200">{action.title}</h2>
              <p className="mt-2 text-sm text-slate-200">{action.description}</p>
              <dl className="mt-4 space-y-1 text-xs font-medium uppercase tracking-widest text-blue-300">
                <div className="flex items-center gap-2">
                  <dt className="rounded bg-blue-500/20 px-2 py-0.5 text-blue-200">{action.method}</dt>
                  <dd className="text-slate-100">{action.endpoint}</dd>
                </div>
              </dl>
              {action.docs && (
                <p className="mt-3 text-xs text-slate-300">
                  {action.docs}
                  {action.endpoint.startsWith("http") && (
                    <>
                      {" "}
                      <Link href={action.endpoint} className="text-blue-300 underline hover:text-blue-200">
                        Open dashboard
                      </Link>
                    </>
                  )}
                </p>
              )}
            </article>
          ))}
        </section>

        <section className="grid gap-6 sm:grid-cols-2">
          <aside className="rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-slate-200">
            <h3 className="text-lg font-semibold text-blue-200">Sample Request</h3>
            <p className="mt-2 text-xs text-slate-300">
              Replace <code>&lt;token&gt;</code> with the value issued by the authentication module.
            </p>
            <pre className="mt-4 overflow-x-auto rounded-md bg-slate-950/80 p-4 text-xs text-blue-200">
              {SAMPLE_PAYLOAD}
            </pre>
          </aside>
          <aside className="rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-slate-200">
            <h3 className="text-lg font-semibold text-blue-200">Quick cURL</h3>
            <p className="mt-2 text-xs text-slate-300">
              Execute from the host once <code>docker compose up backend dbrag db</code> is running.
            </p>
            <pre className="mt-4 overflow-x-auto rounded-md bg-slate-950/80 p-4 text-xs text-blue-200">
              {CURL_COMMAND}
            </pre>
          </aside>
        </section>

        <section className="rounded-xl border border-white/10 bg-white/5 p-6 text-sm text-slate-200 space-y-4">
          <h3 className="text-lg font-semibold text-blue-200">Prerequisites & Notes</h3>
          <ul className="list-disc pl-5 space-y-2 text-xs text-slate-300">
            <li>Backend, Postgres, and Qdrant services must be running before triggering ingestion.</li>
            <li>
              Populate <code>DOCS/area*</code> (or configure alternate paths) so each agent owns its domain content.
            </li>
            <li>Docling and LangChain dependencies are bundled; rebuild the backend image after dependency changes.</li>
            <li>File hashes avoid reprocessing unchanged documents. Use <em>force_reprocess</em> to refresh updates.</li>
            <li>Agents should query with an <code>area_slug</code> filter to maintain domain isolation.</li>
          </ul>
        </section>
      </section>
    </main>
  );
}

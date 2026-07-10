import { Link } from "react-router-dom";
import {
  ArrowRight,
  FileText,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Zap,
} from "lucide-react";

const features = [
  {
    icon: UploadCloud,
    title: "Ingest any document",
    description:
      "Drop PDFs, docs, spreadsheets and notes. We chunk, embed and index them automatically for retrieval.",
  },
  {
    icon: MessageSquareText,
    title: "Ask in plain language",
    description:
      "Query your internal knowledge with natural language and get grounded, source-backed answers instantly.",
  },
  {
    icon: ShieldCheck,
    title: "Private & internal-only",
    description:
      "Your documents stay inside your organization's workspace, never used to train external models.",
  },
  {
    icon: Zap,
    title: "Fast, multipurpose retrieval",
    description:
      "One platform for engineering docs, HR policies, product specs and more — all searchable in one place.",
  },
];

const steps = [
  {
    step: "01",
    title: "Upload your documents",
    description:
      "Send files to the knowledge base from the Upload page to start building your index.",
    to: "/upload",
    cta: "Go to Upload",
  },
  {
    step: "02",
    title: "Chat with your knowledge",
    description:
      "Ask the assistant anything about your internal documents and get instant, cited answers.",
    to: "/chat",
    cta: "Open the Assistant",
  },
];

export default function Index() {
  return (
    <div className="flex flex-1 flex-col">
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-40 -top-40 h-[420px] w-[420px] rounded-full bg-brand-blue/40 blur-[120px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-56 left-1/2 h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-brand-pink/30 blur-[150px] sm:left-auto sm:right-1/4 sm:translate-x-0"
        />

        <div className="container relative flex flex-col items-center px-4 py-20 text-center sm:py-28">
          <span className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/70 px-4 py-1.5 font-body text-xs font-medium text-ink/70 shadow-sm backdrop-blur">
            <Sparkles size={14} className="text-brand-pink" />
            Internal Knowledge Platform
          </span>

          <h1 className="mt-6 max-w-3xl font-sans text-4xl font-extrabold leading-[1.1] tracking-tight text-ink sm:text-5xl md:text-6xl">
            Multipurpose RAG System
          </h1>
          <p className="mt-4 max-w-2xl font-body text-base text-muted-foreground sm:text-lg">
            One retrieval-augmented platform for your entire organization —
            upload any internal document and let your team ask our AI
            anything about it.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              to="/upload"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 font-body text-sm font-semibold text-white shadow-lg shadow-ink/10 transition-transform hover:-translate-y-0.5"
            >
              <UploadCloud size={18} />
              Upload documents
            </Link>
            <Link
              to="/chat"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-ink/15 bg-white/80 px-6 py-3 font-body text-sm font-semibold text-ink shadow-sm backdrop-blur transition-transform hover:-translate-y-0.5"
            >
              <MessageSquareText size={18} />
              Ask our AI
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>

      <section className="border-t border-ink/10 bg-white py-16 sm:py-20">
        <div className="container px-4">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-sans text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
              Everything your team needs to search internal knowledge
            </h2>
            <p className="mt-3 font-body text-muted-foreground">
              Built for teams that need reliable, grounded answers from their
              own documents — not the open internet.
            </p>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {features.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
              >
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-brand-blue/20 to-brand-pink/20 text-ink">
                  <Icon size={20} />
                </span>
                <h3 className="mt-4 font-sans text-base font-bold text-ink">
                  {title}
                </h3>
                <p className="mt-2 font-body text-sm text-muted-foreground">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-ink/10 bg-secondary/50 py-16 sm:py-20">
        <div className="container px-4">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="font-sans text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
              Get started in two steps
            </h2>
          </div>

          <div className="mx-auto mt-12 grid max-w-4xl grid-cols-1 gap-6 sm:grid-cols-2">
            {steps.map(({ step, title, description, to, cta }) => (
              <Link
                key={step}
                to={to}
                className="group flex flex-col justify-between rounded-2xl border border-ink/10 bg-white p-8 shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg"
              >
                <div>
                  <span className="font-sans text-sm font-bold text-brand-pink">
                    {step}
                  </span>
                  <h3 className="mt-3 font-sans text-xl font-bold text-ink">
                    {title}
                  </h3>
                  <p className="mt-2 font-body text-sm text-muted-foreground">
                    {description}
                  </p>
                </div>
                <span className="mt-6 inline-flex items-center gap-1 font-body text-sm font-semibold text-ink">
                  {cta}
                  <ArrowRight
                    size={16}
                    className="transition-transform group-hover:translate-x-1"
                  />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-ink/10 bg-white py-14">
        <div className="container flex flex-col items-center gap-6 px-4 text-center sm:flex-row sm:justify-between sm:text-left">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-ink text-white">
              <FileText size={18} />
            </span>
            <div>
              <p className="font-sans text-sm font-bold text-ink">
                Ready to index your knowledge base?
              </p>
              <p className="font-body text-sm text-muted-foreground">
                Upload your first document and start asking questions in
                minutes.
              </p>
            </div>
          </div>
          <Link
            to="/upload"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-ink px-6 py-3 font-body text-sm font-semibold text-white shadow-lg shadow-ink/10 transition-transform hover:-translate-y-0.5"
          >
            Upload documents
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </div>
  );
}

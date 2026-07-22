import { Activity } from "lucide-react";

export function RetrievalDiagnostics({ metadata }: { metadata?: Record<string, unknown> | null }) {
  const retrieval = metadata?.retrieval;
  if (!retrieval || typeof retrieval !== "object") return null;
  const details = retrieval as Record<string, unknown>;
  return (
    <details className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium hover:text-foreground">
        <Activity className="h-3.5 w-3.5" /> Retrieval details
      </summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border border-border bg-muted p-2">
        <dt>Mode</dt><dd className="text-foreground">{String(details.mode ?? "unknown")}</dd>
        <dt>Query</dt><dd className="break-words text-foreground">{String(details.retrieval_query ?? "Direct")}</dd>
        <dt>Sources</dt><dd className="text-foreground">{String(details.selected ?? 0)}</dd>
        <dt>Context</dt><dd className="text-foreground">{String(details.context_characters ?? 0)} characters</dd>
      </dl>
    </details>
  );
}

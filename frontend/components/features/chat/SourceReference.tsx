"use client";

import { FileText, FolderTree, NotebookText } from "lucide-react";

import type { ChatSources } from "@/types";

interface SourceReferenceProps {
  sources?: ChatSources | null;
}

export function SourceReference({ sources }: SourceReferenceProps) {
  const documents = sources?.documents ?? [];
  const chunks = sources?.chunks ?? [];
  const notes = sources?.notes ?? [];

  const isExactMatch = (origin: string, score: number | null | undefined) =>
    (origin === "lexical" || origin === "hybrid") && typeof score !== "number";

  if (documents.length === 0 && chunks.length === 0 && notes.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 border border-border bg-muted p-3">
      <p className="text-[11px] text-muted-foreground">Source References</p>

      <div className="mt-2 space-y-2">
        {documents.map((document) => (
          <div key={`${document.document_id}-${document.title}`} className="flex items-center justify-between gap-3 border border-border bg-background px-2 py-1.5">
            <div className="flex min-w-0 items-center gap-2">
              <FileText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              {document.citation_ids.length > 0 ? (
                <span className="flex-shrink-0 text-[10px] font-medium text-primary">
                  {document.citation_ids.map((citationId) => `[${citationId}]`).join(" ")}
                </span>
              ) : null}
              <p className="truncate text-xs text-foreground">{document.title}</p>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              {typeof document.max_score === "number" ? (
                <>
                  <span>{document.chunk_count} chunks</span>
                  <span>score {document.max_score.toFixed(2)}</span>
                </>
              ) : isExactMatch(document.origin, document.max_score) ? (
                <span>Exact match</span>
              ) : null}
            </div>
          </div>
        ))}
        {notes.map((note) => (
          <div key={note.note_id} className="border border-border bg-background px-2 py-1.5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <NotebookText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                {typeof note.citation_id === "number" ? (
                  <span className="flex-shrink-0 text-[10px] font-medium text-primary">[{note.citation_id}]</span>
                ) : null}
                <p className="truncate text-xs text-foreground">{note.title}</p>
              </div>
              {typeof note.score === "number" ? (
                <span className="text-[10px] text-muted-foreground">score {note.score.toFixed(2)}</span>
              ) : isExactMatch(note.origin, note.score) ? (
                <span className="text-[10px] text-muted-foreground">Exact match</span>
              ) : null}
            </div>
            <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{note.preview}</p>
          </div>
        ))}
      </div>

      {chunks.length > 0 ? (
        <details className="mt-3 border border-border bg-background p-2">
          <summary className="cursor-pointer text-xs text-muted-foreground">Preview Supporting Chunks ({Math.min(chunks.length, 3)})</summary>
          <div className="mt-2 space-y-2">
            {chunks.slice(0, 3).map((chunk) => (
              <div key={`${chunk.chunk_id}-${chunk.chunk_index}`} className="border border-border bg-muted p-2">
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                  <FolderTree className="h-3 w-3" />
                  {typeof chunk.citation_id === "number" ? <span>[{chunk.citation_id}]</span> : null}
                  <span>{chunk.document_title}</span>
                  <span>
                    {typeof chunk.chunk_end_index === "number" && chunk.chunk_end_index !== chunk.chunk_index
                      ? `chunks ${chunk.chunk_index}-${chunk.chunk_end_index}`
                      : `chunk ${chunk.chunk_index}`}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{chunk.preview}</p>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

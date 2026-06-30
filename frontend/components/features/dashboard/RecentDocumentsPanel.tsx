"use client";

import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";

import { formatBytes, formatDate } from "@/components/features/dashboard/utils";
import type { DocumentResponse } from "@/types";

interface RecentDocumentsPanelProps {
  documents: DocumentResponse[];
  isLoading: boolean;
  errorMessage: string | null;
}

export function RecentDocumentsPanel({ documents, isLoading, errorMessage }: RecentDocumentsPanelProps) {
  return (
    <section className="border border-border bg-background">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-bold text-foreground">Recent documents</h2>
        </div>
        <Link href="/dashboard/documents" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          View all
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3 p-4" aria-label="Loading recent documents">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="space-y-2 border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="h-3 w-2/5 animate-pulse bg-muted" />
              <div className="h-3 w-3/5 animate-pulse bg-muted" />
            </div>
          ))}
        </div>
      ) : errorMessage ? (
        <p className="m-4 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{errorMessage}</p>
      ) : documents.length === 0 ? (
        <div className="p-6 text-center">
          <p className="text-sm font-medium text-foreground">No documents yet</p>
          <p className="mt-1 text-xs text-muted-foreground">Upload a source to add searchable context.</p>
          <Link href="/dashboard/documents/upload" className="mt-4 inline-flex text-sm font-medium text-foreground underline underline-offset-4">
            Upload document
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {documents.map((document) => (
            <Link key={document.id} href={`/dashboard/documents/${document.id}`} className="block px-4 py-3 hover:bg-muted">
              <div className="flex items-start justify-between gap-3">
                <p className="line-clamp-1 text-sm font-medium text-foreground">{document.title}</p>
                <span className="shrink-0 text-[11px] text-muted-foreground">{formatDate(document.updated_at)}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {document.file_type.replace(".", "").toUpperCase()} / {formatBytes(document.file_size)} / {document.chunk_count} chunks
              </p>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

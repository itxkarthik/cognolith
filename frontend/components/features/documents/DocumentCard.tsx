"use client";

import { ArrowUpRight, Clock3, FileText, Trash2 } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils/cn";
import type { DocumentResponse } from "@/types";

import { formatBytes, formatDate, formatFileType, getStatusClasses } from "./utils";

interface DocumentCardProps {
  document: DocumentResponse;
  onDelete?: (id: number) => Promise<void> | void;
  isDeleting?: boolean;
}

export function DocumentCard({ document, onDelete, isDeleting = false }: DocumentCardProps) {
  const handleDeleteClick = async () => {
    if (!onDelete || isDeleting) return;

    const confirmed = window.confirm(`Delete document \"${document.title}\"? This action cannot be undone.`);
    if (!confirmed) return;

    await onDelete(document.id);
  };

  return (
    <article className="border border-border bg-background p-4 hover:bg-muted">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="inline-flex items-center gap-2 text-xs text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />
            {formatFileType(document.file_type)}
          </p>
          <h3 className="mt-2 line-clamp-1 text-lg font-bold text-foreground">{document.title}</h3>
        </div>
        <span className={cn("rounded-sm border px-2 py-1 text-xs font-medium capitalize", getStatusClasses(document.status))}>{document.status}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-muted-foreground">
        <div>
          <p className="text-xs text-muted-foreground">File Size</p>
          <p className="mt-1">{formatBytes(document.file_size)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Chunks</p>
          <p className="mt-1">{document.chunk_count}</p>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" />
          Updated {formatDate(document.updated_at)}
        </span>
        {document.tags.length > 0 ? <span className="line-clamp-1 max-w-[45%] text-right">#{document.tags.slice(0, 3).join(" #")}</span> : null}
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Link href={`/dashboard/documents/${document.id}`} className="inline-flex items-center gap-2 rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground hover:bg-accent">
          View Document
          <ArrowUpRight className="h-4 w-4" />
        </Link>
        <button
          type="button"
          onClick={() => {
            void handleDeleteClick();
          }}
          disabled={!onDelete || isDeleting}
          className="inline-flex items-center gap-2 rounded-sm border border-[#ff3b30] px-3 py-2 text-sm text-[#a50011] hover:bg-[#ff3b30]/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Trash2 className="h-4 w-4" />
          {isDeleting ? "Deleting..." : "Delete"}
        </button>
      </div>
    </article>
  );
}

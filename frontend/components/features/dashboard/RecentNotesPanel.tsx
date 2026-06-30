"use client";

import { ArrowRight, NotebookPen } from "lucide-react";
import Link from "next/link";

import { extractPreview, formatDate } from "@/components/features/dashboard/utils";
import type { NoteResponse } from "@/types";

interface RecentNotesPanelProps {
  notes: NoteResponse[];
  isLoading: boolean;
  errorMessage: string | null;
}

export function RecentNotesPanel({ notes, isLoading, errorMessage }: RecentNotesPanelProps) {
  return (
    <section className="border border-border bg-background">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <NotebookPen className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-bold text-foreground">Recent notes</h2>
        </div>
        <Link href="/dashboard/notes" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          View all
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3 p-4" aria-label="Loading recent notes">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="space-y-2 border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="h-3 w-2/5 animate-pulse bg-muted" />
              <div className="h-3 w-4/5 animate-pulse bg-muted" />
            </div>
          ))}
        </div>
      ) : errorMessage ? (
        <p className="m-4 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{errorMessage}</p>
      ) : notes.length === 0 ? (
        <div className="p-6 text-center">
          <p className="text-sm font-medium text-foreground">No notes yet</p>
          <p className="mt-1 text-xs text-muted-foreground">Create a note to start building your workspace.</p>
          <Link href="/dashboard/notes?new=1" className="mt-4 inline-flex text-sm font-medium text-foreground underline underline-offset-4">
            Create note
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {notes.map((note) => (
            <Link key={note.id} href={`/dashboard/notes?note=${note.id}`} className="block px-4 py-3 hover:bg-muted">
              <div className="flex items-start justify-between gap-3">
                <p className="line-clamp-1 text-sm font-medium text-foreground">{note.title}</p>
                <span className="shrink-0 text-[11px] text-muted-foreground">{formatDate(note.updated_at)}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{extractPreview(note.content, 140)}</p>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

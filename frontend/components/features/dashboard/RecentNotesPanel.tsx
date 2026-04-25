"use client";

import { motion } from "motion/react";
import Link from "next/link";

import {
  extractPreview,
  formatDate,
} from "@/components/features/dashboard/utils";
import type { NoteResponse } from "@/types";

interface RecentNotesPanelProps {
  notes: NoteResponse[];
  isLoading: boolean;
  errorMessage: string | null;
}

export function RecentNotesPanel({
  notes,
  isLoading,
  errorMessage,
}: RecentNotesPanelProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="rounded-2xl border border-outline-variant/30 bg-surface-container-high/70 p-5"
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-on-surface-variant">
            Recent Notes
          </p>
          <h3 className="mt-1 text-lg font-medium text-on-surface">
            Latest note updates
          </h3>
        </div>
        <Link
          href="/dashboard/notes"
          className="text-sm text-on-surface-variant/80 hover:text-on-surface"
        >
          View all
        </Link>
      </div>

      {isLoading ? (
        <ul className="space-y-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <li
              key={idx}
              className="rounded-xl border border-outline-variant/30 p-3"
            >
              <div className="h-4 w-2/3 animate-pulse rounded bg-surface-container-highest" />
              <div className="mt-2 h-3 w-full animate-pulse rounded bg-surface-container-highest" />
            </li>
          ))}
        </ul>
      ) : errorMessage ? (
        <p className="rounded-xl border border-error/50 bg-error/10 p-3 text-sm text-error">
          {errorMessage}
        </p>
      ) : notes.length === 0 ? (
        <p className="rounded-xl border border-outline-variant/30 p-3 text-sm text-on-surface-variant/80">
          No notes yet. Use Create Note to start your first note.
        </p>
      ) : (
        <ul className="space-y-3">
          {notes.map((note) => (
            <li key={note.id}>
              <Link
                href={`/dashboard/notes/${note.id}`}
                className="block rounded-xl border border-outline-variant/30 p-3 transition hover:border-outline-variant/60 hover:bg-surface-container-highest"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="line-clamp-1 font-medium text-on-surface">
                    {note.title}
                  </p>
                  <span className="shrink-0 text-xs text-on-surface-variant/70">
                    {formatDate(note.updated_at)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-on-surface-variant/80">
                  {extractPreview(note.content)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}

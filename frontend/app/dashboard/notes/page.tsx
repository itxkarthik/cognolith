"use client";

import { Grid2X2, List, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { NoteEditor } from "@/components/features/notes/NoteEditor";
import {
  getDefaultNoteTemplates,
  NoteTemplates,
} from "@/components/features/notes/NoteTemplates";
import { NoteSidebar } from "@/components/features/notes/NoteSidebar";
import { useAutoSave } from "@/lib/hooks/useAutoSave";
import { useNotes } from "@/lib/hooks/useNotes";
import type { NoteResponse } from "@/types";

function stripHtmlTags(content: string): string {
  return content.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

type DraftState = {
  title: string;
  content: string;
  tagIds: number[];
};

const EMPTY_DRAFT: DraftState = {
  title: "",
  content: "<p></p>",
  tagIds: [],
};

function draftFromNote(note: NoteResponse): DraftState {
  return {
    title: note.title,
    content: note.content || "<p></p>",
    tagIds: note.tag_ids ?? [],
  };
}

export default function NotesPage() {
  const {
    notes,
    total,
    selectedNote,
    folders,
    tags,
    filters,
    isLoading,
    isSaving,
    isDeleting,
    error,
    createNote,
    updateNoteById,
    deleteNoteById,
    createFolder,
    createTag,
    setSelectedNote,
    setSearch,
    setFolderFilter,
    setTagFilter,
    setViewMode,
    clearError,
  } = useNotes();

  const [draftsByNoteId, setDraftsByNoteId] = useState<Record<number, DraftState>>({});
  const [isCreatingNote, setIsCreatingNote] = useState(false);
  const deletingNoteIdsRef = useRef<Set<number>>(new Set());

  const draft = useMemo(() => {
    if (!selectedNote) {
      return EMPTY_DRAFT;
    }

    return draftsByNoteId[selectedNote.id] ?? draftFromNote(selectedNote);
  }, [draftsByNoteId, selectedNote]);

  useEffect(() => {
    if (!selectedNote && notes.length > 0) {
      setSelectedNote(notes[0]);
    }
  }, [notes, selectedNote, setSelectedNote]);

  const setDraftForSelectedNote = useCallback(
    (updater: (prev: DraftState) => DraftState) => {
      if (!selectedNote) {
        return;
      }

      setDraftsByNoteId((prev) => {
        const current = prev[selectedNote.id] ?? draftFromNote(selectedNote);
        return {
          ...prev,
          [selectedNote.id]: updater(current),
        };
      });
    },
    [selectedNote]
  );

  const saveDraft = useCallback(
    async (value: DraftState) => {
      if (!selectedNote) {
        return;
      }

      if (deletingNoteIdsRef.current.has(selectedNote.id)) {
        return;
      }

      await updateNoteById(selectedNote.id, {
        title: value.title.trim() || "Untitled note",
        content: value.content || "<p></p>",
        content_type: "html",
        tag_ids: value.tagIds,
        folder_id: selectedNote.folder_id ?? null,
      });
    },
    [selectedNote, updateNoteById]
  );

  const { isSaving: isAutoSaving, lastSavedAt, error: autoSaveError } = useAutoSave({
    value: draft,
    onSave: saveDraft,
    enabled: Boolean(selectedNote),
    delayMs: 850,
    skipInitial: true,
  });

  const templates = useMemo(() => getDefaultNoteTemplates(), []);

  const handleCreateNote = useCallback(async () => {
    if (isCreatingNote) {
      return;
    }

    setIsCreatingNote(true);
    try {
      const created = await createNote({
        title: "Untitled note",
        content: "<p>Start writing...</p>",
        content_type: "html",
        folder_id: filters.folderId,
        is_pinned: false,
        is_favorite: false,
        tag_ids: [],
      });
      setSelectedNote(created);
    } finally {
      setIsCreatingNote(false);
    }
  }, [createNote, filters.folderId, isCreatingNote, setSelectedNote]);

  const handleCreateFromTemplate = useCallback(
    async (template: { name: string; content: string; tags: string[] }) => {
      const templateTagIds = tags
        .filter((tag) => template.tags.some((templateTag) => templateTag === tag.name))
        .map((tag) => tag.id);

      const created = await createNote({
        title: template.name,
        content: template.content,
        content_type: "html",
        folder_id: filters.folderId,
        tag_ids: templateTagIds,
        is_pinned: false,
        is_favorite: false,
      });
      setSelectedNote(created);
    },
    [createNote, filters.folderId, setSelectedNote, tags]
  );

  const handleDeleteSelected = useCallback(async () => {
    if (!selectedNote) {
      return;
    }

    const noteId = selectedNote.id;
    const confirmed = window.confirm(
      `Delete note \"${selectedNote.title}\"? This cannot be undone.`
    );
    if (!confirmed) {
      return;
    }

    deletingNoteIdsRef.current.add(noteId);
    setSelectedNote(null);
    setDraftsByNoteId((prev) => {
      const next = { ...prev };
      delete next[noteId];
      return next;
    });

    try {
      await deleteNoteById(noteId);
      clearError();
    } finally {
      deletingNoteIdsRef.current.delete(noteId);
    }
  }, [clearError, deleteNoteById, selectedNote, setSelectedNote]);

  const isSavingState = isSaving || isAutoSaving;

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-cyan-300/60">Notes</p>
            <h1 className="mt-2 text-2xl font-semibold text-cyan-50">Notes</h1>
            <p className="mt-1 text-sm text-cyan-100/65">
              High-signal capture surface for research, meetings, and memory.
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-cyan-300/55">
              {total} {total === 1 ? "entry" : "entries"} indexed
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void handleCreateNote();
              }}
              disabled={isCreatingNote}
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-300 px-3 py-2 text-sm font-medium text-slate-900 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Plus className="h-4 w-4" />
              {isCreatingNote ? "Creating..." : "New Note"}
            </button>
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border transition ${
                filters.viewMode === "grid"
                  ? "border-cyan-400/50 bg-cyan-500/20 text-cyan-100"
                  : "border-cyan-500/30 text-cyan-200/75 hover:border-cyan-400/55"
              }`}
            >
              <Grid2X2 className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border transition ${
                filters.viewMode === "list"
                  ? "border-cyan-400/50 bg-cyan-500/20 text-cyan-100"
                  : "border-cyan-500/30 text-cyan-200/75 hover:border-cyan-400/55"
              }`}
            >
              <List className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="relative mt-4 max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-300/60" />
          <input
            type="search"
            value={filters.search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title or content"
            className="w-full rounded-lg border border-cyan-500/30 bg-cyan-500/5 py-2 pl-9 pr-3 text-sm text-cyan-50 placeholder:text-cyan-300/45 focus:border-cyan-400/60 focus:outline-none"
          />
        </div>
      </section>

      <NoteTemplates onUseTemplate={handleCreateFromTemplate} templates={templates} />

      {error ? (
        <p className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {error}
        </p>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[280px_360px_minmax(0,1fr)]">
        <NoteSidebar
          folders={folders}
          tags={tags}
          selectedFolderId={filters.folderId}
          selectedTagId={filters.tagId}
          onSelectFolder={setFolderFilter}
          onSelectTag={setTagFilter}
          onCreateFolder={() => {
            const name = window.prompt("Folder name");
            if (!name?.trim()) {
              return;
            }
            void createFolder({ name: name.trim() });
          }}
          onCreateTag={() => {
            const name = window.prompt("Tag name");
            if (!name?.trim()) {
              return;
            }
            void createTag({ name: name.trim(), color: "#a1a1aa" });
          }}
        />

        <section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-4 backdrop-blur">
          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-cyan-300/55">Entries</p>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 7 }).map((_, index) => (
                <div
                  key={index}
                  className="h-16 animate-pulse rounded-lg border border-cyan-500/20 bg-[#01040f]"
                />
              ))}
            </div>
          ) : notes.length === 0 ? (
            <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm text-cyan-100/65">
              No notes found for the current filter.
            </div>
          ) : (
            <div
              className={
                filters.viewMode === "grid"
                  ? "grid grid-cols-1 gap-2"
                  : "space-y-2"
              }
            >
              {notes.map((note) => {
                const isActive = selectedNote?.id === note.id;
                const preview = stripHtmlTags(note.content).slice(0, 140);

                return (
                  <button
                    key={note.id}
                    type="button"
                    onClick={() => setSelectedNote(note)}
                    className={`ui-card-hover w-full rounded-lg border p-3 text-left ${
                      isActive
                        ? "border-cyan-400/45 bg-cyan-500/15"
                        : "border-cyan-500/20 bg-[#01040f] hover:border-cyan-400/50"
                    }`}
                  >
                    <p className="line-clamp-1 text-sm font-semibold text-cyan-50">{note.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-cyan-100/60">{preview || "No content"}</p>
                    <div className="mt-2 flex items-center justify-between text-[10px] uppercase tracking-wider text-cyan-300/55">
                      <span>V{note.version}</span>
                      <span>{new Date(note.updated_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <NoteEditor
          note={selectedNote}
          title={draft.title}
          content={draft.content}
          selectedTagIds={draft.tagIds}
          tags={tags}
          isSaving={isSavingState}
          lastSavedAt={lastSavedAt}
          autoSaveError={autoSaveError}
          onTitleChange={(title) => {
            setDraftForSelectedNote((prev) => ({ ...prev, title }));
          }}
          onContentChange={(content) => {
            setDraftForSelectedNote((prev) => ({ ...prev, content }));
          }}
          onToggleTag={(tagId) => {
            setDraftForSelectedNote((prev) => {
              const exists = prev.tagIds.includes(tagId);
              return {
                ...prev,
                tagIds: exists
                  ? prev.tagIds.filter((id) => id !== tagId)
                  : [...prev.tagIds, tagId],
              };
            });
          }}
          onDelete={handleDeleteSelected}
          isDeleting={isDeleting}
        />
      </div>
    </div>
  );
}

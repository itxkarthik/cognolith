"use client";

import type { DocumentResponse } from "@/types";

import { DocumentCard } from "./DocumentCard";

interface DocumentListProps {
  documents: DocumentResponse[];
  isLoading: boolean;
  errorMessage: string | null;
  onDeleteDocument?: (id: number) => Promise<void> | void;
  isDeleting?: boolean;
}

export function DocumentList({ documents, isLoading, errorMessage, onDeleteDocument, isDeleting = false }: DocumentListProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div key={idx} className="border border-border bg-background p-4">
            <div className="h-3 w-24 animate-pulse bg-accent" />
            <div className="mt-3 h-5 w-2/3 animate-pulse bg-accent" />
            <div className="mt-4 h-4 w-full animate-pulse bg-accent" />
            <div className="mt-2 h-4 w-5/6 animate-pulse bg-accent" />
            <div className="mt-4 h-9 w-28 animate-pulse bg-accent" />
          </div>
        ))}
      </div>
    );
  }

  if (errorMessage) {
    return <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-sm text-[#a50011]">{errorMessage}</p>;
  }

  if (documents.length === 0) {
    return (
      <div className="border border-border bg-muted p-8 text-center">
        <h2 className="text-lg font-bold text-foreground">No documents found</h2>
        <p className="mt-2 text-sm text-muted-foreground">Upload your first document to start extracting and searching knowledge.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {documents.map((document) => (
        <DocumentCard key={document.id} document={document} onDelete={onDeleteDocument} isDeleting={isDeleting} />
      ))}
    </div>
  );
}

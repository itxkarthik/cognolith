"use client";

import { FileUp, UploadCloud } from "lucide-react";
import { useState } from "react";

import { useDocumentStore } from "@/store/documentStore";
import type { DocumentResponse } from "@/types";

interface DocumentUploadProps {
  onSuccess?: (document: DocumentResponse) => void;
}

export function DocumentUpload({ onSuccess }: DocumentUploadProps) {
  const uploadDocumentFile = useDocumentStore((state) => state.uploadDocumentFile);
  const isUploading = useDocumentStore((state) => state.isUploading);
  const storeError = useDocumentStore((state) => state.error);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [language, setLanguage] = useState("en");
  const [localError, setLocalError] = useState<string | null>(null);

  const errorMessage = localError ?? storeError;

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);

    if (!file) {
      setLocalError("Please choose a document file to upload.");
      return;
    }

    const parsedTags = tags.split(",").map((tag) => tag.trim()).filter(Boolean);

    try {
      const uploadedDocument = await uploadDocumentFile({
        file,
        title: title.trim() || undefined,
        tags: parsedTags,
        language: language.trim() || "en",
      });

      setFile(null);
      setTitle("");
      setTags("");
      onSuccess?.(uploadedDocument);
    } catch {
      // handled by store
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5 border border-border bg-background p-6">
      <div>
        <p className="text-xs text-muted-foreground">Upload</p>
        <h2 className="mt-2 text-2xl font-bold text-foreground">Add a new document</h2>
        <p className="mt-1 text-sm text-muted-foreground">Supported formats: PDF, DOCX, Markdown, and TXT.</p>
      </div>

      <div className="space-y-2">
        <label htmlFor="document-file" className="text-sm font-medium text-foreground">Document file</label>
        <div className="border border-dashed border-border bg-muted p-4">
          <input
            id="document-file"
            type="file"
            accept=".pdf,.docx,.md,.txt,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
            }}
            className="block w-full text-sm text-muted-foreground file:mr-4 file:rounded-sm file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-sm file:text-foreground"
          />
          {file ? (
            <p className="mt-2 inline-flex items-center gap-2 text-xs text-muted-foreground">
              <FileUp className="h-3.5 w-3.5" />
              {file.name}
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor="document-title" className="text-sm font-medium text-foreground">Title (optional)</label>
          <input id="document-title" type="text" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Leave blank to use filename" className="w-full rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none" />
        </div>

        <div className="space-y-2">
          <label htmlFor="document-language" className="text-sm font-medium text-foreground">Language</label>
          <input id="document-language" type="text" value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="en" className="w-full rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none" />
        </div>
      </div>

      <div className="space-y-2">
        <label htmlFor="document-tags" className="text-sm font-medium text-foreground">Tags (comma separated)</label>
        <input id="document-tags" type="text" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="research, planning, handbook" className="w-full rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none" />
      </div>

      {errorMessage ? <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 text-sm text-[#a50011]">{errorMessage}</p> : null}

      <button type="submit" disabled={isUploading} className="inline-flex items-center gap-2 rounded-sm border border-border bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60">
        <UploadCloud className="h-4 w-4" />
        {isUploading ? "Uploading..." : "Upload document"}
      </button>
    </form>
  );
}

"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DocumentViewer } from "@/components/features/documents";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { regenerateDocumentSummary } from "@/lib/api/documents";
import { useDocumentStore } from "@/store/documentStore";

// Uploads are processed in the background after the upload returns; poll until done
const PROCESSING_POLL_MS = 2000;
const PROCESSING_POLL_LIMIT_MS = 15 * 60 * 1000;

export default function DocumentDetailsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const selectedDocument = useDocumentStore((state) => state.selectedDocument);
  const isLoading = useDocumentStore((state) => state.isLoading);
  const isDeleting = useDocumentStore((state) => state.isDeleting);
  const error = useDocumentStore((state) => state.error);
  const fetchDocumentById = useDocumentStore((state) => state.fetchDocumentById);
  const clearSelectedDocument = useDocumentStore((state) => state.clearSelectedDocument);
  const refreshDocumentStatus = useDocumentStore((state) => state.refreshDocumentStatus);
  const deleteDocumentById = useDocumentStore((state) => state.deleteDocumentById);

  const documentId = Number(params.id);
  const isValidId = Number.isInteger(documentId) && documentId > 0;

  useEffect(() => {
    if (!isValidId) return;

    void fetchDocumentById(documentId);

    return () => {
      clearSelectedDocument();
    };
  }, [clearSelectedDocument, documentId, fetchDocumentById, isValidId]);

  const isProcessing = selectedDocument?.id === documentId && selectedDocument.status === "processing";

  useEffect(() => {
    if (!isProcessing) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    const poll = async () => {
      const document = await refreshDocumentStatus(documentId);
      if (cancelled) return;
      // null means the poll itself failed; keep trying until the time limit
      if (document && document.status !== "processing") return;
      if (Date.now() - startedAt < PROCESSING_POLL_LIMIT_MS) {
        timer = setTimeout(poll, PROCESSING_POLL_MS);
      }
    };
    timer = setTimeout(poll, PROCESSING_POLL_MS);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [documentId, isProcessing, refreshDocumentStatus]);

  return (
    <div className="space-y-6">
      <Link href="/dashboard/documents" className="inline-flex items-center gap-2 rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground hover:bg-accent">
        <ArrowLeft className="h-4 w-4" />
        Back to Documents
      </Link>

      {!isValidId ? (
        <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-sm text-[#a50011]">Invalid document id.</p>
      ) : isLoading && !selectedDocument ? (
        <div className="border border-border bg-background p-6">
          <LoadingSpinner label="Loading document..." />
        </div>
      ) : error ? (
        <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-sm text-[#a50011]">{error}</p>
      ) : selectedDocument ? (
        <>
          {summaryError ? <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-4 text-sm text-[#a50011]">{summaryError}</p> : null}
          <DocumentViewer
            document={selectedDocument}
            isDeleting={isDeleting}
            isGeneratingSummary={isGeneratingSummary}
            onGenerateSummary={async (id) => {
              setIsGeneratingSummary(true);
              setSummaryError(null);
              try {
                await regenerateDocumentSummary(id);
                await fetchDocumentById(id);
              } catch (summaryGenerationError) {
                setSummaryError(summaryGenerationError instanceof Error ? summaryGenerationError.message : "Failed to generate the document summary.");
              } finally {
                setIsGeneratingSummary(false);
              }
            }}
            onDelete={async (id) => {
              await deleteDocumentById(id);
              router.replace("/dashboard/documents");
            }}
          />
        </>
      ) : (
        <p className="border border-border bg-muted p-4 text-sm text-muted-foreground">Document not found.</p>
      )}
    </div>
  );
}

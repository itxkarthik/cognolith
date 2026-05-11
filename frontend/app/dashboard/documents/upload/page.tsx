"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { DocumentUpload } from "@/components/features/documents";

export default function UploadDocumentPage() {
  const router = useRouter();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/60">Documents</p>
          <h1 className="mt-2 text-3xl font-semibold text-cyan-50">Upload Document</h1>
        </div>
        <Link
          href="/dashboard/documents"
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 px-3 py-2 text-sm text-cyan-100 transition hover:border-cyan-400/55"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Documents
        </Link>
      </div>

      <DocumentUpload
        onSuccess={(document) => {
          router.push(`/dashboard/documents/${document.id}`);
        }}
      />
    </div>
  );
}

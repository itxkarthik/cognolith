"use client";

import { RefreshCw, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DocumentList } from "@/components/features/documents";
import { useDocumentStore } from "@/store/documentStore";

export default function DocumentsPage() {
  const [search, setSearch] = useState("");

  const documents = useDocumentStore((state) => state.documents);
  const total = useDocumentStore((state) => state.total);
  const isLoading = useDocumentStore((state) => state.isLoading);
  const isDeleting = useDocumentStore((state) => state.isDeleting);
  const error = useDocumentStore((state) => state.error);
  const fetchDocuments = useDocumentStore((state) => state.fetchDocuments);
  const deleteDocumentById = useDocumentStore((state) => state.deleteDocumentById);

  useEffect(() => {
    void fetchDocuments({ skip: 0, limit: 24 });
  }, [fetchDocuments]);

  const handleSearch = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await fetchDocuments({
      search: search.trim() || undefined,
      skip: 0,
      limit: 24,
    });
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-cyan-500/20 bg-[#020611]/92 p-6 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-300/60">Documents</p>
            <h1 className="mt-2 text-2xl font-semibold text-cyan-50">
              Document Library
            </h1>
            <p className="mt-2 text-sm text-cyan-100/65">
              Browse your uploaded files and manage extracted knowledge.
            </p>
            <p className="mt-3 text-xs uppercase tracking-[0.16em] text-cyan-300/55">
              {total} {total === 1 ? "document" : "documents"}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void fetchDocuments({
                  search: search.trim() || undefined,
                  skip: 0,
                  limit: 24,
                });
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/35 px-3 py-2 text-sm text-cyan-100 transition hover:border-cyan-300/65"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
            <Link
              href="/dashboard/documents/upload"
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-300 px-3 py-2 text-sm font-medium text-slate-900 transition hover:bg-cyan-200"
            >
              <Upload className="h-4 w-4" />
              Upload
            </Link>
          </div>
        </div>

        <form onSubmit={handleSearch} className="mt-5 flex flex-wrap items-center gap-2">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cyan-300/60" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title or content"
              className="w-full rounded-lg border border-cyan-500/30 bg-cyan-500/5 py-2 pl-9 pr-3 text-sm text-cyan-50 placeholder:text-cyan-300/45 focus:border-cyan-300/60 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="rounded-lg border border-cyan-500/35 px-3 py-2 text-sm text-cyan-100 transition hover:border-cyan-300/65"
          >
            Search
          </button>
        </form>
      </section>

      <DocumentList
        documents={documents}
        isLoading={isLoading}
        errorMessage={error}
        onDeleteDocument={deleteDocumentById}
        isDeleting={isDeleting}
      />
    </div>
  );
}

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
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Documents</p>
            <h1 className="mt-2 text-2xl font-semibold text-zinc-100">
              Document Library
            </h1>
            <p className="mt-2 text-sm text-zinc-300">
              Browse your uploaded files and manage extracted knowledge.
            </p>
            <p className="mt-3 text-xs uppercase tracking-[0.16em] text-zinc-500">
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
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-100 transition hover:border-zinc-500"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
            <Link
              href="/dashboard/documents/upload"
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-200"
            >
              <Upload className="h-4 w-4" />
              Upload
            </Link>
          </div>
        </div>

        <form onSubmit={handleSearch} className="mt-5 flex flex-wrap items-center gap-2">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title or content"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 py-2 pl-9 pr-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-100 transition hover:border-zinc-500"
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

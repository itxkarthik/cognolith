"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";

import {
  globalSearch,
  type SearchEntityType,
} from "@/lib/api/search";
import { SearchBar } from "@/components/features/search/SearchBar";
import { SearchFilters } from "@/components/features/search/SearchFilters";
import { SearchResults } from "@/components/features/search/SearchResults";
import type { SearchResultItem } from "@/types";

const DEFAULT_TYPES: SearchEntityType[] = ["document", "note", "chat"];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<SearchEntityType[]>(DEFAULT_TYPES);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = useCallback(
    async (targetPage: number, entityTypes: SearchEntityType[] = selectedTypes) => {
      const trimmed = query.trim();
      if (!trimmed) {
        setResults([]);
        setTotal(0);
        setPage(targetPage);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await globalSearch({
          query: trimmed,
          entityTypes,
          page: targetPage,
          pageSize: 20,
        });

        setResults(response.results);
        setTotal(response.total);
        setPage(response.page);
      } catch (error) {
        setError(error instanceof Error ? error.message : "Failed to perform search.");
      } finally {
        setIsLoading(false);
      }
    },
    [query, selectedTypes]
  );

  const pageSize = 20;
  const hasPrev = page > 1;
  const hasNext = page * pageSize < total;

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-cyan-500/22 bg-[#020611]/92 p-6 backdrop-blur">
        <p className="text-xs uppercase tracking-[0.22em] text-cyan-300/55">Discovery</p>
        <h1 className="mt-2 text-3xl font-semibold text-cyan-50">Global Search</h1>
        <p className="mt-1 text-sm text-cyan-100/65">
          Find matching context across documents, notes, and chat sessions.
        </p>

        <div className="mt-4">
          <SearchBar
            query={query}
            isLoading={isLoading}
            onQueryChange={setQuery}
            onSubmit={() => {
              void runSearch(1);
            }}
          />
        </div>
      </section>

      <SearchFilters
        selectedTypes={selectedTypes}
        onToggleType={(type) => {
          setSelectedTypes((previous) => {
            let next: SearchEntityType[];
            if (previous.includes(type)) {
              if (previous.length === 1) {
                return previous;
              }
              next = previous.filter((item) => item !== type);
            } else {
              next = [...previous, type];
            }

            if (query.trim()) {
              void runSearch(1, next);
            }

            return next;
          });
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            void runSearch(1);
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/30 px-3 py-2 text-xs text-cyan-100/75 transition hover:border-cyan-400/55 hover:text-cyan-100"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh Results
        </button>
      </div>

      {error ? (
        <p className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {error}
        </p>
      ) : null}

      <SearchResults query={query} results={results} total={total} isLoading={isLoading} />

      {total > pageSize ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!hasPrev || isLoading}
            onClick={() => {
              if (hasPrev) {
                void runSearch(page - 1);
              }
            }}
            className="rounded-lg border border-cyan-500/30 px-3 py-2 text-xs text-cyan-100/75 transition hover:border-cyan-400/55 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Previous
          </button>

          <p className="text-xs uppercase tracking-[0.12em] text-cyan-300/55">Page {page}</p>

          <button
            type="button"
            disabled={!hasNext || isLoading}
            onClick={() => {
              if (hasNext) {
                void runSearch(page + 1);
              }
            }}
            className="rounded-lg border border-cyan-500/30 px-3 py-2 text-xs text-cyan-100/75 transition hover:border-cyan-400/55 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

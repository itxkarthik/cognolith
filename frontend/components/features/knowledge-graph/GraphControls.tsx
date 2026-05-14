'use client';

import React from 'react';
import { useGraph } from '@/context/GraphContext';

export const GraphControls: React.FC = () => {
  const { filters, toggleLinkTypeFilter, setFilters, resetFilters } = useGraph();

  const linkTypes = ['related', 'referenced', 'parent', 'child'] as const;

  return (
    <div className="flex flex-col gap-4 p-4 bg-neutral-900 border border-neutral-800 rounded-lg">
      {/* Search */}
      <div>
        <label className="block text-xs font-semibold text-neutral-400 mb-2">
          Search Notes
        </label>
        <input
          type="text"
          placeholder="Search by title or content..."
          value={filters.searchQuery}
          onChange={(e) => setFilters({ searchQuery: e.target.value })}
          className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-md text-sm text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-neutral-600 focus:ring-1 focus:ring-neutral-600"
        />
      </div>

      {/* Link Type Filters */}
      <div>
        <label className="block text-xs font-semibold text-neutral-400 mb-2">
          Link Types
        </label>
        <div className="flex flex-wrap gap-2">
          {linkTypes.map((type) => (
            <button
              key={type}
              onClick={() => toggleLinkTypeFilter(type)}
              className={`px-3 py-1 text-xs rounded-md border transition-colors ${
                filters.linkTypes.has(type)
                  ? 'bg-neutral-700 border-neutral-600 text-neutral-100'
                  : 'bg-neutral-800 border-neutral-700 text-neutral-400 hover:border-neutral-600'
              }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {/* Archived Filter */}
      <div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.showArchived}
            onChange={(e) => setFilters({ showArchived: e.target.checked })}
            className="rounded border-neutral-700 bg-neutral-800 text-neutral-600"
          />
          <span className="text-xs text-neutral-400">Show archived notes</span>
        </label>
      </div>

      {/* Reset Button */}
      <button
        onClick={resetFilters}
        className="mt-2 px-3 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-md text-xs text-neutral-300 transition-colors"
      >
        Reset Filters
      </button>
    </div>
  );
};

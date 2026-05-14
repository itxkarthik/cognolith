'use client';

import React, { createContext, useContext, useState, useCallback } from 'react';

export interface GraphNode {
  id: number;
  title: string;
  content_preview: string | null;
  is_favorite: boolean;
  is_archived: boolean;
  is_pinned: boolean;
  color: string | null;
  emoji: string | null;
  created_at: string;
  updated_at: string;
}

export interface GraphEdge {
  id: number;
  source_note_id: number;
  target_note_id: number;
  link_type: 'related' | 'referenced' | 'parent' | 'child';
  description: string | null;
  created_at: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_node_id?: number;
}

export interface GraphFilters {
  linkTypes: Set<string>;
  searchQuery: string;
  showArchived: boolean;
}

interface GraphContextType {
  // Data
  graphData: GraphData | null;
  isLoading: boolean;
  error: string | null;

  // Filters & Selection
  filters: GraphFilters;
  selectedNodeId: number | null;
  hoveredNodeId: number | null;

  // Actions
  setGraphData: (data: GraphData) => void;
  setIsLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedNodeId: (id: number | null) => void;
  setHoveredNodeId: (id: number | null) => void;
  setFilters: (filters: Partial<GraphFilters>) => void;
  toggleLinkTypeFilter: (linkType: string) => void;
  resetFilters: () => void;

  // Computed
  filteredEdges: GraphEdge[];
  visibleNodes: GraphNode[];
}

const GraphContext = createContext<GraphContextType | undefined>(undefined);

export const GraphProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null);
  const [filters, setFiltersState] = useState<GraphFilters>({
    linkTypes: new Set(['related', 'referenced', 'parent', 'child']),
    searchQuery: '',
    showArchived: false,
  });

  const setFilters = useCallback((newFilters: Partial<GraphFilters>) => {
    setFiltersState((prev) => ({
      ...prev,
      ...newFilters,
    }));
  }, []);

  const toggleLinkTypeFilter = useCallback((linkType: string) => {
    setFiltersState((prev) => {
      const newTypes = new Set(prev.linkTypes);
      if (newTypes.has(linkType)) {
        newTypes.delete(linkType);
      } else {
        newTypes.add(linkType);
      }
      return { ...prev, linkTypes: newTypes };
    });
  }, []);

  const resetFilters = useCallback(() => {
    setFiltersState({
      linkTypes: new Set(['related', 'referenced', 'parent', 'child']),
      searchQuery: '',
      showArchived: false,
    });
  }, []);

  // Compute filtered edges based on link type filters
  const filteredEdges = graphData?.edges.filter((edge) => filters.linkTypes.has(edge.link_type)) ?? [];

  // Compute visible nodes based on filters and filtered edges
  const visibleNodes = graphData?.nodes.filter((node) => {
    // Filter by archived status
    if (!filters.showArchived && node.is_archived) {
      return false;
    }

    // Filter by search query
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      if (
        !node.title.toLowerCase().includes(query) &&
        !node.content_preview?.toLowerCase().includes(query)
      ) {
        // Only show if node is connected to visible edges or is the selected node
        const isConnected = filteredEdges.some(
          (edge) => edge.source_note_id === node.id || edge.target_note_id === node.id
        );
        if (!isConnected && node.id !== selectedNodeId) {
          return false;
        }
      }
    }

    return true;
  }) ?? [];

  const value: GraphContextType = {
    graphData,
    isLoading,
    error,
    filters,
    selectedNodeId,
    hoveredNodeId,
    setGraphData,
    setIsLoading,
    setError,
    setSelectedNodeId,
    setHoveredNodeId,
    setFilters,
    toggleLinkTypeFilter,
    resetFilters,
    filteredEdges,
    visibleNodes,
  };

  return <GraphContext.Provider value={value}>{children}</GraphContext.Provider>;
};

export const useGraph = (): GraphContextType => {
  const context = useContext(GraphContext);
  if (!context) {
    throw new Error('useGraph must be used within GraphProvider');
  }
  return context;
};

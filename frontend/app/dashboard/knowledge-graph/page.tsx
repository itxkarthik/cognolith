'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { GraphProvider, useGraph } from '@/context/GraphContext';
import { GraphView } from '@/components/features/knowledge-graph/GraphView';
import { GraphControls } from '@/components/features/knowledge-graph/GraphControls';
import { fetchNoteGraph } from '@/lib/api/graph';

function GraphPageContent() {
  const router = useRouter();
  const { graphData, setGraphData, setIsLoading, setError, setSelectedNodeId } = useGraph();
  const [graphMode, setGraphMode] = useState<'full' | 'focused'>('full');
  const [focusedNoteId, setFocusedNoteId] = useState<number | null>(null);

  // Load graph data on mount or when mode changes
  useEffect(() => {
    const loadGraph = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // For now, load a sample note graph (ID=1)
        // In production, this would come from a selected note or query param
        const data = await fetchNoteGraph(focusedNoteId || 1);
        setGraphData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load graph');
      } finally {
        setIsLoading(false);
      }
    };

    loadGraph();
  }, [focusedNoteId, graphMode, setGraphData, setIsLoading, setError]);

  const handleNodeClick = (noteId: number) => {
    // Navigate to note detail view
    router.push(`/dashboard/notes/${noteId}`);
  };

  return (
    <div className="w-full h-full flex flex-col bg-neutral-950">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-neutral-800">
        <div>
          <h1 className="text-2xl font-bold text-neutral-100">Knowledge Graph</h1>
          <p className="text-sm text-neutral-400 mt-1">
            {graphMode === 'full'
              ? 'Explore all your notes and their connections'
              : `Connections for note ${focusedNoteId}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setGraphMode('focused');
              setFocusedNoteId(focusedNoteId || 1);
            }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              graphMode === 'focused'
                ? 'bg-neutral-700 text-neutral-100'
                : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
            }`}
          >
            Focused
          </button>
          <button
            onClick={() => setGraphMode('full')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              graphMode === 'full'
                ? 'bg-neutral-700 text-neutral-100'
                : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
            }`}
          >
            Full Graph
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex gap-4 p-4 overflow-hidden">
        {/* Graph Canvas */}
        <div className="flex-1 min-w-0 flex flex-col">
          <GraphView onNodeClick={handleNodeClick} />
        </div>

        {/* Sidebar Controls */}
        <div className="w-80 overflow-y-auto">
          <GraphControls />
          
          {/* Node Info Panel */}
          {graphData?.nodes && graphData.nodes.length > 0 && (
            <div className="mt-4 p-4 bg-neutral-900 border border-neutral-800 rounded-lg">
              <h3 className="text-sm font-semibold text-neutral-400 mb-3">
                Statistics
              </h3>
              <div className="space-y-2 text-xs text-neutral-400">
                <div className="flex justify-between">
                  <span>Total Notes:</span>
                  <span className="text-neutral-200 font-medium">{graphData.nodes.length}</span>
                </div>
                <div className="flex justify-between">
                  <span>Total Connections:</span>
                  <span className="text-neutral-200 font-medium">{graphData.edges.length}</span>
                </div>
                <div className="flex justify-between">
                  <span>Avg Links/Note:</span>
                  <span className="text-neutral-200 font-medium">
                    {(graphData.edges.length / graphData.nodes.length).toFixed(1)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Legend */}
          <div className="mt-4 p-4 bg-neutral-900 border border-neutral-800 rounded-lg">
            <h3 className="text-sm font-semibold text-neutral-400 mb-3">
              Link Types
            </h3>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-6 h-px bg-neutral-600 border-t border-neutral-500" />
                <span className="text-neutral-400">Related</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-px border-t-2 border-dashed border-neutral-500" />
                <span className="text-neutral-400">Referenced</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-px border-t-2 border-dotted border-neutral-500" />
                <span className="text-neutral-400">Parent/Child</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgeGraphPage() {
  return (
    <GraphProvider>
      <GraphPageContent />
    </GraphProvider>
  );
}

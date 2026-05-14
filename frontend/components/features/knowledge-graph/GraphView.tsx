'use client';

import React, { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
// @ts-ignore - cytoscape-cose-bilkent doesn't have type declarations
import COSEBilkent from 'cytoscape-cose-bilkent';
import { useGraph } from '@/context/GraphContext';

// Register layout
cytoscape.use(COSEBilkent);

interface GraphViewProps {
  onNodeClick?: (nodeId: number) => void;
}

export const GraphView: React.FC<GraphViewProps> = ({ onNodeClick }) => {
  const { graphData, filteredEdges, visibleNodes, selectedNodeId, setSelectedNodeId } = useGraph();
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || !graphData || !visibleNodes) return;

    // Build elements for Cytoscape from visible nodes and filtered edges
    const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));
    
    const nodeElements = visibleNodes.map((node) => ({
      data: {
        id: node.id.toString(),
        label: node.title,
        color: node.color || '#6366f1',
        isFavorite: node.is_favorite,
        isPinned: node.is_pinned,
        isArchived: node.is_archived,
      },
      classes: [
        node.is_favorite ? 'favorite' : '',
        node.is_pinned ? 'pinned' : '',
        node.is_archived ? 'archived' : '',
        node.id === selectedNodeId ? 'selected' : '',
      ]
        .filter(Boolean)
        .join(' '),
    }));

    const edgeElements = filteredEdges
      .filter(
        (edge) =>
          visibleNodeIds.has(edge.source_note_id) && visibleNodeIds.has(edge.target_note_id)
      )
      .map((edge) => ({
        data: {
          id: `${edge.source_note_id}-${edge.target_note_id}`,
          source: edge.source_note_id.toString(),
          target: edge.target_note_id.toString(),
          linkType: edge.link_type,
          label: edge.link_type,
        },
        classes: [edge.link_type].join(' '),
      }));

    const elements = [...nodeElements, ...edgeElements];

    // Cytoscape stylesheet - Obsidian-inspired
    const stylesheet: any[] = [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          'border-color': '#444',
          'border-width': '2px',
          color: '#fff',
          'font-size': '12px',
          'text-halign': 'center',
          'text-valign': 'center',
          width: '50px',
          height: '50px',
          'text-wrap': 'wrap',
          'text-max-width': '45px',
          'overlay-padding': '5px',
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': '3px',
          'border-color': '#60a5fa',
          'box-shadow': '0 0 10px rgba(96, 165, 250, 0.5)',
        },
      },
      {
        selector: 'node:hover',
        style: {
          'border-width': '3px',
          'border-color': '#60a5fa',
        },
      },
      {
        selector: 'node.favorite',
        style: {
          'border-width': '3px',
          'border-color': '#fbbf24',
        },
      },
      {
        selector: 'node.archived',
        style: {
          opacity: '0.5',
        },
      },
      {
        selector: 'edge',
        style: {
          'line-color': '#444',
          'target-arrow-color': '#444',
          'target-arrow-shape': 'triangle',
          width: '1.5px',
          opacity: '0.5',
        },
      },
      {
        selector: 'edge:hover',
        style: {
          opacity: '1',
          'line-color': '#60a5fa',
          'target-arrow-color': '#60a5fa',
          width: '2.5px',
        },
      },
      {
        selector: 'edge.related',
        style: {
          'line-style': 'solid',
        },
      },
      {
        selector: 'edge.referenced',
        style: {
          'line-style': 'dashed',
        },
      },
      {
        selector: 'edge.parent',
        style: {
          'line-style': 'dotted',
        },
      },
      {
        selector: 'edge.child',
        style: {
          'line-style': 'dotted',
        },
      },
    ];

    const layout = {
      name: 'cose-bilkent',
      directed: true,
      animate: true,
      animationDuration: 500,
      avoidOverlap: true,
      nodeSeparation: 150,
    };

    // Create or update Cytoscape instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: stylesheet,
      layout,
      wheelSensitivity: 0.1,
      autoungrabify: false,
    });

    cyRef.current = cy;

    // Handle node click
    cy.on('tap', 'node', (event) => {
      const node = event.target;
      const nodeId = parseInt(node.data('id'));
      setSelectedNodeId(nodeId);
      onNodeClick?.(nodeId);
    });

    // Handle background click (deselect)
    cy.on('tap', (event) => {
      if (event.target === cy) {
        setSelectedNodeId(null);
      }
    });

    // Pan and zoom
    cy.panningEnabled(true);
    cy.zoomingEnabled(true);

    // Fit to view
    setTimeout(() => {
      cy.fit();
    }, 100);

    return () => {
      // Don't destroy on unmount to preserve state during re-renders
    };
  }, [graphData, visibleNodes, filteredEdges, selectedNodeId, setSelectedNodeId, onNodeClick]);

  return (
    <div className="relative w-full h-full bg-neutral-950 border border-neutral-800 rounded-lg overflow-hidden">
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ background: '#0a0a0a' }}
      />

      {/* Graph controls overlay */}
      <div className="absolute top-4 right-4 flex gap-2">
        <button
          className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded-md text-xs text-neutral-300 border border-neutral-700 transition-colors"
          onClick={() => {
            if (cyRef.current) {
              cyRef.current.fit();
            }
          }}
          title="Fit to view"
        >
          ⊡ Fit
        </button>
        <button
          className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded-md text-xs text-neutral-300 border border-neutral-700 transition-colors"
          onClick={() => {
            if (cyRef.current) {
              cyRef.current.reset();
            }
          }}
          title="Reset layout"
        >
          ↻ Reset
        </button>
      </div>

      {/* Loading state */}
      {!graphData && (
        <div className="absolute inset-0 flex items-center justify-center bg-neutral-950/50 backdrop-blur">
          <div className="text-neutral-400 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-400 mb-2" />
            <p>Loading knowledge graph...</p>
          </div>
        </div>
      )}
    </div>
  );
};

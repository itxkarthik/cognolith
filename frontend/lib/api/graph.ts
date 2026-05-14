import { GraphData, GraphNode, GraphEdge } from '@/context/GraphContext';

export interface GraphAllResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  cursor?: string;
  has_more: boolean;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_node_id?: number;
}

/**
 * Fetch the knowledge graph for a specific note (depth=1)
 */
export async function fetchNoteGraph(noteId: number): Promise<GraphResponse> {
  const response = await fetch(`/api/v1/notes/${noteId}/graph`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch note graph: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch the full user knowledge graph with pagination
 */
export async function fetchFullGraph(
  limit: number = 500,
  offset: number = 0
): Promise<GraphAllResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });

  const response = await fetch(`/api/v1/notes/graph/all?${params}`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch full graph: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create a link between two notes
 */
export async function createNoteLink(
  sourceId: number,
  targetId: number,
  linkType: 'related' | 'referenced' | 'parent' | 'child' = 'related',
  description?: string
): Promise<void> {
  const params = new URLSearchParams({
    link_type: linkType,
  });
  if (description) {
    params.append('description', description);
  }

  const response = await fetch(`/api/v1/notes/${sourceId}/links/${targetId}?${params}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to create link: ${response.statusText}`);
  }
}

/**
 * Delete a link between two notes
 */
export async function deleteNoteLink(sourceId: number, targetId: number): Promise<void> {
  const response = await fetch(`/api/v1/notes/${sourceId}/links/${targetId}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to delete link: ${response.statusText}`);
  }
}

"use client";

import { entitiesService } from "@/features/entities/api";
import type {
  EntityRelationship,
  EntitySummary,
  EntityType,
  RelationshipType,
  TraversalDirection,
} from "@/features/entities/types";
import { buildNetwork, neighbourhood } from "@/features/graph/lib/build-network";
import { shortestPath } from "@/features/graph/lib/graph-analytics";
import type { LayoutKind } from "@/features/graph/lib/graph-layouts";
import { useQueries } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

export interface GraphFilters {
  entityTypes: EntityType[];
  relationshipTypes: RelationshipType[];
  minWeight: number;
  direction: TraversalDirection;
}

export const EMPTY_GRAPH_FILTERS: GraphFilters = {
  entityTypes: [],
  relationshipTypes: [],
  minWeight: 0,
  direction: "both",
};

export type ColorMode = "type" | "community";
export type SizeMode = "degree" | "importance";

const HOP_LIMIT = 250;

/**
 * The explore state machine for the network viewer. Holds the seed set, which
 * nodes the user has expanded / hidden / dragged, the active layout, and the
 * colour / size / path-finding modes; fans one depth-1
 * `GET /entities/{id}/graph` out per seed / expanded node and merges the
 * responses into a single laid-out graph.
 */
export function useGraphExplore(datasetId: string | undefined) {
  const [seedIds, setSeedIds] = useState<string[]>([]);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<GraphFilters>(EMPTY_GRAPH_FILTERS);

  const [layout, setLayoutState] = useState<LayoutKind>("force");
  const [relayoutNonce, setRelayoutNonce] = useState(0);
  const [colorMode, setColorMode] = useState<ColorMode>("type");
  const [sizeMode, setSizeMode] = useState<SizeMode>("degree");

  const [pathMode, setPathMode] = useState(false);
  const [pathAnchors, setPathAnchors] = useState<string[]>([]);
  const [highlightQuery, setHighlightQuery] = useState("");

  // Manual node positions. Kept out of the `built` memo deps so a drag doesn't
  // trigger the expensive rebuild, but re-applied by `buildNetwork` after an
  // expand so the user's arrangement survives.
  const [pinned, setPinned] = useState<Map<string, { x: number; y: number }>>(
    new Map()
  );

  const fetchIds = useMemo(
    () => Array.from(new Set([...seedIds, ...expandedIds])),
    [seedIds, expandedIds]
  );

  const relTypesKey = filters.relationshipTypes.join(",");
  const results = useQueries({
    queries: fetchIds.map((id) => ({
      queryKey: [
        "graph-explore",
        id,
        filters.direction,
        relTypesKey,
        filters.minWeight,
      ] as const,
      queryFn: () =>
        entitiesService.getGraph(id, {
          depth: 1,
          direction: filters.direction,
          types: filters.relationshipTypes.length
            ? filters.relationshipTypes
            : undefined,
          minWeight: filters.minWeight || undefined,
          limit: HOP_LIMIT,
        }),
      enabled: !!datasetId,
      staleTime: 30_000,
    })),
  });

  const isLoading = results.some((r) => r.isLoading);
  const isError = results.length > 0 && results.every((r) => r.isError);
  // Stable-ish signature so the expensive merge + layout only re-runs on new data.
  const dataSig = results.map((r) => r.dataUpdatedAt ?? 0).join(",");

  const merged = useMemo(() => {
    const nodeMap = new Map<string, EntitySummary>();
    const edgeMap = new Map<string, EntityRelationship>();
    for (const r of results) {
      const data = r.data;
      if (!data) continue;
      for (const n of data.nodes) if (!nodeMap.has(n.id)) nodeMap.set(n.id, n);
      for (const e of data.edges) {
        const key = `${e.srcEntityId}|${e.dstEntityId}|${e.relationshipType}`;
        if (!edgeMap.has(key)) edgeMap.set(key, e);
      }
    }
    return { nodes: [...nodeMap.values()], edges: [...edgeMap.values()] };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dataSig captures result content
  }, [dataSig]);

  const seedSet = useMemo(() => new Set(seedIds), [seedIds]);
  const expandedSet = useMemo(() => new Set(expandedIds), [expandedIds]);

  const built = useMemo(() => {
    if (merged.nodes.length === 0) return null;
    return buildNetwork({
      nodes: merged.nodes,
      edges: merged.edges,
      seedIds: seedSet,
      expandedIds: expandedSet,
      layout,
      pinned,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `pinned` read at build time but must not retrigger a rebuild on drag
  }, [merged, seedSet, expandedSet, layout, relayoutNonce]);

  const addSeed = useCallback((id: string) => {
    setSeedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    setHiddenIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const removeSeed = useCallback((id: string) => {
    setSeedIds((prev) => prev.filter((s) => s !== id));
    setExpandedIds((prev) => prev.filter((e) => e !== id));
  }, []);

  const expand = useCallback((id: string) => {
    setExpandedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  }, []);

  const collapse = useCallback((id: string) => {
    setExpandedIds((prev) => prev.filter((e) => e !== id));
  }, []);

  const hide = useCallback((id: string) => {
    setHiddenIds((prev) => new Set(prev).add(id));
  }, []);

  const unhideAll = useCallback(() => setHiddenIds(new Set()), []);

  const isolate = useCallback(
    (id: string) => {
      if (!built) return;
      const keep = neighbourhood(built.graph, id);
      const next = new Set<string>();
      built.graph.forEachNode((n) => {
        if (!keep.has(n)) next.add(n);
      });
      setHiddenIds(next);
    },
    [built]
  );

  const pinPosition = useCallback(
    (id: string, pos: { x: number; y: number }) => {
      setPinned((prev) => new Map(prev).set(id, pos));
    },
    []
  );

  const setLayout = useCallback((kind: LayoutKind) => {
    setPinned(new Map());
    setLayoutState(kind);
  }, []);

  const relayout = useCallback(() => {
    setPinned(new Map());
    setRelayoutNonce((n) => n + 1);
  }, []);

  const togglePathMode = useCallback(() => {
    setPathMode((on) => {
      if (on) setPathAnchors([]);
      return !on;
    });
  }, []);

  const pushPathAnchor = useCallback((id: string) => {
    setPathAnchors((prev) => {
      if (prev.includes(id)) return prev.filter((p) => p !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  }, []);

  const clearPath = useCallback(() => setPathAnchors([]), []);

  const reset = useCallback(() => {
    setPinned(new Map());
    setSeedIds([]);
    setExpandedIds([]);
    setHiddenIds(new Set());
    setPathAnchors([]);
    setPathMode(false);
    setHighlightQuery("");
  }, []);

  const pathIds = useMemo(() => {
    if (!built || pathAnchors.length < 2) return [] as string[];
    return shortestPath(built.graph, pathAnchors[0], pathAnchors[1]) ?? [];
  }, [built, pathAnchors]);

  const highlightIds = useMemo(() => {
    const q = highlightQuery.trim().toLowerCase();
    const set = new Set<string>();
    if (!built || q.length < 2) return set;
    built.graph.forEachNode((id, attrs) => {
      if (
        String(attrs.label ?? "")
          .toLowerCase()
          .includes(q)
      )
        set.add(id);
    });
    return set;
  }, [built, highlightQuery]);

  const visibleNodeCount = useMemo(() => {
    if (!built) return 0;
    let n = 0;
    built.graph.forEachNode((id, attrs) => {
      if (hiddenIds.has(id)) return;
      if (
        filters.entityTypes.length &&
        !filters.entityTypes.includes(attrs.entityType as EntityType)
      )
        return;
      n += 1;
    });
    return n;
  }, [built, hiddenIds, filters.entityTypes]);

  return {
    seedIds,
    expandedIds,
    expandedSet,
    hiddenIds,
    filters,
    setFilters,
    built,
    isLoading,
    isError,
    nodeCount: built?.nodeCount ?? 0,
    edgeCount: built?.edgeCount ?? 0,
    communityCount: built?.communityCount ?? 0,
    visibleNodeCount,
    layout,
    setLayout,
    relayout,
    colorMode,
    setColorMode,
    sizeMode,
    setSizeMode,
    pathMode,
    togglePathMode,
    pathAnchors,
    pushPathAnchor,
    clearPath,
    pathIds,
    highlightQuery,
    setHighlightQuery,
    highlightIds,
    addSeed,
    removeSeed,
    expand,
    collapse,
    hide,
    unhideAll,
    isolate,
    pinPosition,
    reset,
  };
}

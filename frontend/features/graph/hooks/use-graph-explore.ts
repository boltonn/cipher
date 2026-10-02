"use client";

import { entitiesService } from "@/features/entities/api";
import type {
  EntityRelationship,
  GraphNode,
  GraphNodeType,
  RelationshipType,
  TraversalDirection,
} from "@/features/entities/types";
import { buildNetwork, neighbourhood } from "@/features/graph/lib/build-network";
import { shortestPath } from "@/features/graph/lib/graph-analytics";
import type { LayoutKind } from "@/features/graph/lib/graph-layouts";
import { edgeInWindow, toTimeWindow } from "@/features/graph/lib/time-window";
import { useLocalStorageState } from "@/hooks/use-local-storage-state";
import { useQueries } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

export interface GraphFilters {
  entityTypes: GraphNodeType[];
  relationshipTypes: RelationshipType[];
  minWeight: number;
  direction: TraversalDirection;
  /** ISO timestamps bounding when a dated edge must have been active; client-side only */
  dateFrom: string | undefined;
  dateTo: string | undefined;
}

export const EMPTY_GRAPH_FILTERS: GraphFilters = {
  entityTypes: [],
  relationshipTypes: [],
  minWeight: 0,
  direction: "both",
  dateFrom: undefined,
  dateTo: undefined,
};

export type ColorMode = "type" | "community";
export type SizeMode = "degree" | "importance";

export const HOP_LIMIT = 250;

const NO_IDS: string[] = [];

/**
 * The explore state machine for the network viewer. Holds the seed set, which
 * nodes the user has expanded / hidden / dragged, the active layout, and the
 * colour / size / path-finding modes; fans one depth-1
 * `GET /entities/{id}/graph` out per seed / expanded node and merges the
 * responses into a single laid-out graph. Seeds / expanded / hidden survive a
 * page navigation (localStorage) so opening an entity doesn't lose the canvas.
 */
export function useGraphExplore(datasetId: string | undefined) {
  const [seedIds, setSeedIds] = useLocalStorageState<string[]>("graph:seedIds", NO_IDS);
  const [expandedIds, setExpandedIds] = useLocalStorageState<string[]>("graph:expandedIds", NO_IDS);
  const [hiddenList, setHiddenList] = useLocalStorageState<string[]>("graph:hiddenIds", NO_IDS);
  const hiddenIds = useMemo(() => new Set(hiddenList), [hiddenList]);
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
  // any failure: with nothing built the page shows the error rather than "No connections"
  const isError = results.some((r) => r.isError);
  // Stable-ish signature so the expensive merge + layout only re-runs on new data.
  const dataSig = results.map((r) => r.dataUpdatedAt ?? 0).join(",");

  const merged = useMemo(() => {
    const nodeMap = new Map<string, GraphNode>();
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

  const addSeed = useCallback(
    (id: string) => {
      setSeedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
      setHiddenList((prev) => (prev.includes(id) ? prev.filter((h) => h !== id) : prev));
    },
    [setSeedIds, setHiddenList]
  );

  const removeSeed = useCallback(
    (id: string) => {
      setSeedIds((prev) => prev.filter((s) => s !== id));
      setExpandedIds((prev) => prev.filter((e) => e !== id));
    },
    [setSeedIds, setExpandedIds]
  );

  const addSeeds = useCallback(
    (ids: string[]) => {
      setSeedIds((prev) => [...new Set([...prev, ...ids])]);
      setHiddenList((prev) => prev.filter((h) => !ids.includes(h)));
    },
    [setSeedIds, setHiddenList]
  );

  const expandMany = useCallback(
    (ids: string[]) => setExpandedIds((prev) => [...new Set([...prev, ...ids])]),
    [setExpandedIds]
  );
  const expand = useCallback((id: string) => expandMany([id]), [expandMany]);

  const collapse = useCallback(
    (id: string) => {
      setExpandedIds((prev) => prev.filter((e) => e !== id));
    },
    [setExpandedIds]
  );

  const hideMany = useCallback(
    (ids: string[]) => setHiddenList((prev) => [...new Set([...prev, ...ids])]),
    [setHiddenList]
  );
  const hide = useCallback((id: string) => hideMany([id]), [hideMany]);

  const unhideAll = useCallback(() => setHiddenList(NO_IDS), [setHiddenList]);

  const isolateMany = useCallback(
    (ids: string[]) => {
      if (!built) return;
      const keep = new Set(ids.flatMap((id) => [...neighbourhood(built.graph, id)]));
      setHiddenList(built.graph.filterNodes((n) => !keep.has(n)));
    },
    [built, setHiddenList]
  );
  const isolate = useCallback((id: string) => isolateMany([id]), [isolateMany]);

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
    setSeedIds(NO_IDS);
    setExpandedIds(NO_IDS);
    setHiddenList(NO_IDS);
    setFilters(EMPTY_GRAPH_FILTERS);
    setPathAnchors([]);
    setPathMode(false);
    setHighlightQuery("");
  }, [setSeedIds, setExpandedIds, setHiddenList]);

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

  const timeWindow = useMemo(
    () => toTimeWindow(filters.dateFrom, filters.dateTo),
    [filters.dateFrom, filters.dateTo]
  );

  // Nodes the time window empties out: every edge they have is dated and falls
  // outside it. Seeds stay so the canvas never loses its anchors.
  const timeHiddenIds = useMemo(() => {
    const out = new Set<string>();
    if (!built || !timeWindow) return out;
    const { graph } = built;
    graph.forEachNode((id) => {
      if (seedSet.has(id) || graph.degree(id) === 0) return;
      if (!graph.someEdge(id, (_e, attrs) => edgeInWindow(attrs, timeWindow))) {
        out.add(id);
      }
    });
    return out;
  }, [built, timeWindow, seedSet]);

  const visible = useMemo(() => {
    if (!built) return { nodes: 0, edges: 0 };
    const { graph } = built;
    const shown = (id: string) =>
      !hiddenIds.has(id) &&
      !timeHiddenIds.has(id) &&
      (!filters.entityTypes.length ||
        filters.entityTypes.includes(
          graph.getNodeAttribute(id, "entityType") as GraphNodeType
        ));
    return {
      nodes: graph.filterNodes(shown).length,
      edges: graph.filterEdges(
        (_e, attrs, src, dst) =>
          shown(src) &&
          shown(dst) &&
          (!timeWindow || edgeInWindow(attrs, timeWindow))
      ).length,
    };
  }, [built, hiddenIds, timeHiddenIds, timeWindow, filters.entityTypes]);

  // Nodes whose depth-1 fetch hit HOP_LIMIT: only their heaviest edges are drawn.
  const truncatedIds = useMemo(
    () =>
      new Set(
        fetchIds.filter((_id, i) => {
          const data = results[i]?.data;
          return data?.truncated ?? (data?.edges.length ?? 0) >= HOP_LIMIT;
        })
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dataSig captures result content
    [fetchIds, dataSig]
  );

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
    visibleNodeCount: visible.nodes,
    visibleEdgeCount: visible.edges,
    truncatedIds,
    timeWindow,
    timeHiddenIds,
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
    addSeeds,
    removeSeed,
    expand,
    expandMany,
    collapse,
    hide,
    hideMany,
    unhideAll,
    isolate,
    isolateMany,
    pinPosition,
    reset,
  };
}

"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PageError, PageLoading } from "@/components/page-loading";
import { EdgeInspector } from "@/features/graph/components/edge-inspector";
import {
  GraphContextMenu,
  type ContextTarget,
} from "@/features/graph/components/graph-context-menu";
import { DatasetSelect } from "@/features/datasets/components/dataset-select";
import { useDatasetScope } from "@/features/datasets/hooks/use-selected-datasets";
import { GraphLegend } from "@/features/graph/components/graph-legend";
import { GraphSelectionBar } from "@/features/graph/components/graph-selection-bar";
import { GraphTimeBar } from "@/features/graph/components/graph-time-bar";
import { GraphToolbar } from "@/features/graph/components/graph-toolbar";
import type {
  EdgePick,
  LabelsMode,
} from "@/features/graph/components/network-canvas";
import { EventNodeInspector } from "@/features/graph/components/event-node-inspector";
import { NodeInspector } from "@/features/graph/components/node-inspector";
import { useGraphExplore } from "@/features/graph/hooks/use-graph-explore";
import { Database, Loader2, Route, Share2, Waypoints, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

// sigma is browser-only (reads WebGL globals at module scope).
const NetworkCanvas = dynamic(
  () =>
    import("@/features/graph/components/network-canvas").then(
      (m) => m.NetworkCanvas
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center rounded-xl border border-border bg-background text-xs text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading canvas…
      </div>
    ),
  }
);

function GraphPageInner() {
  const searchParams = useSearchParams();
  const processed = useRef(false);

  const { datasetIds, setDatasetIds } = useDatasetScope();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<EdgePick | null>(null);
  const [contextTarget, setContextTarget] = useState<ContextTarget | null>(null);
  const [labelsMode, setLabelsMode] = useState<LabelsMode>("all");
  const [labelDensity, setLabelDensity] = useState(1);
  const [liveLayout, setLiveLayout] = useState(false);
  const [exportNonce, setExportNonce] = useState(0);
  const [timeBarOpen, setTimeBarOpen] = useState(false);
  const [multiIds, setMultiIds] = useState<string[]>([]);

  const explore = useGraphExplore(datasetIds);
  const { addSeed } = explore;

  useEffect(() => {
    if (processed.current) return;
    const qsSeed = searchParams.get("seed");
    if (qsSeed) addSeed(qsSeed);
    processed.current = true;
  }, [searchParams, addSeed]);

  const graph = explore.built?.graph;
  const seeds = explore.seedIds.map((id) => ({
    id,
    label: graph?.hasNode(id)
      ? String(graph.getNodeAttribute(id, "label"))
      : "Loading…",
  }));
  const removeSeed = (id: string) => {
    explore.removeSeed(id);
    if (selectedId === id) setSelectedId(null);
    setSelectedEdge(null);
  };
  const selectNode = (id: string) => {
    setSelectedEdge(null);
    setSelectedId(id);
  };
  const multiSet = new Set(multiIds);
  const toggleMulti = (id: string) =>
    setMultiIds((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  const withMulti = (action: (ids: string[]) => void) => () => {
    action(multiIds);
    setMultiIds([]);
  };

  const selectedIsEvent =
    !!selectedId &&
    !!explore.built?.graph.hasNode(selectedId) &&
    explore.built.graph.getNodeAttribute(selectedId, "entityType") === "event";
  const selectedIsSeed = selectedId ? explore.seedIds.includes(selectedId) : false;
  const selectedIsExpanded = selectedId
    ? explore.expandedSet.has(selectedId)
    : false;
  const ctxIsSeed = contextTarget
    ? explore.seedIds.includes(contextTarget.id)
    : false;
  const ctxIsExpanded = contextTarget
    ? explore.expandedSet.has(contextTarget.id)
    : false;

  const handleSelect = (id: string | null) => {
    if (id && explore.pathMode) {
      explore.pushPathAnchor(id);
      return;
    }
    setMultiIds([]);
    setSelectedEdge(null);
    setSelectedId(id);
  };

  return (
    <div className="relative mx-auto flex h-full w-full max-w-400 flex-col px-6 pb-6 pt-5">
      <PageHeader
        eyebrow="Graph"
        icon={<Waypoints size={12} className="text-primary/70" />}
        value={
          datasetIds.length === 0
            ? "No dataset selected"
            : !explore.nodeCount
              ? "No nodes"
              : explore.visibleNodeCount === explore.nodeCount
                ? `${explore.nodeCount.toLocaleString()} nodes`
                : `${explore.visibleNodeCount.toLocaleString()} of ${explore.nodeCount.toLocaleString()} nodes`
        }
        actions={
          <DatasetSelect
            datasetIds={datasetIds}
            onChange={(ids) => {
              setDatasetIds(ids);
              explore.reset();
              setSelectedId(null);
              setSelectedEdge(null);
            }}
          />
        }
      />

      <div className="mt-4 shrink-0">
        <GraphToolbar
          datasetIds={datasetIds}
          filters={explore.filters}
          onFiltersChange={explore.setFilters}
          labelsMode={labelsMode}
          onLabelsModeChange={setLabelsMode}
          labelDensity={labelDensity}
          onLabelDensityChange={setLabelDensity}
          layout={explore.layout}
          onLayoutChange={explore.setLayout}
          onRelayout={explore.relayout}
          liveLayout={liveLayout}
          onToggleLiveLayout={() => setLiveLayout((v) => !v)}
          colorMode={explore.colorMode}
          onColorModeChange={explore.setColorMode}
          communityCount={explore.communityCount}
          sizeMode={explore.sizeMode}
          onSizeModeChange={explore.setSizeMode}
          pathMode={explore.pathMode}
          onTogglePathMode={explore.togglePathMode}
          pathAnchorCount={explore.pathAnchors.length}
          onExportPng={() => setExportNonce((n) => n + 1)}
          timeBarOpen={timeBarOpen}
          onToggleTimeBar={() => setTimeBarOpen((v) => !v)}
          onAddSeed={explore.addSeed}
          seeds={seeds}
          onRemoveSeed={removeSeed}
          onSelectSeed={selectNode}
          onHighlightChange={explore.setHighlightQuery}
          onReset={() => {
            explore.reset();
            setSelectedId(null);
            setSelectedEdge(null);
          }}
          hiddenCount={explore.hiddenIds.size}
          onUnhideAll={explore.unhideAll}
          visibleNodeCount={explore.visibleNodeCount}
          nodeCount={explore.nodeCount}
          edgeCount={explore.edgeCount}
          visibleEdgeCount={explore.visibleEdgeCount}
          truncatedCount={explore.truncatedIds.size}
          isLoading={explore.isLoading}
        />
      </div>

      {timeBarOpen && explore.built && (
        <GraphTimeBar
          graph={explore.built.graph}
          dateFrom={explore.filters.dateFrom}
          dateTo={explore.filters.dateTo}
          onChange={(range) => explore.setFilters({ ...explore.filters, ...range })}
          onClose={() => setTimeBarOpen(false)}
        />
      )}

      {explore.pathMode && explore.pathAnchors.length === 2 && (
        <div className="mt-2 flex shrink-0 items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs text-primary">
          <Route size={13} />
          {explore.pathIds.length
            ? `Shortest path · ${explore.pathIds.length - 1} hop${
                explore.pathIds.length - 1 === 1 ? "" : "s"
              }`
            : "No path between the two nodes"}
          <button
            type="button"
            onClick={explore.clearPath}
            className="ml-auto inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
          >
            <X size={12} /> Clear
          </button>
        </div>
      )}

      <div className="relative z-0 mt-3 min-h-0 flex-1">
        <div className="h-full">
          {datasetIds.length === 0 ? (
            <EmptyState
              icon={Database}
              title="Choose datasets"
              body="The network is scoped to the datasets you pick. Choose one or more from the selector in the top bar, then add entities to explore their connections."
            />
          ) : explore.seedIds.length === 0 ? (
            <EmptyState
              icon={Share2}
              title="Add an entity to start"
              body="Search for a person, organization, location, or selector in the toolbar. Double-click any node on the canvas to pull in its neighbours."
            />
          ) : explore.isError && !explore.built ? (
            <PageError
              title="Couldn’t build the graph"
              body="The relationship traversal failed for every seed. This is usually temporary — try again."
              onRetry={explore.reset}
            />
          ) : explore.isLoading && !explore.built ? (
            <PageLoading icon={Waypoints} label="Building graph…" />
          ) : explore.built ? (
            <NetworkCanvas
              built={explore.built}
              hiddenIds={explore.hiddenIds}
              timeHiddenIds={explore.timeHiddenIds}
              timeWindow={explore.timeWindow}
              multiIds={multiSet}
              visibleTypes={explore.filters.entityTypes}
              visibleRelTypes={explore.filters.relationshipTypes}
              labelsMode={labelsMode}
              labelDensity={labelDensity}
              colorMode={explore.colorMode}
              sizeMode={explore.sizeMode}
              liveLayout={liveLayout}
              selectedId={selectedId}
              selectedEdgeId={selectedEdge?.id ?? null}
              highlightIds={explore.highlightIds}
              pathIds={explore.pathIds}
              pathAnchors={explore.pathAnchors}
              exportNonce={exportNonce}
              onSelect={handleSelect}
              onToggleMulti={toggleMulti}
              onSelectEdge={(e) => {
                if (e) setSelectedId(null);
                setSelectedEdge(e);
              }}
              onNodeContextMenu={setContextTarget}
              onDragEnd={explore.pinPosition}
              onExpand={explore.expand}
            />
          ) : (
            <EmptyState
              icon={Share2}
              title="No connections"
              body="None of the seed entities have relationships in this dataset yet."
            />
          )}
        </div>

        {multiIds.length > 0 && explore.built && (
          <GraphSelectionBar
            count={multiIds.length}
            onExpand={withMulti(explore.expandMany)}
            onIsolate={withMulti(explore.isolateMany)}
            onHide={withMulti(explore.hideMany)}
            onAddSeeds={withMulti(explore.addSeeds)}
            onClear={() => setMultiIds([])}
          />
        )}

        {explore.built && explore.seedIds.length > 0 && (
          <GraphLegend
            graph={explore.built.graph}
            hiddenIds={explore.hiddenIds}
            timeHiddenIds={explore.timeHiddenIds}
            colorMode={explore.colorMode}
            visibleTypes={explore.filters.entityTypes}
            onToggleType={(type) =>
              explore.setFilters({
                ...explore.filters,
                entityTypes: explore.filters.entityTypes.includes(type)
                  ? explore.filters.entityTypes.filter((t) => t !== type)
                  : [...explore.filters.entityTypes, type],
              })
            }
          />
        )}

        {selectedId && selectedIsEvent && (
          <EventNodeInspector
            key={selectedId}
            eventId={selectedId}
            isExpanded={selectedIsExpanded}
            onClose={() => setSelectedId(null)}
            onExpand={explore.expand}
            onCollapse={explore.collapse}
            onHide={(id) => {
              explore.hide(id);
              setSelectedId(null);
            }}
            onIsolate={explore.isolate}
          />
        )}

        {selectedId && !selectedIsEvent && (
          <NodeInspector
            key={selectedId}
            entityId={selectedId}
            graph={graph}
            isSeed={selectedIsSeed}
            isExpanded={selectedIsExpanded}
            isTruncated={explore.truncatedIds.has(selectedId)}
            onClose={() => setSelectedId(null)}
            onSelect={selectNode}
            onAddSeed={explore.addSeed}
            onRemoveSeed={removeSeed}
            onExpand={explore.expand}
            onCollapse={explore.collapse}
            onHide={(id) => {
              explore.hide(id);
              setSelectedId(null);
            }}
            onIsolate={explore.isolate}
          />
        )}

        {!selectedId && selectedEdge && (
          <EdgeInspector
            key={selectedEdge.id}
            edge={selectedEdge}
            onClose={() => setSelectedEdge(null)}
          />
        )}
      </div>

      {contextTarget && explore.built && (
        <GraphContextMenu
          target={contextTarget}
          isSeed={ctxIsSeed}
          isExpanded={ctxIsExpanded}
          pathMode={explore.pathMode}
          onClose={() => setContextTarget(null)}
          onInspect={selectNode}
          onExpand={explore.expand}
          onCollapse={explore.collapse}
          onAddSeed={explore.addSeed}
          onRemoveSeed={removeSeed}
          onIsolate={explore.isolate}
          onHide={(id) => {
            explore.hide(id);
            if (selectedId === id) setSelectedId(null);
          }}
          onPathAnchor={explore.pushPathAnchor}
        />
      )}
    </div>
  );
}

export default function GraphPage() {
  return (
    <Suspense>
      <GraphPageInner />
    </Suspense>
  );
}

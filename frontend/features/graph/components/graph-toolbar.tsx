"use client";

import {
  Autocomplete,
  AutocompleteContent,
  AutocompleteInput,
  AutocompleteItem,
} from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ENTITY_TYPE_META,
  GRAPH_NODE_TYPE_META,
} from "@/features/entities/components/entity-type-meta";
import { useEntitySearch } from "@/features/entities/hooks/use-entities";
import {
  GRAPH_NODE_TYPES,
  RELATIONSHIP_TYPES,
  type GraphNodeType,
  type RelationshipType,
  type TraversalDirection,
} from "@/features/entities/types";
import type { LabelsMode } from "@/features/graph/components/network-canvas";
import type {
  ColorMode,
  GraphFilters,
  SizeMode,
} from "@/features/graph/hooks/use-graph-explore";
import {
  LAYOUT_KINDS,
  LAYOUT_LABELS,
  type LayoutKind,
} from "@/features/graph/lib/graph-layouts";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";
import {
  Download,
  Eye,
  Info,
  Loader2,
  Play,
  RotateCcw,
  RotateCw,
  Route,
  SlidersHorizontal,
  Tag,
} from "lucide-react";
import { useEffect, useState } from "react";

const DIRECTIONS: { value: TraversalDirection; label: string }[] = [
  { value: "both", label: "Both" },
  { value: "out", label: "Out" },
  { value: "in", label: "In" },
];

const LABEL_MODES: { value: LabelsMode; label: string }[] = [
  { value: "all", label: "All" },
  { value: "hover", label: "Hover" },
  { value: "off", label: "Off" },
];

/** One shell height for every control on the bar. */
const CTRL = "h-9";

/** Backend entity name search needs at least this many characters to match. */
const ENTITY_SEARCH_MIN_CHARS = 2;

interface GraphToolbarProps {
  datasetId: string | undefined;
  filters: GraphFilters;
  onFiltersChange: (next: GraphFilters) => void;
  labelsMode: LabelsMode;
  onLabelsModeChange: (mode: LabelsMode) => void;
  labelDensity: number;
  onLabelDensityChange: (v: number) => void;
  layout: LayoutKind;
  onLayoutChange: (k: LayoutKind) => void;
  onRelayout: () => void;
  liveLayout: boolean;
  onToggleLiveLayout: () => void;
  colorMode: ColorMode;
  onColorModeChange: (m: ColorMode) => void;
  communityCount: number;
  sizeMode: SizeMode;
  onSizeModeChange: (m: SizeMode) => void;
  pathMode: boolean;
  onTogglePathMode: () => void;
  pathAnchorCount: number;
  onExportPng: () => void;
  onAddSeed: (id: string) => void;
  onHighlightChange: (q: string) => void;
  onReset: () => void;
  hiddenCount: number;
  onUnhideAll: () => void;
  visibleNodeCount: number;
  nodeCount: number;
  edgeCount: number;
  isLoading: boolean;
}

export function GraphToolbar({
  datasetId,
  filters,
  onFiltersChange,
  labelsMode,
  onLabelsModeChange,
  labelDensity,
  onLabelDensityChange,
  layout,
  onLayoutChange,
  onRelayout,
  liveLayout,
  onToggleLiveLayout,
  colorMode,
  onColorModeChange,
  communityCount,
  sizeMode,
  onSizeModeChange,
  pathMode,
  onTogglePathMode,
  pathAnchorCount,
  onExportPng,
  onAddSeed,
  onHighlightChange,
  onReset,
  hiddenCount,
  onUnhideAll,
  visibleNodeCount,
  nodeCount,
  edgeCount,
  isLoading,
}: GraphToolbarProps) {
  const [q, setQ] = useState("");
  const [minWeightDraft, setMinWeightDraft] = useState(filters.minWeight);
  const debouncedQ = useDebounce(q, 350);
  const trimmed = q.trim();
  const searchable = debouncedQ.trim().length >= ENTITY_SEARCH_MIN_CHARS;
  const { data: results, isFetching } = useEntitySearch(
    { datasetId, q: debouncedQ.trim() },
    searchable
  );

  // True while the query the user sees hasn't been searched yet: either the
  // debounce hasn't caught up, or the request is still in flight. Used to hold
  // back the "No matches" message until a real result comes back.
  const pendingSearch =
    trimmed.length >= ENTITY_SEARCH_MIN_CHARS &&
    (isFetching || debouncedQ.trim() !== trimmed);

  const emptyMessage =
    trimmed.length === 0
      ? "Type to find an entity"
      : trimmed.length < ENTITY_SEARCH_MIN_CHARS
        ? `Type at least ${ENTITY_SEARCH_MIN_CHARS} characters`
        : "No matches";

  // Canvas node-highlight follows the debounced query, not every keystroke.
  useEffect(() => {
    onHighlightChange(debouncedQ);
  }, [debouncedQ, onHighlightChange]);

  const activeFilterCount =
    filters.entityTypes.length +
    filters.relationshipTypes.length +
    (filters.minWeight > 0 ? 1 : 0) +
    (filters.direction !== "both" ? 1 : 0);

  const toggle = <T,>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-muted/30 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <Autocomplete className="w-72">
          <AutocompleteInput
            className={cn(CTRL, "rounded-md")}
            value={q}
            onValueChange={setQ}
            placeholder={datasetId ? "Add / find an entity…" : "Pick a dataset above first"}
            disabled={!datasetId}
          />
          <AutocompleteContent
            isLoading={pendingSearch}
            emptyMessage={emptyMessage}
          >
            {(searchable ? (results ?? []) : []).map((r) => {
              const meta = ENTITY_TYPE_META[r.entityType];
              return (
                <AutocompleteItem
                  key={r.id}
                  value={r.id}
                  onSelect={() => {
                    onAddSeed(r.id);
                    setQ("");
                    onHighlightChange("");
                  }}
                >
                  <meta.Icon size={12} className={meta.textClass} />
                  <span className="flex-1 truncate">{r.displayName}</span>
                  <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    {meta.label}
                  </span>
                </AutocompleteItem>
              );
            })}
          </AutocompleteContent>
        </Autocomplete>

        <Segmented
          icon={Tag}
          label="Labels"
          value={labelsMode}
          options={LABEL_MODES}
          onChange={onLabelsModeChange}
        />

        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className={cn(CTRL, "gap-1.5 border-border bg-muted/40 text-xs")}
            >
              <SlidersHorizontal size={13} />
              Filters
              {activeFilterCount > 0 && (
                <span className="rounded-full bg-primary/15 px-1.5 text-[11px] font-bold text-primary">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            className="w-80 space-y-4 border-border bg-popover"
          >
            <FilterBlock label="Direction">
              <div className="flex overflow-hidden rounded-md border border-border">
                {DIRECTIONS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() =>
                      onFiltersChange({ ...filters, direction: d.value })
                    }
                    className={cn(
                      "flex-1 px-2 py-1.5 text-xs font-medium transition-colors",
                      filters.direction === d.value
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </FilterBlock>

            <FilterBlock label="Node types">
              <div className="flex flex-wrap gap-1.5">
                {GRAPH_NODE_TYPES.map((t) => {
                  const meta = GRAPH_NODE_TYPE_META[t];
                  const active = filters.entityTypes.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() =>
                        onFiltersChange({
                          ...filters,
                          entityTypes: toggle<GraphNodeType>(filters.entityTypes, t),
                        })
                      }
                      className={cn(
                        "flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
                        active
                          ? cn(meta.bgClass, meta.textClass, meta.borderClass)
                          : "border-border bg-muted/30 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <meta.Icon size={11} />
                      {meta.label}
                    </button>
                  );
                })}
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                None selected = all shown.
              </p>
            </FilterBlock>

            <FilterBlock label="Relationship types">
              <div className="flex flex-wrap gap-1.5">
                {RELATIONSHIP_TYPES.map((t) => {
                  const active = filters.relationshipTypes.includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() =>
                        onFiltersChange({
                          ...filters,
                          relationshipTypes: toggle<RelationshipType>(
                            filters.relationshipTypes,
                            t
                          ),
                        })
                      }
                      className={cn(
                        "rounded-md border px-2 py-1 text-[11px] font-medium transition-colors",
                        active
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border bg-muted/30 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {t.replace(/_/g, " ")}
                    </button>
                  );
                })}
              </div>
            </FilterBlock>

            <FilterBlock
              label={`Min edge weight: ${minWeightDraft === 0 ? "off" : `≥ ${minWeightDraft}`}`}
              hint="Hide thin edges. Weight is the interaction count on an edge (e.g. messages exchanged); most typed relationships have weight 1. Applied when you release the slider."
            >
              <Slider
                value={[minWeightDraft]}
                onValueChange={([v]) => setMinWeightDraft(v)}
                onValueCommit={([v]) =>
                  onFiltersChange({ ...filters, minWeight: v })
                }
                min={0}
                max={50}
                step={1}
              />
            </FilterBlock>

            <FilterBlock
              label={`Label density: ${labelDensity.toFixed(1)}`}
              hint="How many node labels the canvas shows at once. Lower = only the most prominent nodes are labelled (less clutter); higher = more labels, more overlap."
            >
              <Slider
                value={[labelDensity]}
                onValueChange={([v]) => onLabelDensityChange(v)}
                min={0.1}
                max={3}
                step={0.1}
              />
            </FilterBlock>
          </PopoverContent>
        </Popover>

        {hiddenCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onUnhideAll}
            className={cn(
              CTRL,
              "gap-1.5 text-xs text-muted-foreground hover:text-primary"
            )}
          >
            <Eye size={13} />
            Show {hiddenCount} hidden
          </Button>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className={cn(
            CTRL,
            "gap-1.5 text-xs text-muted-foreground hover:text-destructive"
          )}
        >
          <RotateCcw size={13} />
          Reset
        </Button>

        <span className="ml-auto flex items-center gap-1.5 pr-1 font-mono text-[11px] text-muted-foreground">
          {isLoading && (
            <span className="flex items-center gap-1 text-primary">
              <Loader2 size={11} className="animate-spin" />
              loading
            </span>
          )}
          {visibleNodeCount === nodeCount
            ? `${nodeCount} nodes`
            : `${visibleNodeCount} / ${nodeCount} nodes`}{" "}
          · {edgeCount} edges
        </span>
      </div>

      <TooltipProvider delayDuration={150}>
        <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-2">
          <Segmented
            icon={RotateCw}
            label="Layout"
            hint="How nodes are positioned. Force runs a physics simulation so connected nodes pull together; Circular, Cluster pack and Scatter are fixed arrangements."
            value={layout}
            options={LAYOUT_KINDS.map((k) => ({
              value: k,
              label: LAYOUT_LABELS[k],
            }))}
            onChange={onLayoutChange}
          />
          <MiniButton
            icon={RotateCw}
            onClick={onRelayout}
            hint="Recompute the current layout from scratch. Discards any nodes you dragged."
          >
            Re-run
          </MiniButton>
          <MiniButton
            icon={Play}
            onClick={onToggleLiveLayout}
            active={liveLayout}
            hint="Keep the force simulation running so the graph settles continuously — you can drag nodes while it moves and they stay pinned where you drop them."
          >
            {liveLayout ? "Live · on" : "Live"}
          </MiniButton>

          <Segmented
            label="Colour"
            hint="Type: colour each node by its kind (person, organization, location, selector). Community: colour by an automatically detected cluster of densely-connected nodes."
            value={colorMode}
            options={[
              { value: "type", label: "Type" },
              {
                value: "community",
                label: communityCount
                  ? `Community · ${communityCount}`
                  : "Community",
              },
            ]}
            onChange={onColorModeChange}
          />
          <Segmented
            label="Size"
            hint="Connections: bigger node = more edges. Influence: bigger node = higher PageRank, i.e. connected to other well-connected nodes."
            value={sizeMode}
            options={[
              { value: "degree", label: "Connections" },
              { value: "importance", label: "Influence" },
            ]}
            onChange={onSizeModeChange}
          />

          <MiniButton
            icon={Route}
            onClick={onTogglePathMode}
            active={pathMode}
            hint="Click two nodes to highlight the shortest chain of relationships between them."
          >
            {pathMode
              ? pathAnchorCount === 0
                ? "Path · pick 2"
                : pathAnchorCount === 1
                  ? "Path · pick 1 more"
                  : "Path · on"
              : "Find path"}
          </MiniButton>

          <MiniButton
            icon={Download}
            onClick={onExportPng}
            className="ml-auto"
            hint="Download the current canvas as a PNG image."
          >
            PNG
          </MiniButton>
        </div>
      </TooltipProvider>
    </div>
  );
}

function InfoHint({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          tabIndex={-1}
          aria-label="What is this?"
          className="text-muted-foreground/60 transition-colors hover:text-foreground"
          onClick={(e) => e.preventDefault()}
        >
          <Info size={11} />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-64 text-xs leading-relaxed">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function Segmented<T extends string>({
  icon: Icon,
  label,
  hint,
  value,
  options,
  onChange,
}: {
  icon?: typeof Tag;
  label: string;
  hint?: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div
      className={cn(
        "flex items-stretch overflow-hidden rounded-md border border-border bg-muted/40",
        CTRL
      )}
    >
      <span className="flex items-center gap-1 border-r border-border px-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        {Icon && <Icon size={11} />}
        {label}
        {hint && <InfoHint text={hint} />}
      </span>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cn(
            "flex items-center px-2.5 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function MiniButton({
  icon: Icon,
  onClick,
  active,
  hint,
  className,
  children,
}: {
  icon: typeof Tag;
  onClick: () => void;
  active?: boolean;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const btn = (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
        CTRL,
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground",
        className
      )}
    >
      <Icon size={12} />
      {children}
    </button>
  );
  if (!hint) return btn;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{btn}</TooltipTrigger>
      <TooltipContent className="max-w-64 text-xs leading-relaxed">
        {hint}
      </TooltipContent>
    </Tooltip>
  );
}

function FilterBlock({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
        {hint && (
          <TooltipProvider delayDuration={150}>
            <InfoHint text={hint} />
          </TooltipProvider>
        )}
      </span>
      {children}
    </div>
  );
}

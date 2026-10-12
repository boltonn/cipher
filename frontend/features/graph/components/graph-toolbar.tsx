"use client";

import { DatePicker } from "@/components/date-picker";
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
import { GRAPH_NODE_TYPE_META } from "@/features/entities/components/entity-type-meta";
import { EntityPicker } from "@/features/entities/components/entity-picker";
import {
  GRAPH_NODE_TYPES,
  RELATIONSHIP_TYPES,
  type GraphNodeType,
  type RelationshipType,
  type TraversalDirection,
} from "@/features/entities/types";
import type { LabelsMode } from "@/features/graph/components/network-canvas";
import {
  EMPTY_GRAPH_FILTERS,
  type ColorMode,
  type GraphFilters,
  type SizeMode,
} from "@/features/graph/hooks/use-graph-explore";
import {
  LAYOUT_KINDS,
  LAYOUT_LABELS,
  type LayoutKind,
} from "@/features/graph/lib/graph-layouts";
import { useDebounce } from "@/hooks/use-debounce";
import { cn, humanize } from "@/lib/utils";
import {
  CalendarRange,
  Download,
  Eye,
  Info,
  Loader2,
  Play,
  RotateCcw,
  RotateCw,
  Route,
  SlidersHorizontal,
  Sparkles,
  Tag,
  X,
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

interface GraphToolbarProps {
  datasetIds: string[];
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
  timeBarOpen: boolean;
  onToggleTimeBar: () => void;
  onAddSeed: (id: string) => void;
  seeds: { id: string; label: string }[];
  onRemoveSeed: (id: string) => void;
  onSelectSeed: (id: string) => void;
  onHighlightChange: (q: string) => void;
  onReset: () => void;
  hiddenCount: number;
  onUnhideAll: () => void;
  visibleNodeCount: number;
  nodeCount: number;
  edgeCount: number;
  visibleEdgeCount: number;
  truncatedCount: number;
  isLoading: boolean;
}

export function GraphToolbar({
  datasetIds,
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
  timeBarOpen,
  onToggleTimeBar,
  onAddSeed,
  seeds,
  onRemoveSeed,
  onSelectSeed,
  onHighlightChange,
  onReset,
  hiddenCount,
  onUnhideAll,
  visibleNodeCount,
  nodeCount,
  edgeCount,
  visibleEdgeCount,
  truncatedCount,
  isLoading,
}: GraphToolbarProps) {
  const [q, setQ] = useState("");
  // Only set while the slider is held, so an outside reset shows through.
  const [minWeightDrag, setMinWeightDrag] = useState<number | null>(null);
  const minWeightDraft = minWeightDrag ?? filters.minWeight;
  const debouncedQ = useDebounce(q, 350);

  // Canvas node-highlight follows the debounced query, not every keystroke.
  useEffect(() => {
    onHighlightChange(debouncedQ);
  }, [debouncedQ, onHighlightChange]);

  const activeFilterCount =
    filters.entityTypes.length +
    filters.relationshipTypes.length +
    (filters.minWeight > 0 ? 1 : 0) +
    (filters.direction !== "both" ? 1 : 0) +
    (filters.dateFrom || filters.dateTo ? 1 : 0);

  const toggle = <T,>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-muted/30 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <EntityPicker
          className={cn(CTRL, "w-72 rounded-md")}
          datasetIds={datasetIds}
          disabled={datasetIds.length === 0}
          placeholder={datasetIds.length > 0 ? "Add / find an entity…" : "Pick datasets above first"}
          onSelect={(entityId) => onAddSeed(entityId)}
          onQueryChange={setQ}
        />

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
                      {humanize(t)}
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
                onValueChange={([v]) => setMinWeightDrag(v)}
                onValueCommit={([v]) => {
                  setMinWeightDrag(null);
                  onFiltersChange({ ...filters, minWeight: v });
                }}
                min={0}
                max={50}
                step={1}
              />
            </FilterBlock>

            <FilterBlock
              label="Active between"
              hint="Keep dated relationships (emails, events) that were active inside this window. Undated ones always stay. The timeline button gives the same filter as a draggable chart."
            >
              <div className="grid grid-cols-2 gap-2">
                <DatePicker
                  className="h-8"
                  placeholder="From"
                  value={filters.dateFrom}
                  onChange={(dateFrom) => onFiltersChange({ ...filters, dateFrom })}
                />
                <DatePicker
                  className="h-8"
                  placeholder="To"
                  value={filters.dateTo}
                  onChange={(iso) =>
                    onFiltersChange({
                      ...filters,
                      // the picked day is inclusive
                      dateTo: iso && new Date(Date.parse(iso) + 86_399_999).toISOString(),
                    })
                  }
                />
              </div>
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

            {activeFilterCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onFiltersChange(EMPTY_GRAPH_FILTERS)}
                className="h-7 w-full gap-1.5 text-xs text-muted-foreground"
              >
                <X size={12} />
                Clear filters
              </Button>
            )}
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
          Clear graph
        </Button>

        <span className="ml-auto flex items-center gap-1.5 pr-1 font-mono text-[11px] text-muted-foreground">
          {isLoading && (
            <span className="flex items-center gap-1 text-primary">
              <Loader2 size={11} className="animate-spin" />
              loading
            </span>
          )}
          {truncatedCount > 0 && (
            <span title="Some nodes have more connections than are drawn; only their strongest are shown. Select one to see how many.">
              {truncatedCount} truncated ·
            </span>
          )}
          {visibleNodeCount === nodeCount
            ? `${nodeCount} nodes`
            : `${visibleNodeCount} / ${nodeCount} nodes`}{" "}
          ·{" "}
          {visibleEdgeCount === edgeCount
            ? `${edgeCount} edges`
            : `${visibleEdgeCount} / ${edgeCount} edges`}
        </span>
      </div>

      {seeds.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-2">
          <span className="flex items-center gap-1 px-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            <Sparkles size={11} />
            Seeds
          </span>
          {seeds.map((seed) => (
            <span
              key={seed.id}
              className="flex h-7 items-center overflow-hidden rounded-md border border-border bg-muted/40 text-xs"
            >
              <button
                type="button"
                onClick={() => onSelectSeed(seed.id)}
                className="max-w-48 truncate px-2 text-foreground hover:text-primary"
              >
                {seed.label}
              </button>
              <button
                type="button"
                aria-label={`Remove seed ${seed.label}`}
                onClick={() => onRemoveSeed(seed.id)}
                className="flex h-full items-center border-l border-border px-1.5 text-muted-foreground hover:text-destructive"
              >
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}

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
            icon={CalendarRange}
            onClick={onToggleTimeBar}
            active={timeBarOpen}
            hint="Show a timeline of when relationships were active. Drag across it to keep only what was active in that window."
          >
            {filters.dateFrom || filters.dateTo ? "Timeline · on" : "Timeline"}
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

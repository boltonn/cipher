"use client";

import type {
  OrganizationTree,
  OrganizationTreeNode,
} from "@/features/organizations/types";
import { cn } from "@/lib/utils";
import { BadgeCheck, ChevronDown, ChevronRight, Users } from "lucide-react";
import { useState } from "react";

/** Above this many units, start with everything below the second level folded. */
const FOLD_ABOVE = 30;

/**
 * Connectors drawn by each child: its half of the bar over the siblings plus a drop line
 * (`after:` carries the drop). End children round the bar's corner; an only child gets no bar.
 */
const BRANCH = cn(
  "relative flex flex-col items-center px-1.5 pt-5 only:pt-0",
  "before:absolute before:top-0 before:right-1/2 before:h-5 before:w-1/2 before:border-t before:border-border",
  "after:absolute after:top-0 after:left-1/2 after:h-5 after:w-1/2 after:border-t after:border-l after:border-border",
  "first:before:border-0 first:after:rounded-tl-md last:after:border-0 last:before:border-r last:before:rounded-tr-md",
  "only:before:hidden only:after:hidden"
);
/** A row of sub-units, with the line dropping into it from the parent card. */
const CHILD_ROW =
  "relative flex justify-center pt-5 before:absolute before:top-0 before:left-1/2 before:h-5 before:border-l before:border-border";

interface OrgIndex {
  byId: Map<string, OrganizationTreeNode>;
  children: Map<string, OrganizationTreeNode[]>;
  /** Members on the unit plus every unit below it (an edge count, so a person on two units counts twice). */
  subtreeMembers: Map<string, number>;
  depth: Map<string, number>;
}

export function indexTree(tree: OrganizationTree): OrgIndex {
  const byId = new Map(tree.nodes.map((n) => [n.entity.id, n]));
  const children = new Map<string, OrganizationTreeNode[]>();
  for (const node of tree.nodes) {
    if (!node.parentId) continue;
    children.set(node.parentId, [...(children.get(node.parentId) ?? []), node]);
  }
  const subtreeMembers = new Map<string, number>();
  const depth = new Map<string, number>();
  const walk = (id: string, level: number): number => {
    depth.set(id, level);
    const total = (children.get(id) ?? []).reduce(
      (sum, child) => sum + walk(child.entity.id, level + 1),
      byId.get(id)?.memberCount ?? 0
    );
    subtreeMembers.set(id, total);
    return total;
  };
  walk(tree.rootId, 0);
  return { byId, children, subtreeMembers, depth };
}

/** Root-first chain from the top of the tree down to `id`. */
export function pathTo(index: OrgIndex, id: string): OrganizationTreeNode[] {
  const path: OrganizationTreeNode[] = [];
  for (
    let node = index.byId.get(id);
    node;
    node = node.parentId ? index.byId.get(node.parentId) : undefined
  ) {
    path.unshift(node);
  }
  return path;
}

/**
 * Top-down org chart: every unit is a clickable card, connected to its `partOf` parent.
 * Selecting a unit is the parent's state -- it drives the people table underneath.
 */
export function OrgChart({
  tree,
  index,
  selectedId,
  onSelect,
}: {
  tree: OrganizationTree;
  index: OrgIndex;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const [folded, setFolded] = useState<Set<string>>(
    () =>
      new Set(
        tree.nodes.length > FOLD_ABOVE
          ? tree.nodes
              .filter((n) => index.depth.get(n.entity.id) === 2)
              .map((n) => n.entity.id)
          : []
      )
  );
  const onPath = new Set(pathTo(index, selectedId).map((n) => n.entity.id));

  const toggle = (id: string) =>
    setFolded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const renderNode = (node: OrganizationTreeNode) => {
    const id = node.entity.id;
    const kids = index.children.get(id) ?? [];
    // a folded ancestor of the selected unit would hide the selection, so it stays open
    const isForcedOpen = onPath.has(id) && id !== selectedId;
    const isFolded = folded.has(id) && !isForcedOpen;
    return (
      <li key={id} className={BRANCH}>
        <UnitCard
          node={node}
          totalMembers={index.subtreeMembers.get(id) ?? 0}
          childCount={isForcedOpen ? 0 : kids.length}
          isSelected={id === selectedId}
          isOnPath={onPath.has(id)}
          isFolded={isFolded}
          onSelect={() => onSelect(id)}
          onToggle={() => toggle(id)}
        />
        {kids.length > 0 && !isFolded && (
          <ul className={CHILD_ROW}>{kids.map(renderNode)}</ul>
        )}
      </li>
    );
  };

  const root = index.byId.get(tree.rootId);
  if (!root) return null;
  return (
    <div className="overflow-x-auto pb-2">
      <ul className="mx-auto flex w-max min-w-full justify-center">
        {renderNode(root)}
      </ul>
    </div>
  );
}

function UnitCard({
  node,
  totalMembers,
  childCount,
  isSelected,
  isOnPath,
  isFolded,
  onSelect,
  onToggle,
}: {
  node: OrganizationTreeNode;
  totalMembers: number;
  /** Sub-units the fold toggle hides; 0 hides the toggle. */
  childCount: number;
  isSelected: boolean;
  isOnPath: boolean;
  isFolded: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  const FoldIcon = isFolded ? ChevronRight : ChevronDown;
  return (
    <div
      className={cn(
        "group relative w-44 rounded-lg border bg-card text-left shadow-xs transition-colors",
        node.suggestionId &&
          "border-dashed border-annotation/70 bg-annotation/5",
        isSelected
          ? "border-primary ring-2 ring-primary/25"
          : isOnPath
            ? "border-primary/40"
            : "border-border hover:border-primary/50"
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={isSelected}
        className="block w-full rounded-lg px-3 pb-2 pt-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex items-center gap-1">
          <span
            className={cn(
              "truncate text-xs font-semibold",
              isSelected ? "text-primary" : "text-foreground"
            )}
            title={node.entity.displayName}
          >
            {node.entity.displayName}
          </span>
          {node.entity.isVerified && (
            <BadgeCheck size={12} className="shrink-0 text-primary" />
          )}
        </span>
        <span className="mt-0.5 block truncate text-[11px] capitalize text-muted-foreground">
          {node.suggestionId ? (
            <span className="normal-case text-annotation">
              suggested · review below
            </span>
          ) : (
            (node.category ?? "organization")
          )}
        </span>
        <span className="mt-1.5 flex items-center gap-1 text-[11px] tabular-nums text-muted-foreground">
          <Users size={11} className="shrink-0" />
          <span className="text-foreground">{node.memberCount}</span>
          {totalMembers !== node.memberCount && (
            <span>· {totalMembers} total</span>
          )}
          {node.connectedCount > 0 && (
            <span className="ml-auto">+{node.connectedCount} linked</span>
          )}
        </span>
      </button>
      {childCount > 0 && (
        <button
          type="button"
          onClick={onToggle}
          aria-label={
            isFolded ? `Show ${childCount} sub-units` : "Hide sub-units"
          }
          className="absolute -bottom-2.5 left-1/2 z-10 flex h-5 -translate-x-1/2 items-center gap-0.5 rounded-full border border-border bg-background px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <FoldIcon size={11} />
          {isFolded && childCount}
        </button>
      )}
    </div>
  );
}

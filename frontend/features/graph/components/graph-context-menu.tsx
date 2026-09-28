"use client";

import {
  EyeOff,
  Focus,
  Minimize2,
  Route,
  ScanSearch,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface ContextTarget {
  id: string;
  clientX: number;
  clientY: number;
}

interface GraphContextMenuProps {
  target: ContextTarget;
  isSeed: boolean;
  isExpanded: boolean;
  pathMode: boolean;
  onClose: () => void;
  onInspect: (id: string) => void;
  onExpand: (id: string) => void;
  onCollapse: (id: string) => void;
  onAddSeed: (id: string) => void;
  onIsolate: (id: string) => void;
  onHide: (id: string) => void;
  onPathAnchor: (id: string) => void;
}

/** Right-click actions for a node. Positioned at the pointer; a transparent
 * backdrop closes it on any outside interaction. */
export function GraphContextMenu({
  target,
  isSeed,
  isExpanded,
  pathMode,
  onClose,
  onInspect,
  onExpand,
  onCollapse,
  onAddSeed,
  onIsolate,
  onHide,
  onPathAnchor,
}: GraphContextMenuProps) {
  const { id } = target;
  const run = (fn: () => void) => () => {
    fn();
    onClose();
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          onClose();
        }}
        onWheel={onClose}
      />
      <div
        role="menu"
        className="fixed z-50 min-w-44 overflow-hidden rounded-lg border border-border bg-popover p-1 shadow-xl"
        style={{
          left: Math.min(target.clientX, window.innerWidth - 200),
          top: Math.min(target.clientY, window.innerHeight - 260),
        }}
      >
        <Item icon={ScanSearch} onClick={run(() => onInspect(id))}>
          Inspect
        </Item>
        {isExpanded ? (
          <Item icon={Minimize2} onClick={run(() => onCollapse(id))}>
            Collapse neighbours
          </Item>
        ) : (
          <Item icon={Focus} onClick={run(() => onExpand(id))}>
            Expand neighbours
          </Item>
        )}
        {!isSeed && (
          <Item icon={Sparkles} onClick={run(() => onAddSeed(id))}>
            Pin as seed
          </Item>
        )}
        <Item icon={Focus} onClick={run(() => onIsolate(id))}>
          Isolate
        </Item>
        <Item icon={EyeOff} onClick={run(() => onHide(id))}>
          Hide from view
        </Item>
        {pathMode && (
          <Item icon={Route} onClick={run(() => onPathAnchor(id))}>
            Use as path endpoint
          </Item>
        )}
      </div>
    </>
  );
}

function Item({
  icon: Icon,
  onClick,
  children,
}: {
  icon: LucideIcon;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <Icon size={13} className="shrink-0" />
      {children}
    </button>
  );
}


import type { NodeHoverDrawingFunction } from "sigma/rendering";
import type { Settings } from "sigma/settings";
import type { NodeDisplayData, PartialButFor } from "sigma/types";

/** Resolve a CSS custom property to a concrete rgb() string the canvas can use. */
export function resolveColor(varName: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const probe = document.createElement("span");
  probe.style.cssText = `color:var(${varName});position:absolute;visibility:hidden`;
  document.body.appendChild(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value || fallback;
}

/**
 * `fg` composited over `bg` at `alpha`, as an opaque rgb() string. Sigma's WebGL
 * programs don't premultiply alpha, so a translucent token (e.g. `--border`)
 * paints near-white on a dark canvas; flatten it first.
 */
export function blendColor(fg: string, bg: string, alpha: number): string {
  if (typeof document === "undefined") return fg;
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return fg;
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 1, 1);
  ctx.globalAlpha = alpha;
  ctx.fillStyle = fg;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

export interface ChipColors {
  text: string;
  chip: string;
  border: string;
}

function drawChipLabel(
  context: CanvasRenderingContext2D,
  data: PartialButFor<NodeDisplayData, "x" | "y" | "size" | "label" | "color">,
  settings: Settings,
  colors: ChipColors,
  { ring }: { ring: boolean }
) {
  const label = typeof data.label === "string" ? data.label : "";

  if (ring) {
    context.beginPath();
    context.arc(data.x, data.y, data.size + 2, 0, Math.PI * 2);
    context.strokeStyle = (data as { ringColor?: string }).ringColor ?? data.color;
    context.lineWidth = 2;
    context.stroke();
  }

  if (!label) return;

  const size = settings.labelSize;
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
  const padX = 6;
  const padY = 4;
  const textWidth = context.measureText(label).width;
  const boxH = size + padY * 2;
  const boxX = data.x + data.size + 4;
  const boxY = data.y - boxH / 2;
  const boxW = textWidth + padX * 2;

  context.beginPath();
  context.fillStyle = colors.chip;
  context.strokeStyle = colors.border;
  context.lineWidth = 1;
  if (context.roundRect) context.roundRect(boxX, boxY, boxW, boxH, 5);
  else context.rect(boxX, boxY, boxW, boxH);
  context.fill();
  context.stroke();

  context.fillStyle = colors.text;
  context.textBaseline = "middle";
  context.fillText(label, boxX + padX, data.y + 1);
}

/**
 * Themed node label: a popover-coloured chip behind the text so it stays
 * readable on either theme (sigma's built-in label draws plain text with no
 * backing, which vanishes against the canvas and other nodes).
 */
export function makeLabelRenderer(colors: ChipColors) {
  return ((context, data, settings) => {
    drawChipLabel(context, data, settings, colors, { ring: false });
  }) as NodeHoverDrawingFunction;
}

/**
 * Themed hover: the same chip, plus a ring on the node. Replaces sigma's
 * built-in hover, which paints a hard-coded white box that's unreadable in
 * dark mode.
 */
export function makeHoverRenderer(colors: ChipColors): NodeHoverDrawingFunction {
  return (context, data, settings) => {
    drawChipLabel(context, data, settings, colors, { ring: true });
  };
}

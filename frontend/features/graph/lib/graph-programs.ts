import { EdgeCurvedArrowProgram } from "@sigma/edge-curve";
import { createNodeImageProgram } from "@sigma/node-image";
import { EdgeArrowProgram, NodeCircleProgram } from "sigma/rendering";

/**
 * WebGL programs for the network canvas. The node-image program's texture atlas
 * is bound to the class (not the sigma instance), so it is rebuilt per canvas
 * mount via {@link makeGraphPrograms} to keep the atlas fresh across theme
 * remounts. Edges read `curvature` off each edge (set in `buildNetwork`) and
 * render straight or curved by `type`.
 */
export function makeGraphPrograms() {
  const entity = createNodeImageProgram({
    drawingMode: "background",
    keepWithinCircle: true,
    objectFit: "contain",
    padding: 0,
    size: { mode: "force", value: 128 },
    // default 500ms: every rebuild (expand, filter) showed bare circles for half a second
    debounceTimeout: 40,
  });

  return {
    nodeProgramClasses: { entity, circle: NodeCircleProgram },
    edgeProgramClasses: {
      straight: EdgeArrowProgram,
      curved: EdgeCurvedArrowProgram,
    },
  };
}

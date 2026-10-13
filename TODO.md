# Possible next steps

Nothing here is promised. Roughly in the order of how much it would help.

## LODs

- **Bridge to an outside LOD tool.** The trick that works from Blender: every selection becomes a
  bone, the mesh goes out as FBX with a skin, the tool reduces it keeping the skin weights, the
  result comes back and the weights become selections again. Then: skeletal weights normalised
  (three bones at most, sum 1), texture and rvmat paths put back by material name.
- **Shadow LOD from a LOD**: copy, triangulate, all edges sharp, no textures, pulled a little inward
  along the normals so that it never sticks out of the model.
- **View / Fire Geometry from Geometry**, with the usual named properties.
- **Collision from the model**: keep the faces of chosen materials, drop small parts, cut above a height.

## Checks

- **Check the model before export**: bones and sections of `model.cfg` exist in the LODs, axes of
  the animations exist in Memory, Geometry has mass and components, textures and `.rvmat` files are
  there, how many sections (texture x material) every LOD has, the same selections in all
  resolution LODs.
- **Check a folder of models** from the command line: LODs, sections, shadow LOD, components of
  Geometry. For judging third-party packs before they go into a mission.

## Model work

- **Proxies**: place one by picking a p3d (triangle of the right shape, selection name, next free
  number), show the proxied model as a see-through stand-in, renumber.
- **Animations of `model.cfg` in the scene**: axes from Memory, rotation and translation keys on the
  bone objects. The export must always write the pose of frame 0 first.
- **Skin to weights** and back: the weights of a Skin modifier as weighted selections.
- **Selections**: union, difference, intersection; a mirrored copy by name pattern (`kolL1` to
  `kolP1`); redo next to the tab's own undo.
- **Hit points**: follow the inheritance of `radius` in a config; spheres that follow moved points.
- **Name sets for memory points**, and a set made from the bones and sections of a `model.cfg`.

## Materials and textures

- **Read `.rvmat` on import**: normal and specular maps from its stages in the viewport; Multimat.
- **Fire Geometry materials**: pick the penetration material of the game for the chosen faces.
- **Write `.paa`** without ImageToPAA.

## Tools around

- Open the model in Buldozer; build the addon and show the output in the log.
- `#include` and simple macros in `model.cfg`.
- Reload the plugin without restarting 3ds Max.

## Keeping it alive

- **3ds Max 2025 and later**: Qt 6 instead of Qt 5, and no C# compiler to build the fast helper with.
- Unit tests on every commit, a release archive with a version number.
- Screenshots in the documentation.

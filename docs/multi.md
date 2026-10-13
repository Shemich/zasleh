---
title: Multi
nav_order: 10
---

# Multi tab

For buildings made of several models (multi-structure): one scene, one p3d per part.

1. Select the objects of a part and press **Add selected**. Give the part its class name and mass with **Set**.
2. **Build points** puts a memory point `pos_<name>` at the centre of every part: where the game
   attaches it.
3. **Verify** checks that every part has its point and warns about parts the game would re-centre.
4. **Export parts...** writes a p3d per part, each moved to the origin, with the options of the Model tab.
5. **Config line** copies `multiStructureParts[]` for your config to the clipboard.

**Centre** moves the picked part to the origin, as it is exported; **Restore** moves it back to its
memory point. *Set autocenter = 0* and *Include Geometry LOD* apply to the exported parts.

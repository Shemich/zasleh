---
title: Config
nav_order: 8
---

# Config tab

`model.cfg`: the skeleton, the sections and the animations of one model.

## Skeleton

A tree of bones. Drag a bone onto another to make it its child; double click to rename.

| Button | What it does |
|---|---|
| From selections | Adds the selections of the scene that are not bones yet. |
| From links | Takes bones and parents from the linked objects of the scene. |
| To scene | The selection of every bone becomes an object of its own, linked to the object of its parent bone. The export joins the objects again. |
| Add, Remove | A new bone under the picked one; removing a bone moves its children up. |

## Sections

One per line. A section is a selection the game may retexture or hide: `camo1`, `zasleh`, `clan`...

## Animations

A row per animation: name, type, source, selection, axis, the range of the source and the two values
it moves between (angles for rotations, offsets for translations, the hide value for `hide`).
The cells for source, selection and axis offer what fits: known sources, the bones, the memory points.

## Files

**Load...** reads a `model.cfg`. If the file has several models, you choose one. What the model takes
from other classes is put into it: bones from `skeletonInherit`, sections from `sectionsInherit`,
animations from the classes it is derived from.

**Save...** writes a file that needs no other class. **Preview** shows it in the log first.

`#include` and macros are not expanded: a file that relies on them has to be preprocessed first.

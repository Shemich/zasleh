---
title: How a p3d is kept in the scene
nav_order: 10
---

# How a p3d is kept in the scene

| In the p3d | In 3ds Max |
|---|---|
| LOD | a layer named after the LOD |
| faces | Editable Poly objects on the layer |
| points without faces | point helpers; the helper's name is its selection |
| UV set *n* | map channel *n + 1* |
| texture and rvmat of a face | material ID > sub-material with *Arma* attributes |
| sharp edges | smoothing groups |
| named selections, weights, mass, flags | map channels 10 to 99 |
| named properties, order of selections | data of the layer |

Coordinates: p3d `(x, y, z)` is 3ds Max `(x, z, y)`. UV: `v` becomes `1 - v`.

## Why map channels

Selections have to survive modelling. In 3ds Max:

- a **map channel** lives through cut, slice, extrude, bevel, tessellate, attach, detach, weld,
  Symmetry and conversion to mesh and back; new vertices get interpolated values;
- a **vertex data channel** loses its values on tessellate, meshsmooth and chamfer;
- a **named selection set** breaks as soon as a vertex is deleted.

So every selection is numbers in a map channel. You can look at them (*Channel Info*), but do not
edit or clear channels 10 to 99 by hand.

Because the values are per face corner, a selection knows both its vertices and its faces, as
it does in a p3d. Vertices that modelling created between two selections belong to neither: **Check**
in the Selections tab finds them.

## What an export does

It reads every object of a layer, puts the points back in the order of the file they came from
(new ones go last), joins objects that were split off, works the normals out the way Object Builder
does when it saves, and writes the tags in Object Builder's order.

## Scenes with one object per selection

An object that was not imported and has no selections of this kind counts as a selection named
after itself, so scenes laid out as "one object per selection" still export.

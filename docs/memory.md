---
title: Memory
nav_order: 7
---

# Memory tab

Memory points are point helpers on a point LOD layer (`Memory`, `Landcontact`, `Paths`...).
The name of a helper is the selection the point is in.

Choose the LOD at the top. The list shows its points; picking them in the list selects them in the scene.

| Button | What it does |
|---|---|
| At centre | One point in the middle of the picked vertices or the selected objects. |
| At verts | A point on every picked vertex. |
| Place... | Click in the viewport to place points; right click ends. |
| Rename | Gives the picked points the name typed above. Several names at once: `a, b`. |
| Make axis | Two picked points get the name typed above: an axis for `model.cfg`. |
| Delete | Deletes the picked points. |

**Size** sets the size of the markers. **Hide points**, **Hide geometry** and **X-ray** change what
the viewport shows, nothing in the model.

Points made here are named after the text in the name field, so the usual way is: type
`osaveze`, pick two vertices on the turret ring, **At verts**.

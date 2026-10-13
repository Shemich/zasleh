---
title: Hit points
nav_order: 8
---

# Hit points tab

The `HitPoints` LOD: clouds of points that tell the game where the engine, the ammunition or the
hull are, and how far each hit point reaches.

The table lists the selections of the LOD, the number of their points and their radius, if one is set.

## Point cloud

1. Model the volume as a closed object (a box is enough) and select it.
2. Set the distances between the points along X, Y and Z of the object.
3. Press **Fill object**.

The points land on the `HitPoints` layer as one object, named after the object you filled, and that
name is their selection. Type another name in the field above the distances to use it instead.

- An object put together from several closed pieces (boxes and cylinders attached into one engine)
  is filled piece by piece. Every piece gets a grid of its own, laid along its own sides, with the
  same room left at both ends. So a slanted block is filled along its slant.
- Pieces may overlap: the room two of them share is filled once.
- Several selected objects are filled into one selection.
- Points sit in the middle of the grid cells, never on the surface.
- If a piece has a hole, the grid lines running through it are skipped; the log says how many.
- The objects you filled are not changed and are not needed afterwards.

Untick **Each piece on its own grid** to get one grid for the whole object, along the object's axes.

The cloud is an ordinary Editable Poly made of points, so thousands of them are no problem, and the
[Selections](selections.md) tab works on it: pick some of its vertices and assign them to another selection.

## Radius

The game treats a hit point as a sphere, `radius` in its class of the config:

    class HitHull: HitHull
    {
        name = "int_ammo_hit";
        radius = 0.15;
    };

| Button | What it does |
|---|---|
| Set | Gives the radius to the picked selections. With none picked: to all points whose selections have no radius of their own. 0 takes a radius away. |
| From config... | Reads a `config.cpp`. Every class with both a `name` and a `radius` gives its radius to that selection. |
| Show | Draws a sphere of its radius around every hit point. |

The spheres are for the eye only and are not written to the p3d. They are drawn once: after moving
points, press **Show** again. A class that takes its radius from a parent class is not followed.

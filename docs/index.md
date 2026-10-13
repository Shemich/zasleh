---
title: Home
nav_order: 1
---

# Zasleh

Arma 3 tools for 3ds Max. Zasleh reads and writes editable `.p3d` models (MLOD) and lets you do in
3ds Max what you would otherwise go to Object Builder for: named selections and their weights,
memory points, mass, face textures and `.rvmat` paths, LOD properties, `model.cfg`.

*Zasleh* is the name BI's models give to the muzzle flash selection. Every Arma modder has typed it at least once.

## What you get

- **Import and export of p3d** that does not lose anything: a model imported and exported again has the
  same points, faces, normals, UV sets, selections, properties and mass.
- **Selections** that survive modelling. Cut, extrude, weld, attach, detach: the selections stay.
- **Name sets**: what a tank, a car or a house is usually cut into, ready to assign.
- **Textures and materials per selection**, and `.rvmat` files written for you.
- **`.paa` textures in the viewport.**
- **Hit points**: a cloud of points inside any closed object, and the reach of every hit point drawn as a sphere.
- **`model.cfg`**: skeleton, sections and animations in a table; an existing file is read with its inheritance.
- **Big models**: a 145 MB tank with 11 LODs imports in about 6 seconds and exports in about 7.

## Where to start

1. [Installation](installation.md)
2. [Quick start](quick-start.md)
3. The tabs: [Model](model.md), [Selections](selections.md), [Materials](materials.md),
   [Memory](memory.md), [Hit points](hitpoints.md), [Config](config.md), [Multi](multi.md); [Settings](settings.md)
4. [How a p3d is kept in the scene](scene.md) and the [limits](limits.md)

Tested with 3ds Max 2024.

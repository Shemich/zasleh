---
title: Quick start
nav_order: 3
---

# Quick start

## Open a model

1. **Settings** at the bottom of the panel: set *Tex root* to your project drive (usually `P:\`).
   Texture paths in a p3d are relative to it.
2. **Model** tab, **Import p3d...**, pick an editable p3d.

Every LOD of the model is now a layer named after the LOD: `1`, `2`, `Geometry`, `Memory`...
Double click a layer in the list to see that LOD alone.

## Look at its selections

Select the object of a LOD and open the **Selections** tab. The list shows its named selections.
Double click one to select its polygons; press **Show in colour** to see it painted on the mesh.

## Change something and write it back

1. Pick a few polygons, type a name, press **Assign**. That is a new selection.
2. **Model** tab, tick the layers you want in the file, **Export p3d...**

## Start from nothing

A scene does not have to come from a p3d.

1. Model something. Convert it to Editable Poly (**Model > To Editable Poly** does it for the selection).
2. Right click the layer list > **Add...** and choose a LOD name. Put your objects on that layer.
3. Right click the layer > **Properties...** for the named properties (`class = house`, `autocenter = 0`...).
4. In **Selections** choose a name set (tank, car, house...) to see what such a model usually needs.
5. Give the faces their textures: **Selections**, or ordinary 3ds Max materials (see [Materials](materials.md)).
6. Export.

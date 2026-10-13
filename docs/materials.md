---
title: Materials
nav_order: 6
---

# Materials tab

A p3d stores two paths per face: a texture and an `.rvmat`. In the scene they come from the
material of the face.

## Two kinds of material

**A material imported from a p3d** carries the two paths as they were in the file (rollout *Arma* in
the material editor). The export writes them back untouched. The picture in its colour slot is only
there for the viewport.

**An ordinary 3ds Max material** (Standard, Physical, inside a Multi/Sub-Object or not) gets its
paths worked out on export: the texture from the file in the colour slot, made relative to *Tex root*
(see [Settings](settings.md)) and given the `.paa` extension; the `.rvmat`, if you ask for one, next to it.

## The table

Every material the scene's geometry uses, and what it lacks.

| Column | Meaning |
|---|---|
| Colour map | The file in the colour slot. |
| N, S | Normal and specular map: `Y` in the material, `f` a file lying next to the colour map, `-` none. |
| Status | `OK`, `no nohq/smdi`, `no _co`, `file missing`, `outside root`, or `paths set` for a material with paths of its own. |

Double click a row to open the material in the material editor.

## Buttons

| Button | What it does |
|---|---|
| Find maps | Puts the `_nohq` and `_smdi` pictures lying next to the `_co` into the free slots of the material. |
| Write .rvmat | Writes an `.rvmat` next to the colour map, with the shader chosen beside the button. An existing file is replaced only after a question. |
| Set / Automatic | **Set** makes the picked materials write exactly the texture and rvmat typed in the two fields. **Automatic** goes back to working the paths out from the maps. |
| Replace in picked / in all | Replaces a piece of the texture paths, for a project that moved to another folder. |
| Select objects | Selects the objects that use the picked materials. |

The buttons work on the picked rows; **Find maps** and **Write .rvmat** take all rows when none is picked.

## Shaders of the generated .rvmat

| Preset | Shader | Stages |
|---|---|---|
| Super | `Super` | normal, detail, macro, ambient shadow, specular, fresnel, environment |
| NormalSpecular | `NormalMapSpecularDIMap` | normal, specular |
| Detail | `NormalMapDetailSpecularDIMap` | normal, detail, specular |
| Glass | `Glass` | none of the material's maps |

A normal or specular map that does not exist yet is still named in the file (`x_nohq.paa`,
`x_smdi.paa`), so you can make it later. Stages the material has nothing for get the plain values
the game's own files use.

## Textures per selection

To give a texture and an `.rvmat` to a part of a mesh without touching materials, use the two
fields in the [Selections](selections.md) tab.

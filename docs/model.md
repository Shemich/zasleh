---
title: Model
nav_order: 4
---

# Model tab

Import, export and everything about LODs.

## Import

**Import p3d...** reads an editable p3d (MLOD). Each LOD becomes a layer; faces become an Editable
Poly, points without faces become point helpers.

| Option | What it does |
|---|---|
| Show .paa textures in the viewport | 3ds Max cannot open `.paa`. With this on, a source picture lying next to the `.paa` is shown, or a preview is made from the `.paa` itself (kept in `<Tex root>\temp\atb_preview`). |
| Game data | The folder with your unpacked game data. Textures the project does not have (`a3\...`) are looked up there. |
| Proxies as separate objects | Every proxy triangle becomes its own object named after the proxy. |
| Split off | Selections whose faces become objects of their own, for example `wheel_*, otocvez`. `*` and `?` are allowed, commas between. A face goes with the first selection that has it. |
| Debinarizer | A program that turns a binarized (ODOL) p3d into an editable one, called as `program inFolder outFolder`. Binarized models are passed through it on import. |

Objects split off the LOD stay on its layer and keep all their selections. The export joins them
again: shared points become one point, faces go back to their place in the file.

## The LOD list

Layers that are LODs, with the LOD each one becomes. Ticked layers are exported.

- Double click: show only this LOD.
- Right click: **Show all**, **Add...**, **Rename...**, **Duplicate...**, **Properties...**, **Delete**.

**Properties...** edits the named properties of the LOD, a line each: `class = house`, `map = house`,
`autocenter = 0`, `lodnoshadow = 1`.

A layer is a LOD when its name is a LOD name: a number for a resolution LOD, or `Geometry`,
`Memory`, `Fire Geometry`, `View Geometry`, `Shadow Volume 0`, `Roadway` and so on.

## Export

**Export p3d...** writes the ticked layers.

| Option | What it does |
|---|---|
| Use .paa paths | Texture paths are written with the `.paa` extension, whatever the picture in 3ds Max is. |
| Generate .rvmat | Writes an `.rvmat` for every ordinary 3ds Max material and names it on the faces. A file that is already there is kept. The shader is chosen in the Materials tab. |
| Deploy textures to | Copies or converts the textures into a folder next to the p3d. Needs `ImageToPAA.exe`; `texconv.exe` for `.dds` sources. Files already there are kept. |
| Tex root | Texture paths are written relative to this folder. |

Polygons with more than four corners are written as triangles and quads; the scene is not changed.

## Preparing a mesh

**Reset XForm**, **Reset pivot**, **To Editable Poly**, **Clean mesh** work on the selected objects.

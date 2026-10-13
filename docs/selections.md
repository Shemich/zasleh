---
title: Selections
nav_order: 5
---

# Selections tab

Named selections of the selected Editable Poly: what Object Builder shows in its *Named Selections* window.

## The list

The selections the object has. `[weighted]` marks those with weights other than 1.

- Click: the name goes into the field below; texture and material of its faces are shown.
- Double click: select its vertices and polygons. Hold Ctrl to add to what is selected, Alt to subtract.
- Right click: **New**, **Delete**, **Delete (All LODs)**, **Rename**, **Rename (All LODs)**,
  **Redefine**, **Refresh**.

## Buttons

| Button | What it does |
|---|---|
| Assign | Puts the picked vertices or polygons into the selection named in the field. With nothing picked: the whole object. The weight field sets the weight. |
| Remove | Takes the picked vertices or polygons out of it. |
| Select | Same as a double click in the list. |
| Find components | Every separate piece of the mesh becomes `Component01`, `Component02`... |
| Check | Looks for vertices and polygons that fell out of their selections after modelling. |
| Ungrouped | Selects the vertices that are in no selection. |
| Show in colour | Paints the selection on the mesh: grey outside, blue to red by weight. |
| Undo | Takes back the last change made in this tab. Ctrl+Z does not see these changes. |

With several objects selected, the buttons work on all of them.

## Name sets

A name set is a short list of what a kind of model is usually cut into: a tank has `otocVez`,
`otocHlaven`, `koloL1`...; a house has `Door_1`, `Glass_1_hide`...

Choose a set in the box above the list. The selections the object does not have yet appear in grey
below its own, each with a word on what it is. Pick polygons and double click a grey line: they
become that selection.

The sets are text files, a line per selection:

    otocVez = turret, turns left and right
    koloL1 = left road wheel 1

Right click the list > **Edit this name set** opens the file, **Name sets folder** opens the folder.
To make your own set, copy a file there under another name.

## Texture and material of a selection

The two fields under the name show what the faces of the picked selection carry: the texture and the
`.rvmat`, written as the p3d has them (`myaddon\data\hull_co.paa`). Type other paths and press **Set**
to give them to these faces.

If the faces of a selection do not all have the same texture, the most used one is shown and the
rest is listed in the log.

## Mass

**Set** spreads the mass over the picked vertices (the whole object when nothing is picked);
**Get** tells the mass of the picked vertices. Mass is stored only in the Geometry LOD.

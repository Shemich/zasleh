---
title: Limits
nav_order: 11
---

# Limits

- **Editable p3d only.** Zasleh does not read binarized (ODOL) models itself; it can pass them
  through a debinarizer you have (Model tab). What binarization threw away does not come back.
- **Undo.** 3ds Max keeps no undo record for map channels, so Ctrl+Z does not undo what the
  Selections tab does. The tab has its own **Undo**; there is no redo.
- **Smoothing groups** are 32 bits per face. Where more than 32 separately smoothed surfaces meet in
  one point, the sharp edges around it cannot be kept exactly. The import tells you where.
- **Double-sided faces and three faces on one edge** cannot share vertices in an Editable Poly. Such
  points are imported as several vertices and become one point again on export.
- **Quads.** In rare non-manifold spots 3ds Max does not join two triangles back into a quad; the
  quad is then written as two triangles.
- **Editor state** of Object Builder (selected, locked and hidden items, keyframe animation) is not kept.
- **model.cfg** is read without a preprocessor.
- **Tested with 3ds Max 2024 only.** The fast import and export need the C# compiler of
  .NET Framework, which such a machine has; without it Zasleh works, only slower.

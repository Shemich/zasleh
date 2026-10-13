---
title: Settings
nav_order: 11
---

# Settings

The **Settings** button at the bottom of the panel. Folders and tools you tell Zasleh about once.

| Setting | What it is |
|---|---|
| Tex root | Your project drive, usually `P:\`. Texture paths in a p3d are relative to it. |
| Game data | The folder with your unpacked game data (the one that holds `a3\`). Textures the project does not have are looked up there, so imported models show the game's own textures. |
| Debinarizer | A program that turns a binarized (ODOL) p3d into an editable one, called as `program inFolder outFolder`. Binarized models are passed through it on import. |
| ImageToPAA | `ImageToPAA.exe` of Arma 3 Tools. Converts textures to `.paa` when they are deployed on export. |
| Texconv | `texconv.exe` of Microsoft DirectXTex. Needed only when deployed textures come from `.dds`. |

Everything is kept in `Zasleh.ini` in the `plugcfg` folder of your 3ds Max profile.

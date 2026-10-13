---
title: Installation
nav_order: 2
---

# Installation

## What you need

- 3ds Max 2024. Zasleh runs on the Python and Qt that come with 3ds Max, there is nothing else to install.
- For textures deployed on export (optional): `ImageToPAA.exe` from Arma 3 Tools, and `texconv.exe`
  from Microsoft DirectXTex if your source pictures are `.dds`.

## Steps

1. Download the repository (green **Code** button > *Download ZIP*, or `git clone`) and put the folder
   where you keep your tools. Do not put it inside the 3ds Max folder.
2. Run `install.bat`. If 3ds Max is under *Program Files* and the script says it could not link the
   folder, run it as administrator. For another version or place of 3ds Max:

       install.bat "C:\Program Files\Autodesk\3ds Max 2024"

3. Start 3ds Max. Open *Customize > Customize User Interface > Toolbars*, choose the category
   **Zasleh** and drag the action onto a toolbar.
4. Press the button. The panel docks on the left side.

`install.bat` does not copy the plugin. It makes `<3ds Max>\scripts\Zasleh` a link to the folder you
downloaded, so updating is replacing that folder (or `git pull`).

## By hand

Copy `scripts\Zasleh` into `<3ds Max>\scripts`, the files of `ui\icons` into `<3ds Max>\ui\icons`
and `ui\macroscripts\zasleh.mcr` into `<3ds Max>\ui\macroscripts`.

## Removing

Delete `<3ds Max>\scripts\Zasleh` (if it is a link, only the link goes), `zasleh_*.bmp` from
`ui\icons` and `zasleh.mcr` from `ui\macroscripts`. Settings are in `Zasleh.ini` in the `plugcfg`
folder of your 3ds Max profile.

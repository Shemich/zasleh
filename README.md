# Zasleh

**Arma 3 tools for 3ds Max**: import and export of `.p3d` models, named selections, memory points,
materials and `.rvmat`, `model.cfg`. What you used to open Object Builder for, done inside 3ds Max.

[Documentation](https://shemich.github.io/zasleh/) · [Русская версия](README.ru.md)

*Zasleh* is what BI's models call the muzzle flash selection.

## Features

- **p3d in, p3d out, nothing lost.** A model imported and exported again has the same points, faces,
  normals, UV sets, selections, properties and mass. Checked on 47 models, the Arma 3 Samples among them.
- **Selections that survive modelling.** Cut, extrude, weld, attach, detach: they stay. Weights,
  "find components", checks, an undo of their own.
- **Name sets.** What a tank, a car, a house is usually cut into, with a word on each selection.
  What your object still lacks is listed; a double click assigns the picked polygons.
- **Textures and materials.** Texture and `.rvmat` per selection, as in Object Builder. `.rvmat` files
  written for you (Super, NormalSpecular, Detail, Glass). `.paa` textures shown in the viewport.
- **LODs as layers**, with their named properties. Proxies, wheels or turrets as separate objects if you like.
- **model.cfg**: skeleton, sections, animations; existing files are read with their inheritance.
- **Fast.** A 145 MB tank with 11 LODs: about 6 seconds in, about 7 out.
- Binarized models through a debinarizer of your choice. Multi-structure buildings.

## Install

1. Download this repository and put the folder where you keep your tools.
2. Run `install.bat` (as administrator if it cannot write to the 3ds Max folder).
3. In 3ds Max: *Customize > Customize User Interface > Toolbars*, category **Zasleh**, drag the action
   onto a toolbar and press it.

Needs 3ds Max 2024 and nothing else. More in the [documentation](https://shemich.github.io/zasleh/installation.html).

## For developers

```
scripts/Zasleh/python/zasleh/formats  file formats, no 3ds Max needed: p3d, paa, rvmat, model.cfg
scripts/Zasleh/python/zasleh          the scene: import, export, selections, materials...
scripts/Zasleh/python/zasleh/ui       the Qt panel, a file per tab
scripts/Zasleh/python/tests           unit tests, and checks that run inside 3ds Max without its UI
docs/                                 the documentation site
```

    cd scripts\Zasleh\python
    python -m unittest discover -s tests -t .
    python -m zasleh.formats info model.p3d
    python -m zasleh.formats diff a.p3d b.p3d

## License

Copyright (C) 2026 Shemich. Zasleh is free software under the GNU General Public License v3.0:
you may use, change and share it, and what you build on it has to stay open too. See [LICENSE](LICENSE).

## Thanks

To Soul_Assassin, whose ArmA Toolbox showed years ago that this belongs inside 3ds Max.

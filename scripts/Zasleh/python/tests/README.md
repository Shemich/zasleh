# Tests

Core (no 3ds Max needed), from the `python` folder:

    python -m unittest discover -s tests -t .

Scene tests run inside 3ds Max without its UI. Each writes a JSON report; `"ok": true` means pass.

    $env:ZASLEH_OUT = "D:\temp\scene.json"
    $env:ZASLEH_TMP = "D:\temp"
    & "C:\Program Files\Autodesk\3ds Max 2024\3dsmaxbatch.exe" python\tests\headless\scene.py

| script | what | extra env |
|---|---|---|
| `scene.py` | export of a hand-built scene, options, mass, n-gons | `ZASLEH_TMP` |
| `groups.py` | vertex groups | `ZASLEH_SAMPLE` (a p3d, optional) |
| `panel.py` | the Qt panel, driven from script | `ZASLEH_TMP` |
| `preview.py` | .paa previews on import | `ZASLEH_TMP` |
| `bulk.py` | the C# helper vs the Python reference | `ZASLEH_SAMPLE` (optional) |
| `parts.py` | selections split off into objects, and the p3d that comes back | `ZASLEH_TMP`, `ZASLEH_SAMPLE` (optional) |
| `roundtrip.py` | p3d -> scene -> p3d on a list of files | `ZASLEH_FILES` (text file, one path per line); `ZASLEH_PARTS` (patterns to split off, optional) |

`ZASLEH_BULK=0` forces the slow MAXScript path.

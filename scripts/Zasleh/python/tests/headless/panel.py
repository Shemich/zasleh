"""The Qt panel: its widgets are driven from script"""
import json
import os
import shutil
import sys
import traceback

import pymxs

rt = pymxs.runtime
out = {"checks": {}}


def check(name, condition, detail=None):
    out["checks"][name] = bool(condition) if detail is None else [bool(condition), detail]


SETTINGS_BEFORE = {}        # put back whatever happens
try:
    sys.path.insert(0, os.path.join(str(rt.getDir(rt.Name("scripts"))), "Zasleh", "python"))
    from zasleh import formats
    from zasleh import settings as all_settings
    SETTINGS_BEFORE.update((key, all_settings.get(key)) for key in
                         ("texRoot", "gameRoot", "debinarizer", "imageToPaa", "texConv", "nameSet", "rvmatPreset"))
    from zasleh.formats import LOD, P3D, Face
    import zasleh.ui as ui
    from PySide2 import QtCore

    rt.resetMaxFile(rt.Name("noPrompt"))
    panel = ui.show()
    check("the panel opens with its tabs", panel.isVisible() and
          [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == ["Model", "Selections", "Memory", "Hit points", "Materials", "Config", "Multi"])
    check("opening it again gives the same panel", ui.show() is panel)

    # -- Selections
    tab = panel.selections
    panel.tabs.setCurrentWidget(tab)
    kept_set = tab.name_set.currentText()
    tab.name_set.setCurrentIndex(0)
    plane = rt.convertToPoly(rt.Plane(length=4, width=4, lengthsegs=4, widthsegs=4, name="hull"))
    rt.select(plane)
    ui.selection_changed()
    check("the selected object is shown", tab.object_label.text() == "Object: hull", tab.object_label.text())

    def listed():
        return [tab.list.item(i).text() for i in range(tab.list.count())]

    tab.name.setText("alpha")
    state = tab.do("assign")
    check("assign", state["status"] == "alpha: 16 polygons assigned" and listed() == ["alpha"] and
          tab.status.text() == state["status"], [state["status"], listed()])
    tab.do("undo")
    check("undo", tab.status.text() == "Undone: Assign" and listed() == [], [tab.status.text(), listed()])
    tab.do("assign")
    tab.list.setCurrentRow(0)
    tab.item_clicked(tab.list.item(0))
    check("a click puts the name into the field", tab.name.text() == "alpha" and tab.current() == "alpha")
    tab.colour.setChecked(True)
    check("show in colour", tab.colour.isChecked() and bool(plane.showVertexColors), tab.status.text())
    tab.colour.setChecked(False)
    check("colours off", not tab.colour.isChecked() and not bool(plane.showVertexColors))
    tab.name.setText("")
    tab.colour.setChecked(True)
    check("show in colour without a name: the button comes back up", not tab.colour.isChecked())

    answers = []
    tab.ask = lambda title, initial="": answers.pop(0)
    tab.confirm = lambda question: True
    rt.polyop.setFaceSelection(plane, rt.execute("#{1..4}"))
    answers.append("fresh")
    tab.menu("new")
    check("menu: New", tab.status.text() == "fresh: 16 polygons assigned" and listed() == ["alpha", "fresh"], [tab.status.text(), listed()])
    answers.append("fresh")
    tab.menu("new")
    check("menu: New refuses a name the object has", "already has a group" in tab.status.text(), tab.status.text())
    tab.list.setCurrentRow(1)
    answers.append("renamed")
    tab.menu("rename")
    check("menu: Rename", listed() == ["alpha", "renamed"] and tab.current() == "renamed", [tab.status.text(), listed()])
    answers.append("everywhere")
    tab.menu("rename_all")
    check("menu: Rename (All LODs)", listed() == ["alpha", "everywhere"], [tab.status.text(), listed()])
    tab.list.setCurrentRow(1)
    tab.menu("redefine")
    check("menu: Redefine", tab.status.text() == "everywhere: now the 16 picked polygons", tab.status.text())
    tab.list.setCurrentRow(1)
    tab.menu("delete")
    check("menu: Delete", listed() == ["alpha"], listed())
    tab.list.setCurrentRow(0)
    tab.menu("delete_all")
    check("menu: Delete (All LODs)", listed() == [], [tab.status.text(), listed()])
    tab.menu("refresh")
    check("menu: Refresh", listed() == [])
    tab.do("check")
    check("check writes to the log when there is something to say", tab.status.text().startswith("Checked: "), tab.status.text())
    tab.mass.setValue(80.0)
    tab.do("mass_set")
    tab.mass.setValue(0.0)
    tab.do("mass_get")
    check("mass: set, then get fills the field", abs(tab.mass.value() - 80.0) < 0.05, [tab.mass.value(), tab.status.text()])
    # texture and rvmat of a selection's faces: shown on a click, given with Set
    from zasleh import exporter as face_exporter, selections as face_selections
    from zasleh import groups as face_groups, materials as face_materials_module, importer as face_importer
    from zasleh import registry as face_reg
    registry = face_reg.Registry.load()
    face_groups.assign(plane, registry, "everywhere", 1.0, "faces", list(range(1, 17)))
    face_groups.assign(plane, registry, "strip", 1.0, "faces", [1, 2, 3, 4])
    registry.save()
    tab.menu("refresh")

    def pick_selection(name):
        tab.list.setCurrentRow(tab.names.index(name))
        tab.item_clicked(tab.list.currentItem())

    pick_selection("everywhere")
    check("faces: an object without materials shows empty fields", tab.texture.text() == "" and tab.rvmat.text() == "")
    tab.texture.setText("proj\\data\\hull_co.paa")
    tab.rvmat.setText("proj\\data\\hull.rvmat")
    status = tab.set_faces()
    check("faces: Set gives the texture and the rvmat to the faces of the selection",
          "16 face(s) now have proj\\data\\hull_co.paa and proj\\data\\hull.rvmat" in status and
          face_selections.face_materials("everywhere")["pairs"] == [("proj\\data\\hull_co.paa", "proj\\data\\hull.rvmat", 16)],
          [status, face_selections.face_materials("everywhere")])
    pick_selection("strip")
    check("faces: a click on a selection shows what its faces carry",
          tab.texture.text() == "proj\\data\\hull_co.paa" and tab.rvmat.text() == "proj\\data\\hull.rvmat")
    tab.texture.setText("proj\\data\\glass_ca.paa")
    tab.rvmat.setText("")
    tab.set_faces()
    pick_selection("everywhere")
    lookup = face_exporter.Textures()
    written = sorted({lookup(plane.material, int(rt.polyop.getFaceMatID(plane, f))) for f in range(1, 17)})
    check("faces: two textures on a selection - the most used is shown, the rest is said; the export writes both",
          tab.texture.text() == "proj\\data\\hull_co.paa" and "2 different" in tab.status.text() and
          face_selections.face_materials("everywhere")["pairs"] ==
          [("proj\\data\\hull_co.paa", "proj\\data\\hull.rvmat", 12), ("proj\\data\\glass_ca.paa", "", 4)] and
          written == [("proj\\data\\glass_ca.paa", ""), ("proj\\data\\hull_co.paa", "proj\\data\\hull.rvmat")],
          [tab.status.text(), face_selections.face_materials("everywhere"), written])
    pick_selection("strip")
    tab.texture.setText("proj\\data\\hull_co.paa")
    tab.rvmat.setText("proj\\data\\hull.rvmat")
    tab.set_faces()
    check("faces: a pair the object has already takes no new sub-material",
          int(plane.material.numsubs) == 3 and len(face_selections.face_materials("everywhere")["pairs"]) == 1,
          [int(plane.material.numsubs), face_selections.face_materials("everywhere")])
    # an object with one ordinary material: the other faces keep it
    painted = rt.convertToPoly(rt.Box(name="painted"))
    plain = rt.Standardmaterial(name="plain")
    painted.material = plain
    registry = face_reg.Registry.load()
    face_groups.assign(painted, registry, "lid", 1.0, "faces", [1])
    registry.save()
    face_materials_module.put_on_faces(painted, [1], "proj\\data\\lid_co.paa", "", face_importer.arma_material)
    check("faces: an object with one ordinary material keeps it on the other faces",
          rt.classOf(painted.material) == rt.Multimaterial and painted.material.materialList[0] == plain and
          [int(rt.polyop.getFaceMatID(painted, f)) for f in range(1, 7)] == [2, 1, 1, 1, 1, 1],
          [int(rt.polyop.getFaceMatID(painted, f)) for f in range(1, 7)])
    rt.delete(painted)
    tab.do("clear", "strip")
    tab.do("clear", "everywhere")
    plane.material = None
    from zasleh.ui.selections_tab import known_names
    check("names offered while typing: the scene's, and the chosen name set's",
          {"alpha", "everywhere"} <= set(known_names()) and "otocVez" not in known_names() and
          {"alpha", "otocVez", "koloL1"} <= set(known_names("tank")), known_names()[:12])
    # a name set: what the object lacks is listed in grey; a double click assigns what is picked
    before = listed()
    tab.name_set.setCurrentText("tank")
    turret = len(tab.names) + tab.offered.index("otocVez")
    check("name set: the object's own selections first, then the ones it lacks, with what they are",
          {"tank", "car", "house"} <= {tab.name_set.itemText(i) for i in range(tab.name_set.count())} and
          listed()[:len(before)] == before and "otocVez" in tab.offered and
          tab.list.item(turret).text() == "+ otocVez   - turret, turns left and right" and tab.current() == "",
          [listed()[:4], tab.offered[:4]])
    tab.list.setCurrentRow(turret)
    tab.item_clicked(tab.list.item(turret))
    check("name set: a click on a grey row puts its name into the field; the menu has nothing to delete there",
          tab.name.text() == "otocVez" and tab.current() == "")
    tab.item_double_clicked(tab.list.item(turret))
    check("name set: a double click on a grey row assigns what is picked",
          "otocVez" in tab.names and "otocVez" not in tab.offered and tab.current() == "otocVez" and
          "assigned" in tab.status.text(), [tab.names, tab.status.text()])
    tab.do("clear", "otocVez")
    tab.name_set.setCurrentIndex(0)
    check("name set: without one the list is the object's own again", listed() == before and tab.offered == [], listed())
    from zasleh import settings as kept_settings
    kept_settings.put("nameSet", kept_set if tab.name_set.findText(kept_set) > 0 else "")   # the widget stays on "none"
    rt.clearSelection()
    ui.selection_changed()
    check("nothing selected: the list empties by itself", tab.object_label.text().startswith("Object: (select") and listed() == [])

    # -- Model: import a small p3d, export it again
    work = os.path.join(os.environ["ZASLEH_TMP"], "zasleh_panel_test")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    model = P3D()
    lod = LOD(1.0)
    lod.points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    lod.point_flags = [0] * 4
    lod.normals = [(0.0, 1.0, 0.0)]
    lod.faces.append(Face.new((0, 1, 2, 3), (0, 0, 0, 0), ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
                              texture="proj\\data\\a_co.paa", material=""))
    model.lods.append(lod)
    source = os.path.join(work, "in.p3d")
    formats.write(model, source)

    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.model
    panel.tabs.setCurrentWidget(tab)
    panel.log.clear()
    kept_split = (tab.split_proxies.isChecked(), tab.split_names.text())
    tab.split_proxies.setChecked(False)
    tab.split_names.setText("")
    check("import", tab.import_file(source) and "in: 1 LOD(s)" in panel.log.toPlainText() and
          "Split off" not in panel.log.toPlainText(), panel.log.toPlainText())
    layers = [(tab.layers.item(i).text(), tab.layers.item(i).checkState() == QtCore.Qt.Checked) for i in range(tab.layers.count())]
    check("the imported LOD is listed and ticked", ("1  ->  1", True) in layers, layers)
    target = os.path.join(work, "out.p3d")
    check("export", tab.export_file(target) and os.path.isfile(target) and "out.p3d: 1 LOD(s)" in panel.log.toPlainText(),
          panel.log.toPlainText())
    again = formats.read(target)
    check("what was exported is what was imported", len(again.lods) == 1 and again.lods[0].faces[0].points == (0, 1, 2, 3) and
          again.lods[0].faces[0].texture == "proj\\data\\a_co.paa")
    for i in range(tab.layers.count()):
        tab.layers.item(i).setCheckState(QtCore.Qt.Unchecked)
    check("export with no layer ticked says so", not tab.export_file(target) and "tick at least one layer" in panel.log.toPlainText())
    check("a file that is not a p3d: a line in the log, no crash", not tab.import_file(os.path.join(work, "missing.p3d")) and
          "Import failed" in panel.log.toPlainText())
    # import with proxies as objects of their own
    lod.points += [(5.0, 0.0, 0.0), (5.0, 1.0, 0.0), (5.0, 0.0, 1.0)]
    lod.point_flags = [0] * 7
    lod.faces.insert(0, Face.new((4, 5, 6), (0, 0, 0), ((0.0, 0.0),) * 3, texture="", material=""))
    lod.taggs.append(formats.Selection("proxy:\\a3\\x\\gunner.001", bytes([0, 0, 0, 0, 1, 1, 1]), bytes([1, 0])))
    proxied = os.path.join(work, "proxied.p3d")
    formats.write(model, proxied)
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab.split_proxies.setChecked(True)
    panel.log.clear()
    check("import with proxies as objects: an object per proxy, said in the log",
          tab.import_file(proxied) and "Split off: 1 - 1 object(s)" in panel.log.toPlainText() and
          sorted(str(n.name) for n in rt.objects) == ["proxied_1", "proxy:\\a3\\x\\gunner.001"],
          [panel.log.toPlainText(), [str(n.name) for n in rt.objects]])
    check("... and the export puts the proxy back where it was in the file",
          tab.export_file(target) and [f.points for f in formats.read(target).lods[0].faces] == [(4, 5, 6), (0, 1, 2, 3)],
          [f.points for f in formats.read(target).lods[0].faces])
    # a binarized model goes through the debinarizer; a batch file stands in for it
    binarized = os.path.join(work, "bin", "in.p3d")
    os.makedirs(os.path.dirname(binarized))
    with open(binarized, "wb") as stream:
        stream.write(b"ODOL" + bytes(32))
    tool = os.path.join(work, "tool.bat")
    with open(tool, "w") as stream:
        stream.write('@echo off\ncopy /y "%~dp0proxied.p3d" "%~2\\in.p3d" >nul\n')
    from zasleh import settings as path_settings
    kept_tool = path_settings.get("debinarizer")
    path_settings.put("debinarizer", "")
    rt.resetMaxFile(rt.Name("noPrompt"))
    panel.log.clear()
    check("a binarized model without a debinarizer: said in the log",
          not tab.import_file(binarized) and "set the path of a debinarizer" in panel.log.toPlainText(), panel.log.toPlainText())
    path_settings.put("debinarizer", tool)
    check("a binarized model is converted and imported under its own name",
          tab.import_file(binarized) and "made editable by tool.bat" in panel.log.toPlainText() and
          "in_1" in [str(n.name) for n in rt.objects], [panel.log.toPlainText(), [str(n.name) for n in rt.objects]])
    path_settings.put("debinarizer", kept_tool)
    tab.split_proxies.setChecked(kept_split[0])
    tab.split_names.setText(kept_split[1])
    tab.split_names.editingFinished.emit()
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab.import_file(source)
    # LOD layers: add, duplicate, rename, show one, delete
    answers = []
    tab.ask = lambda title, initial="": answers.pop(0)
    tab.confirm = lambda question: True

    def rows():
        return [tab.layers.item(i).text() for i in range(tab.layers.count())]

    def pick(layer):
        tab.layers.setCurrentRow(next(i for i in range(tab.layers.count())
                                      if tab.layers.item(i).data(QtCore.Qt.UserRole) == layer))

    answers.append("Geometry")
    tab.lod("add")
    check("lods: add", "Geometry  ->  Geometry" in rows() and str(rt.LayerManager.current.name) == "Geometry", rows())
    answers.append("Geometry")
    tab.lod("add")
    check("lods: a name that is taken is refused", "already is a layer" in panel.log.toPlainText())
    from zasleh import lodtools
    pick("Geometry")
    tab.ask_lines = lambda title, initial="": "class = house\nautocenter=0;  map = house"
    tab.lod("properties")
    check("lods: named properties typed as lines", lodtools.properties("Geometry") ==
          [("class", "house"), ("autocenter", "0"), ("map", "house")], lodtools.properties("Geometry"))
    seen = []
    pick("Geometry")
    tab.ask_lines = lambda title, initial="": seen.append(initial) or "class = house\nno equals sign"
    tab.lod("properties")
    check("lods: the dialog opens with what is set; a line that is no property is refused, nothing changes",
          seen == ["class = house\nautocenter = 0\nmap = house"] and "is not \"key = value\"" in panel.log.toPlainText() and
          len(lodtools.properties("Geometry")) == 3, [seen, lodtools.properties("Geometry")])
    box = rt.convertToPoly(rt.Box(name="geo_box"))
    rt.LayerManager.getLayerFromName("Geometry").addNode(box)
    from zasleh import exporter as exp0
    written = exp0.build_model(["Geometry"])[0].lods[0]
    check("lods: the properties are written to the p3d", [(p.key, p.value) for p in written.properties] ==
          [("class", "house"), ("autocenter", "0"), ("map", "house")], [(p.key, p.value) for p in written.properties])
    rt.delete(box)
    pick("1")
    answers.append("2")
    tab.lod("duplicate")
    two = rt.LayerManager.getLayerFromName("2")
    copies = list(rt.zaslehLayerNodes(two)) if two is not None else []
    from zasleh import exporter as exp
    made = exp.build_model(["1", "2"])[0]
    check("lods: duplicate copies the objects with their data", len(copies) == 1 and len(made.lods) == 2 and
          made.lods[1].faces[0].points == made.lods[0].faces[0].points and
          made.lods[1].faces[0].texture == "proj\\data\\a_co.paa" and made.lods[1].resolution == 2.0,
          [len(copies), [l.resolution for l in made.lods]])
    pick("2")
    answers.append("3")
    tab.lod("rename")
    check("lods: rename", "3  ->  3" in rows() and "2  ->  2" not in rows() and
          exp.build_model(["3"])[0].lods[0].resolution == 3.0, rows())
    pick("1")
    tab.lod("show_only")
    hidden = {str(rt.LayerManager.getLayer(i).name): bool(rt.LayerManager.getLayer(i).ishidden)
              for i in range(int(rt.LayerManager.count))}
    check("lods: show only this", hidden["1"] is False and hidden["3"] is True and hidden["Geometry"] is True and
          str(rt.LayerManager.current.name) == "1", hidden)
    tab.lod("show_all")
    check("lods: show all", not any(bool(rt.LayerManager.getLayer(i).ishidden) for i in range(int(rt.LayerManager.count))))
    pick("3")
    tab.lod("delete")
    check("lods: delete takes the layer and its objects", rt.LayerManager.getLayerFromName("3") is None and
          "3  ->  3" not in rows() and all(rt.isValidNode(n) is False for n in copies), rows())
    pick("1")

    # the small tools for selected objects
    box = rt.Box(length=10, width=20, height=30, name="crate", pos=rt.Point3(50, 0, 0))
    box.scale = rt.Point3(2, 1, 1)
    rt.select(box)
    check("prep: to Editable Poly", tab.prepare("to_poly") == 1 and str(rt.classOf(box)) == "Editable_Poly")
    tab.prepare("reset_xform")
    check("prep: reset xform bakes the scale", [round(v, 3) for v in (box.scale.x, box.scale.y, box.scale.z)] == [1.0, 1.0, 1.0] and
          str(rt.classOf(box)) == "Editable_Poly", str(box.scale))
    tab.prepare("reset_pivots")
    check("prep: pivot in the centre", abs(box.pivot.x - box.center.x) < 1e-3 and abs(box.pivot.z - box.center.z) < 1e-3,
          [str(box.pivot), str(box.center)])
    check("prep: clean on a sound mesh removes nothing", tab.prepare("clean") == 0 and int(rt.polyop.getNumFaces(box)) == 6)
    rt.delete(box)

    # the log: one line while folded, opens for a report
    check("log: a report opened it, the bar shows the first line", panel.log.isVisible() and panel.last.text() != "")
    panel.log_toggle.setChecked(False)
    panel.say("one line")
    check("log: folded, a single line does not open it", not panel.log.isVisible() and panel.last.text() == "one line")

    options = tab.options()
    check("options come from the widgets", options.convert_paa and not options.gen_rvmat and not options.deploy and
          options.deploy_dir != "", options)
    # -- Memory points
    from zasleh import memory
    from zasleh import exporter as exp
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.memory
    panel.tabs.setCurrentWidget(tab)
    tab.confirm = lambda question: True
    crate = rt.convertToPoly(rt.Box(length=10, width=10, height=10, name="crate", pos=rt.Point3(4, 6, 0)))
    rt.select(crate)

    def shown():
        return [tab.list.item(i).text() for i in range(tab.list.count())]

    tab.name.setText("pos_driver")
    tab.do("centre")
    made = memory.points()
    check("memory: a point at the centre of the selected object, on the Memory layer", shown() == ["pos_driver"] and
          len(made) == 1 and [round(v, 3) for v in made[0][2]] == [4.0, 6.0, 5.0], [shown(), made[0][2] if made else None])
    rt.clearSelection()
    tab.do("centre")
    check("memory: nothing picked is said, not raised", "Pick vertices" in panel.log.toPlainText() and len(memory.points()) == 1)
    first = memory.add_point((0.0, 0.0, 1.0))
    second = memory.add_point((0.0, 5.0, 1.0))
    tab.refresh()
    check("memory: unnamed points are listed as such", shown() == ["(no name)", "(no name)", "pos_driver"], shown())
    tab.list.item(0).setSelected(True)
    tab.list.item(1).setSelected(True)
    check("memory: picking in the list selects in the scene", {str(n.name) for n in rt.selection} == {"point"} and
          len(list(rt.selection)) == 2, [str(n.name) for n in rt.selection])
    tab.name.setText("axis_wheel")
    tab.do("axis")
    check("memory: two points become an axis", shown() == ["axis_wheel", "axis_wheel", "pos_driver"] and
          memory.names_of(first) == ["axis_wheel"] and memory.names_of(second) == ["axis_wheel"], shown())
    lod = exp.build_model(["Memory"])[0].lods[0]
    check("memory: exported as selections of the Memory LOD",
          {s.name: len(s.point_indices()) for s in lod.selections} == {"axis_wheel": 2, "pos_driver": 1} and len(lod.faces) == 0,
          {s.name: len(s.point_indices()) for s in lod.selections})
    tab.list.clearSelection()
    tab.list.item(2).setSelected(True)
    tab.name.setText("pos_driver, pos_driver_dir")
    tab.do("rename")
    lod = exp.build_model(["Memory"])[0].lods[0]
    check("memory: a point under two names", "pos_driver, pos_driver_dir" in shown() and
          sorted(s.name for s in lod.selections) == ["axis_wheel", "pos_driver", "pos_driver_dir"], shown())
    rt.select(first)
    ui.selection_changed()
    check("memory: selecting in the scene marks the row", [i.row() for i in tab.list.selectedIndexes()] ==
          [next(k for k, (node, _names) in enumerate(tab.rows) if node == first)])
    tab.size.setValue(25.0)
    check("memory: marker size", abs(float(first.size) - 25.0) < 1e-3)
    tab.hide_points.setChecked(True)
    tab.xray.setChecked(True)
    check("memory: view switches", bool(first.isHidden) and bool(crate.xray) and not bool(crate.isHidden))
    tab.hide_points.setChecked(False)
    tab.xray.setChecked(False)
    tab.hide_geometry.setChecked(True)
    check("memory: hide geometry", bool(crate.isHidden) and not bool(first.isHidden) and not bool(crate.xray))
    tab.hide_geometry.setChecked(False)
    tab.list.clearSelection()
    tab.list.item(0).setSelected(True)
    tab.do("delete")
    check("memory: delete", len(memory.points()) == 2 and len(shown()) == 2, shown())
    memory.placed(1.0, 2.0, 3.0)
    check("memory: a point placed with the mouse tool lands on the layer", len(memory.points()) == 3)
    try:
        memory.add_at_verts()
        check("memory: at verts with nothing picked is refused", False)
    except memory.MemoryError_:
        check("memory: at verts with nothing picked is refused", True)

    # -- Hit points: a cloud inside an object is one selection; radius per selection, drawn as spheres
    from zasleh import hitpoints
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.hitpoints
    panel.tabs.setCurrentWidget(tab)
    panel.log.clear()
    rack = rt.Box(length=1.0, width=2.0, height=1.0, name="int_ammo_hit", pos=rt.Point3(10, 0, 0))
    rack.rotation = rt.EulerAngles(0, 0, 30)
    rt.select(rack)
    for box, value in zip(tab.spacing, (0.5, 0.5, 0.5)):
        box.setValue(value)
    made = tab.fill()
    clouds = [n for n in rt.objects if str(n.layer.name) == "HitPoints"]
    check("hit points: a turned 2 x 1 x 1 box takes 4 x 2 x 2 points, as one object on the HitPoints layer named after it",
          made == 16 and len(clouds) == 1 and str(clouds[0].name) == "int_ammo_hit" and
          rt.classOf(clouds[0]) == rt.Editable_Poly and tab.rows() == [("int_ammo_hit", "16", "")], [made, tab.rows()])
    middle = [sum(float(rt.polyop.getVert(clouds[0], v)[axis]) for v in range(1, 49)) / 48.0 for axis in range(3)]
    check("hit points: the cloud sits in the middle of the object, on its own axes",
          all(abs(middle[axis] - float(rack.center[axis])) < 1e-3 for axis in range(3)), middle)
    tab.name.setText("engine_hit")
    for box in tab.spacing:
        box.setValue(0.1)
    made = tab.fill()
    check("hit points: 2000 points are one more object, not 2000 helpers; the typed name wins over the object's",
          made == 2000 and len([n for n in rt.objects if str(n.layer.name) == "HitPoints"]) == 2 and
          tab.rows() == [("engine_hit", "2000", ""), ("int_ammo_hit", "16", "")], [made, tab.rows()])
    sheet = rt.convertToPoly(rt.Plane(length=1, width=1, name="open_sheet", pos=rt.Point3(20, 0, 0)))
    rt.select(sheet)
    check("hit points: an object that encloses nothing gives no points and says so",
          tab.fill() == 0 and "is it closed" in panel.log.toPlainText())
    rt.delete(sheet)

    tab.table.selectRow(1)
    tab.radius.setValue(0.15)
    tab.set_radius()
    tab.show_button.setChecked(True)
    drawn = [n for n in rt.objects if rt.getUserProp(n, "zasleh_display") is not None]
    check("hit points: radius of a selection, drawn as a sphere around each of its points",
          tab.rows()[1] == ("int_ammo_hit", "16", "0.15") and len(drawn) == 1 and int(drawn[0].numfaces) == 16 * 32 and
          bool(drawn[0].isFrozen) and "16 sphere(s) drawn" in panel.log.toPlainText(), [tab.rows()[1], len(drawn)])
    with open(os.path.join(os.environ["ZASLEH_TMP"], "zasleh_hit_config.cpp"), "w") as stream:
        stream.write('class HitPoints { class HitHull: HitHull { armor = -190; name = "int_ammo_hit"; '
                     'visual = "dmg_hull"; radius = 0.25; }; class HitGun { name = "gun_hit"; radius = 1; }; };')
    done = tab.load_radii(os.path.join(os.environ["ZASLEH_TMP"], "zasleh_hit_config.cpp"))
    os.remove(os.path.join(os.environ["ZASLEH_TMP"], "zasleh_hit_config.cpp"))
    drawn = [n for n in rt.objects if rt.getUserProp(n, "zasleh_display") is not None]
    box_size = drawn[0].max - drawn[0].min if drawn else None
    check("hit points: radius from the classes of a config; what is drawn follows",
          done == ["int_ammo_hit"] and tab.rows()[1][2] == "0.25" and len(drawn) == 1 and
          hitpoints.radii() == {"int_ammo_hit": 0.25}, [done, tab.rows()[1], hitpoints.radii()])
    tab.table.clearSelection()
    tab.radius.setValue(0.05)
    tab.set_radius()
    drawn = [n for n in rt.objects if rt.getUserProp(n, "zasleh_display") is not None]
    check("hit points: a radius for all the other points", tab.rows()[-1] == ("(all other points)", "", "0.05") and
          len(drawn) == 1 and int(drawn[0].numfaces) == 2016 * 32, [tab.rows()[-1], int(drawn[0].numfaces) if drawn else 0])
    from zasleh import exporter as hit_exporter
    built = hit_exporter.build_model(["HitPoints"])[0].lods[0]
    check("hit points: the p3d gets the 2016 points and the two selections, nothing of the spheres",
          len(built.points) == 2016 and not built.faces and
          sorted((s.name, len(s.weights) - s.weights.count(0)) for s in built.selections) ==
          [("engine_hit", 2000), ("int_ammo_hit", 16)], [len(built.points), len(built.faces)])
    tab.show_button.setChecked(False)
    check("hit points: hidden again", not [n for n in rt.objects if rt.getUserProp(n, "zasleh_display") is not None])

    # -- Settings: the paths live in one dialog
    from zasleh.ui.settings_dialog import SettingsDialog
    dialog = SettingsDialog(panel)
    dialog.rows["debinarizer"].edit.setText("D:\\tools\\debin.exe")
    dialog.rows["debinarizer"].edit.editingFinished.emit()
    dialog.rows["texConv"].edit.setText("  D:\\tools\\texconv.exe ")
    dialog.accept()
    check("settings: tex root, game data, debinarizer, ImageToPAA and texconv in one dialog, kept as typed",
          sorted(dialog.rows) == ["debinarizer", "gameRoot", "imageToPaa", "texConv", "texRoot"] and
          all_settings.get("debinarizer") == "D:\\tools\\debin.exe" and all_settings.get("texConv") == "D:\\tools\\texconv.exe" and
          panel.model.options().tex_conv == "D:\\tools\\texconv.exe", [all_settings.get("debinarizer"), all_settings.get("texConv")])
    for key in ("debinarizer", "texConv"):
        all_settings.put(key, SETTINGS_BEFORE[key])

    # -- Materials
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.materials
    work = os.path.join(os.environ["ZASLEH_TMP"], "zasleh_panel_test")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "root", "data"))
    os.makedirs(os.path.join(work, "elsewhere"))
    for name in (os.path.join("root", "data", "hull_co.png"), os.path.join("root", "data", "hull_nohq.png"),
                 os.path.join("root", "data", "hull_smdi.png"), os.path.join("root", "data", "gun_co.png"),
                 os.path.join("elsewhere", "far_co.png")):
        formats.paa.write_png(os.path.join(work, name), 1, 1, b"\x10\x20\x30")

    def with_material(name, colour=None, normal=None, specular=None, x=0.0):
        material = rt.Standardmaterial(name=name)
        if colour:
            material.diffuseMap = rt.Bitmaptexture(filename=os.path.join(work, colour))
        if normal:
            material.bumpMap = rt.Bitmaptexture(filename=os.path.join(work, normal))
        if specular:
            material.specularMap = rt.Bitmaptexture(filename=os.path.join(work, specular))
        node = rt.convertToPoly(rt.Box(name=name, pos=rt.Point3(x, 0, 0)))
        node.material = material
        return node

    with_material("whole", "root\\data\\hull_co.png", "root\\data\\hull_nohq.png", "root\\data\\hull_smdi.png")
    gun = with_material("colour_only", "root\\data\\gun_co.png", x=40.0)
    with_material("lost", "root\\data\\gone_co.png", x=80.0)
    with_material("bare", x=120.0)
    with_material("far", "elsewhere\\far_co.png", x=160.0)
    kept_root = path_settings.get("texRoot")
    path_settings.put("texRoot", os.path.join(work, "root"))
    panel.tabs.setCurrentWidget(tab)
    check("materials: what each one lacks", dict(tab.statuses()) == {
        "whole": "OK", "colour_only": "no nohq/smdi", "lost": "file missing", "bare": "no _co", "far": "outside root"}, tab.statuses())
    rows = [name for name, _status in tab.statuses()]
    tab.table.selectRow(rows.index("far"))
    tab.find.setText(os.path.join(work, "elsewhere") + "\\far_co")
    tab.replacement.setText(os.path.join(work, "root", "data") + "\\gun_co")
    check("materials: replace in the picked rows", tab.replace(False) == 1 and dict(tab.statuses())["far"] == "no nohq/smdi",
          tab.statuses())
    tab.table.selectRow(rows.index("colour_only"))
    check("materials: select the objects that use a material", tab.select_objects() == 1 and
          [str(n.name) for n in rt.selection] == ["colour_only"])
    tab.selected_only.setChecked(True)
    check("materials: selected objects only", [name for name, _status in tab.statuses()] == ["colour_only"], tab.statuses())
    tab.selected_only.setChecked(False)
    tab.find.setText("")
    check("materials: replace without a find text says so", tab.replace(True) == 0 and "fill the find field" in panel.log.toPlainText())

    # maps lying next to the colour map; .rvmat files; paths of a material's own
    from zasleh import exporter, materials, settings
    formats.paa.write_png(os.path.join(work, "root", "data", "gun_nohq.png"), 1, 1, b"\x80\x80\xff")
    with open(os.path.join(work, "root", "data", "gun_smdi.paa"), "wb") as stream:
        stream.write(b"not a real paa")
    tab.scan()
    check("materials: maps lying next to the colour map count", dict(tab.statuses())["colour_only"] == "OK" and
          tab.table.item(rows.index("colour_only"), 3).text() == "f", tab.statuses())
    tab.table.selectRow(rows.index("colour_only"))
    counts = tab.find_maps()
    check("materials: find maps puts the picture in, a lone .paa is only counted",
          counts == {"normal": 1, "specular": 0, "paa_only": 1} and
          materials.map_file(materials.normal_map(gun.material)).lower().endswith("gun_nohq.png") and
          tab.table.item(rows.index("colour_only"), 3).text() == "Y" and
          [index.row() for index in tab.table.selectionModel().selectedRows()] == [rows.index("colour_only")],
          [counts, materials.map_file(materials.normal_map(gun.material))])

    kept_preset = settings.get("rvmatPreset", "Super")
    hull_rvmat = os.path.join(work, "root", "data", "hull.rvmat")
    tab.table.selectRow(rows.index("whole"))
    tab.preset.setCurrentText("NormalSpecular")
    asked = []
    tab.confirm = lambda question: asked.append(question) or False
    done = tab.write_rvmats()
    text = open(hull_rvmat).read() if os.path.isfile(hull_rvmat) else ""
    check("materials: an .rvmat of the chosen preset for the picked row",
          done["written"] == 1 and done["kept"] == 0 and not asked and "NormalMapSpecularDIMap" in text and
          'texture="data\\hull_nohq.paa"' in text and 'texture="data\\hull_smdi.paa"' in text, [done, text[:300]])
    tab.preset.setCurrentText("Super")
    done = tab.write_rvmats()
    check("materials: an .rvmat that is there is kept when the answer is no",
          done["written"] == 0 and done["kept"] == 1 and len(asked) == 1 and "NormalMapSpecularDIMap" in open(hull_rvmat).read(),
          [done, asked])
    tab.confirm = lambda question: True
    done = tab.write_rvmats()
    check("materials: ... and replaced when it is yes", done["written"] == 1 and 'PixelShaderID="Super"' in open(hull_rvmat).read(), done)
    tab.table.clearSelection()
    done = tab.write_rvmats()
    check("materials: nothing picked means every material; those without a colour map are left out",
          done["skipped"] == 1 and os.path.isfile(os.path.join(work, "root", "data", "gun.rvmat")) and
          'texture="data\\gun_smdi.paa"' in open(os.path.join(work, "root", "data", "gun.rvmat")).read(), done)
    tab.preset.setCurrentText(kept_preset)

    bare = next(m for m in tab.found if str(m.name) == "bare")
    tab.table.selectRow(rows.index("bare"))
    tab.texture.setText("proj\\data\\bare_co.paa")
    tab.rvmat.setText("proj\\data\\bare.rvmat")
    check("materials: paths of its own make a material without maps exportable",
          tab.set_paths() == 1 and dict(tab.statuses())["bare"] == "paths set" and
          exporter.Textures()(bare, 1) == ("proj\\data\\bare_co.paa", "proj\\data\\bare.rvmat") and
          tab.texture.text() == "proj\\data\\bare_co.paa", [tab.statuses(), tab.texture.text()])
    tab.table.selectRow(rows.index("whole"))
    check("materials: for a material without paths of its own the fields show what its maps give",
          tab.texture.text() == "" and tab.texture.placeholderText() == "from the maps: data\\hull_co.paa" and
          tab.rvmat.placeholderText().endswith("data\\hull.rvmat"), [tab.texture.placeholderText(), tab.rvmat.placeholderText()])
    check("materials: Automatic on a material without paths of its own says so", tab.clear_paths() == 0)
    tab.table.selectRow(rows.index("bare"))
    check("materials: Automatic takes the paths away again", tab.clear_paths() == 1 and
          dict(tab.statuses())["bare"] == "no _co" and exporter.Textures()(bare, 1) == ("", ""), tab.statuses())
    path_settings.put("texRoot", kept_root)
    shutil.rmtree(work, ignore_errors=True)

    # -- Config: bones from the scene, an animation, model.cfg out and in again
    from zasleh.formats import modelcfg
    from zasleh import groups
    from zasleh import registry as reg
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.config
    panel.tabs.setCurrentWidget(tab)
    hull = rt.convertToPoly(rt.Box(name="hull"))
    turret = rt.convertToPoly(rt.Box(name="turret", pos=rt.Point3(0, 0, 30)))
    gun = rt.convertToPoly(rt.Box(name="gun", pos=rt.Point3(0, 0, 60)))
    turret.parent = hull
    gun.parent = turret
    rt.convertToPoly(rt.Box(name="loose", pos=rt.Point3(90, 0, 0)))
    tab.from_links()
    check("config: bones from linked objects", tab.bones() == [("hull", ""), ("turret", "hull"), ("gun", "turret")], tab.bones())
    layer = rt.LayerManager.newLayerFromName("1")
    for node in (hull, turret, gun):
        layer.addNode(node)
    registry = reg.Registry.load()
    groups.assign(hull, registry, "camo1", 1.0, "faces", [1, 2])
    registry.save()
    memory = rt.LayerManager.newLayerFromName("Memory")
    memory.addNode(rt.Point(name="axis_turret"))
    from zasleh import skeleton
    names, points = skeleton.scene_names()
    check("config: names from the scene", names == ["camo1", "gun", "hull", "turret"] and points == ["axis_turret"], [names, points])
    tab.from_selections()
    check("config: selections that are not bones yet are added, the tree is kept",
          tab.bones() == [("hull", ""), ("turret", "hull"), ("gun", "turret"), ("camo1", "")], tab.bones())
    tab.tree.setCurrentItem(tab.tree.topLevelItem(1))
    tab.tree.topLevelItem(1).setSelected(True)
    tab.remove_bones()
    tab.tree.clearSelection()
    tab.tree.setCurrentItem(tab.tree.topLevelItem(0).child(0))
    tab.tree.topLevelItem(0).child(0).setSelected(True)
    tab.remove_bones()
    check("config: removing a bone moves its children up", tab.bones() == [("hull", ""), ("gun", "hull")], tab.bones())
    check("config: To scene with bones that have no faces of their own says so",
          tab.to_scene() == 0 and "no bone has faces of its own" in panel.log.toPlainText(), panel.log.toPlainText()[-300:])
    tab.model.setText("t34")
    tab.skeleton.setText("t34_skeleton")
    tab.sections.setPlainText("camo1\nzasleh")
    row = tab.add_animation(modelcfg.Animation("Turret", "rotationY", "mainTurret", "turret", "axis_turret"))
    tab.table.item(row, 8).setText("0")
    tab.table.item(row, 9).setText("rad 360")
    row = tab.add_animation(modelcfg.Animation("Hatch", "hide", "user", "hatch", "", False))
    tab.table.item(row, 8).setText("0.5")
    text = tab.preview()
    check("config: preview", 'class t34 : Default' in text and '"gun", "hull"' in text and 'angle1 = "rad 360";' in text and
          "hideValue = 0.5;" in text and '"camo1",' in text and text in panel.log.toPlainText(), text[:300])
    work = os.path.join(os.environ["ZASLEH_TMP"], "zasleh_panel_test")
    os.makedirs(work, exist_ok=True)
    saved = os.path.join(work, "model.cfg")
    before = tab.collect()
    check("config: save", tab.save_file(saved) and os.path.isfile(saved))
    tab.fill(modelcfg.ModelCfg())
    check("config: load brings everything back", tab.load_file(saved) and tab.collect() == before, [tab.collect(), before])
    two = os.path.join(work, "two.cfg")
    with open(two, "w") as stream:
        stream.write('class CfgSkeletons { class S { skeletonBones[] = {"a", ""}; }; };\n'
                     'class CfgModels { class first { skeletonName = "S"; }; class second { skeletonName = "S"; sections[] = {"x"}; }; };')
    tab.choose = lambda names: names[1]
    check("config: a file with several models asks which one", tab.load_file(two) and tab.model.text() == "second" and
          tab.collect().sections == ["x"] and tab.bones() == [("a", "")])
    editor = tab.table.itemDelegateForColumn(3).createEditor(tab.table, None, None)
    check("config: the selection column offers the bones", editor.completer() is not None and
          editor.completer().model().stringList() == ["a"])
    tab.load_file(saved)
    with open(saved, "w") as stream:
        stream.write("class CfgModels { class A { sections[] = ; }; };")
    check("config: a broken file is reported, the tab keeps what it had",
          not tab.load_file(saved) and "not read" in panel.log.toPlainText() and tab.collect() == before)
    # -- Multi-structure: two parts, a memory point each, a p3d each around its own origin
    from zasleh import multistruct
    from zasleh import memory as memory_points
    rt.resetMaxFile(rt.Name("noPrompt"))
    tab = panel.multi
    panel.tabs.setCurrentWidget(tab)
    part_a = rt.convertToPoly(rt.Box(length=2, width=2, height=2, name="PART1", pos=rt.Point3(10, 0, 0)))
    part_b = rt.convertToPoly(rt.Box(length=2, width=2, height=2, name="PART2", pos=rt.Point3(-30, 5, 0)))
    geo_layer = rt.LayerManager.newLayerFromName("Geometry")
    geo_layer.addNode(rt.convertToPoly(rt.Box(length=2, width=2, height=2, name="PART1_geo", pos=rt.Point3(10, 0, 0))))
    rt.select(rt.Array(part_a, part_b))
    tab.add_selected()
    check("multi: parts from the selection", tab.list.count() == 2 and "PART1  ->  pos_PART1   [PART1]" in tab.list.item(0).text(),
          [tab.list.item(i).text() for i in range(tab.list.count())])
    tab.list.setCurrentRow(1)
    tab.cls.setText("Land_Part2")
    tab.mass.setValue(0.0)
    tab.set_part()
    tab.build_points()
    points = {str(n.name): (n.pos.x, n.pos.y, n.pos.z) for n, _names, _p in memory_points.points()}
    check("multi: a memory point at every part's centre", points == {"pos_PART1": (10.0, 0.0, 1.0), "pos_PART2": (-30.0, 5.0, 1.0)}, points)
    check("multi: the config line", tab.cfg_line() == 'multiStructureParts[] = {{"PART1","pos_PART1"},{"Land_Part2","pos_PART2"}};')
    tab.list.setCurrentRow(0)
    tab.centre()
    moved = (round(part_a.center.x, 3), round(part_a.center.y, 3), round(part_a.center.z, 3))
    tab.restore()
    back = (round(part_a.center.x, 3), round(part_a.center.y, 3), round(part_a.center.z, 3))
    check("multi: centre and restore", moved == (0.0, 0.0, 0.0) and back == (10.0, 0.0, 1.0), [moved, back])
    tab.verify()
    check("multi: verify writes to the log", "Multi-structure check:" in panel.log.toPlainText() and "point ok" in panel.log.toPlainText())
    work = os.path.join(os.environ["ZASLEH_TMP"], "zasleh_panel_test")
    os.makedirs(work, exist_ok=True)
    tab.geometry.setChecked(True)
    tab.geo_props.setText("class=house; sbsource=shadowvolume")
    tab.mass_all.setValue(400.0)
    objects_before = len(list(rt.objects))
    layers_before = int(rt.LayerManager.count)
    report = tab.export_to(work)
    first = formats.read(os.path.join(work, "PART1.p3d")) if os.path.isfile(os.path.join(work, "PART1.p3d")) else None
    second = formats.read(os.path.join(work, "PART2.p3d")) if os.path.isfile(os.path.join(work, "PART2.p3d")) else None
    check("multi: one p3d per part", report["ok"] == ["PART1", "PART2"] and not report["failed"] and
          report["no_geometry"] == ["PART2"], report)

    def extent(lod):
        return [round(min(p[k] for p in lod.points), 3) for k in range(3)] + [round(max(p[k] for p in lod.points), 3) for k in range(3)]

    check("multi: the part sits around the origin, autocenter is off",
          first is not None and extent(first.lods[0]) == [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0] and
          first.lods[0].get_property("autocenter") == "0" and second is not None and
          extent(second.lods[0]) == [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0], [first and extent(first.lods[0])])
    geo = first.lods[1] if first is not None and len(first.lods) == 2 else None
    check("multi: the Geometry LOD comes along, moved the same way, with its properties and mass",
          geo is not None and formats.lod_name(geo.resolution) == "Geometry" and extent(geo) == [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0] and
          geo.get_property("class") == "house" and geo.get_property("autocenter") == "0" and
          abs(sum(geo.mass) - 400.0) < 0.01 and len(second.lods) == 1, geo and [geo.properties, sum(geo.mass or [])])
    check("multi: the scene is left as it was", len(list(rt.objects)) == objects_before and
          int(rt.LayerManager.count) == layers_before and round(part_a.center.x, 3) == 10.0)
    tab.refresh()
    check("multi: the part list is kept with the scene", tab.list.count() == 2 and "[Land_Part2]" in tab.list.item(1).text())
    shutil.rmtree(work, ignore_errors=True)
    ui.close()
    check("closing", ui.instance() is None)
    out["ok"] = all((v if isinstance(v, bool) else v[0]) for v in out["checks"].values())
except Exception as error:  # noqa: BLE001
    out["ok"] = False
    out["error"] = "%s: %s" % (type(error).__name__, error)
    out["trace"] = traceback.format_exc()
finally:
    for key, value in SETTINGS_BEFORE.items():
        all_settings.put(key, value)
with open(os.environ["ZASLEH_OUT"], "w", encoding="utf-8") as stream:
    json.dump(out, stream, indent=1, default=str)

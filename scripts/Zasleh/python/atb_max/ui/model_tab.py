import os
import shutil

import pymxs
from PySide2 import QtCore, QtWidgets

import atb_p3d
from atb_p3d import odol

from .. import exporter, importer, lodtools, parts, prep, reader, settings

rt = pymxs.runtime
P3D_FILTER = "Arma p3d (*.p3d)"


class PathRow(QtWidgets.QWidget):
    def __init__(self, key: str, caption: str, pick_folder: bool, tip: str):
        super().__init__()
        self.key, self.caption, self.pick_folder = key, caption, pick_folder
        self.edit = QtWidgets.QLineEdit(settings.get(key))
        self.edit.setToolTip(tip)
        self.edit.editingFinished.connect(lambda: settings.put(key, self.edit.text()))
        browse = QtWidgets.QToolButton()
        browse.setText("...")
        browse.clicked.connect(self.browse)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)

    def text(self) -> str:
        return self.edit.text().strip()

    def browse(self) -> None:
        if self.pick_folder:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, self.caption, self.text())
        else:
            path, _kind = QtWidgets.QFileDialog.getOpenFileName(self, self.caption, self.text(), "Programs (*.exe)")
        if path:
            self.edit.setText(os.path.normpath(path))
            settings.put(self.key, self.edit.text())


class ModelTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say

        import_button = QtWidgets.QPushButton("Import p3d...")
        import_button.setToolTip("Editable (MLOD) p3d: every LOD becomes a layer")
        import_button.clicked.connect(self.pick_import)
        self.previews = QtWidgets.QCheckBox("Show .paa textures in the viewport")
        self.previews.setChecked(settings.flag("paaPreview"))
        self.previews.toggled.connect(lambda on: settings.put("paaPreview", "1" if on else "0"))
        self.game_root = PathRow("gameRoot", "Unpacked game data", True,
                                 "The folder that holds a3\\...: textures of the game are shown on imported models")
        game_form = QtWidgets.QFormLayout()
        game_form.addRow("Game data", self.game_root)
        self.split_proxies = QtWidgets.QCheckBox("Proxies as separate objects")
        self.split_proxies.setToolTip("Every proxy triangle becomes an object named after the proxy. An export joins them again")
        self.split_proxies.setChecked(settings.flag("splitProxies", False))
        self.split_proxies.toggled.connect(lambda on: settings.put("splitProxies", "1" if on else "0"))
        self.split_names = QtWidgets.QLineEdit(settings.get("splitNames"))
        self.split_names.setPlaceholderText("selections, e.g. wheel_*, otocvez")
        self.split_names.setToolTip("Selections whose faces become objects of their own (* and ? allowed, comma between).\n"
                                    "A face goes with the first selection that has it. An export joins them again")
        self.split_names.editingFinished.connect(lambda: settings.put("splitNames", self.split_names.text()))
        game_form.addRow("Split off", self.split_names)
        self.debinarizer = PathRow("debinarizer", "Debinarizer", False,
                                   "A program that turns a binarized (ODOL) p3d into an editable one, called as\n"
                                   "\"program inFolder outFolder\" (P3DDebinarizer does). Binarized models go through it on import")
        game_form.addRow("Debinarizer", self.debinarizer)
        import_box = QtWidgets.QGroupBox("Import")
        box = QtWidgets.QVBoxLayout(import_box)
        box.addWidget(import_button)
        box.addWidget(self.previews)
        box.addWidget(self.split_proxies)
        box.addLayout(game_form)

        self.layers = QtWidgets.QListWidget()
        self.layers.setToolTip("LOD layers; the ticked ones are exported.\n"
                               "Double click: show only this LOD. Right click: add, rename, duplicate, properties, delete")
        self.layers.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.layers.customContextMenuRequested.connect(self.open_menu)
        self.layers.itemDoubleClicked.connect(lambda _item: self.lod("show_only"))
        self.paa = QtWidgets.QCheckBox("Use .paa paths")
        self.paa.setChecked(True)
        self.rvmat = QtWidgets.QCheckBox("Generate .rvmat")
        self.rvmat.setToolTip("An .rvmat per material, named on its faces. One that is there already is kept.\n"
                              "The shader is chosen in the Materials tab")
        self.deploy = QtWidgets.QCheckBox("Deploy textures to")
        self.deploy_dir = QtWidgets.QLineEdit(settings.get("deployDir", "data"))
        self.deploy_dir.setToolTip("Folder next to the p3d, or a full path. Files already there are kept")
        self.deploy_dir.editingFinished.connect(lambda: settings.put("deployDir", self.deploy_dir.text()))
        self.tex_root = PathRow("texRoot", "Texture root", True, "Texture paths are written relative to this folder, e.g. P:\\")
        if not self.tex_root.text():
            self.tex_root.edit.setText(settings.default_texture_root())
        self.image_to_paa = PathRow("imageToPaa", "ImageToPAA.exe", False, "Converts textures to .paa when deploying")
        self.tex_conv = PathRow("texConv", "texconv.exe", False, "For .dds sources")
        export_button = QtWidgets.QPushButton("Export p3d...")
        export_button.clicked.connect(self.pick_export)

        deploy_row = QtWidgets.QHBoxLayout()
        deploy_row.addWidget(self.deploy)
        deploy_row.addWidget(self.deploy_dir, 1)
        form = QtWidgets.QFormLayout()
        form.addRow("Tex root", self.tex_root)
        form.addRow("ImageToPAA", self.image_to_paa)
        form.addRow("Texconv", self.tex_conv)
        export_box = QtWidgets.QGroupBox("Export")
        box = QtWidgets.QVBoxLayout(export_box)
        box.addWidget(self.layers, 1)
        box.addWidget(self.paa)
        box.addWidget(self.rvmat)
        box.addLayout(deploy_row)
        box.addLayout(form)
        box.addWidget(export_button)

        prep_box = QtWidgets.QGroupBox("Selected objects")
        grid = QtWidgets.QGridLayout(prep_box)
        for at, (text, action, tip) in enumerate((
                ("Reset XForm", "reset_xform", "Bake rotation and scale into the mesh"),
                ("Reset pivot", "reset_pivots", "Pivot to the centre, aligned to the world"),
                ("To Editable Poly", "to_poly", "Collapse to Editable Poly"),
                ("Clean mesh", "clean", "Remove loose verts and broken faces"))):
            button = QtWidgets.QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, a=action: self.prepare(a))
            grid.addWidget(button, at // 2, at % 2)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(import_box)
        layout.addWidget(export_box, 1)
        layout.addWidget(prep_box)

    def refresh(self) -> None:
        checked = {self.layers.item(i).data(QtCore.Qt.UserRole): self.layers.item(i).checkState()
                   for i in range(self.layers.count())}
        self.layers.clear()
        for candidate in exporter.candidate_layers(include_empty=True):
            text = "%s  ->  %s" % (candidate["layer"], candidate["lod"] or "not a LOD name")
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, candidate["layer"])
            item.setToolTip("%d objects, %d points" % (candidate["objects"], candidate["points"]))
            default = QtCore.Qt.Checked if candidate["checked"] else QtCore.Qt.Unchecked
            item.setCheckState(checked.get(candidate["layer"], default))
            self.layers.addItem(item)

    def prepare(self, action: str) -> int:
        count = getattr(prep, action)()
        note = {"reset_xform": "XForm reset on %d object(s)", "reset_pivots": "pivot reset on %d object(s)",
                "to_poly": "%d object(s) are Editable Poly now", "clean": "clean mesh: %d broken face(s) removed"}[action]
        self.say(note % count)
        rt.redrawViews()
        return count

    # -- LOD layers

    def current_layer(self) -> str:
        item = self.layers.currentItem()
        return item.data(QtCore.Qt.UserRole) if item is not None else ""

    def ask(self, title: str, initial: str = "") -> str:
        names = lodtools.standard_names()
        if initial and initial not in names:
            names.insert(0, initial)
        at = names.index(initial) if initial in names else 0
        text, ok = QtWidgets.QInputDialog.getItem(self, title, "LOD name:", names, at, True)
        return text.strip() if ok else ""

    def confirm(self, question: str) -> bool:
        return QtWidgets.QMessageBox.question(self, "LODs", question) == QtWidgets.QMessageBox.Yes

    def lod(self, action: str) -> None:
        picked = self.current_layer()
        try:
            if action == "add":
                name = self.ask("New LOD")
                if name:
                    lodtools.add(name)
                    self.say("LOD %s added" % name)
            elif action == "show_all":
                lodtools.show_all()
            elif not picked:
                return
            elif action == "show_only":
                lodtools.show_only(picked)
                self.say("Showing %s only" % picked)
            elif action == "rename":
                name = self.ask("Rename LOD", picked)
                if name and name != picked:
                    lodtools.rename(picked, name)
                    self.say("%s renamed to %s" % (picked, name))
            elif action == "duplicate":
                name = self.ask("Duplicate LOD as", picked)
                if name:
                    self.say("%s copied to %s: %d object(s)" % (picked, name, lodtools.duplicate(picked, name)))
            elif action == "properties":
                before = "\n".join("%s = %s" % pair for pair in lodtools.properties(picked))
                typed = self.ask_lines("Named properties of %s" % picked, before)
                if typed is not None and typed != before:
                    self.say("%s: %d named propert(ies) set" % (picked, lodtools.set_properties(picked, typed)))
            elif action == "delete":
                if self.confirm("Delete the layer \"%s\" with everything on it?" % picked):
                    self.say("%s deleted: %d object(s)" % (picked, lodtools.delete(picked)))
        except lodtools.LodError as error:
            self.say(str(error))
        self.refresh()

    def ask_lines(self, title: str, initial: str = ""):
        """Lines of text, None if the dialog was cancelled"""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(self, title, "One per line, as  key = value  (class = house, "
                                                           "autocenter = 0, lodnoshadow = 1 ...)", initial)
        return text.strip() if ok else None

    def open_menu(self, position) -> None:
        item = self.layers.itemAt(position)
        if item is not None:
            self.layers.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        entries = (("Show only this", "show_only", False), ("Show all", "show_all", True), None, ("Add...", "add", True),
                   ("Rename...", "rename", False), ("Duplicate...", "duplicate", False),
                   ("Properties...", "properties", False), None, ("Delete", "delete", False))
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            text, action, always = entry
            added = menu.addAction(text)
            added.setEnabled(always or item is not None)
            added.triggered.connect(lambda _checked=False, a=action: self.lod(a))
        menu.exec_(self.layers.mapToGlobal(position))

    def chosen_layers(self) -> list:
        return [self.layers.item(i).data(QtCore.Qt.UserRole) for i in range(self.layers.count())
                if self.layers.item(i).checkState() == QtCore.Qt.Checked]

    def options(self) -> exporter.Options:
        return exporter.Options(convert_paa=self.paa.isChecked(), tex_root=self.tex_root.text(),
                                gen_rvmat=self.rvmat.isChecked(), rvmat_preset=settings.get("rvmatPreset", "Super"),
                                deploy=self.deploy.isChecked(),
                                deploy_dir=self.deploy_dir.text().strip() or "data",
                                image_to_paa=self.image_to_paa.text(), tex_conv=self.tex_conv.text())

    def import_file(self, path: str) -> bool:
        patterns = parts.patterns_of(self.split_names.text(), self.split_proxies.isChecked())
        work = settings.scratch_folder("odol", settings.default_texture_root())
        binarized = False
        try:
            binarized = odol.is_odol(path)
            if binarized:
                path = odol.to_mlod(path, self.debinarizer.text(), work)
            report = importer.import_p3d(path)
        except (atb_p3d.P3DError, OSError) as error:
            self.say("Import failed: %s" % error)
            return False
        finally:
            if binarized:
                shutil.rmtree(work, ignore_errors=True)
        if binarized:
            self.say("A binarized model, made editable by %s: what the game has no use for (sharp edges, "
                     "some selections, exact masses) does not come back" % os.path.basename(self.debinarizer.text()))
        made = parts.split_scene(patterns, [info["layer"] for info in report["lods"]])
        rt.redrawViews()
        self.say(importer.summary(report))
        if made:
            self.say("Split off: " + ", ".join("%s - %d object(s)" % pair for pair in made.items()))
        self.refresh()
        imported = {info["layer"] for info in report["lods"]}
        for i in range(self.layers.count()):            # what was just imported is ticked, whatever was before
            if self.layers.item(i).data(QtCore.Qt.UserRole) in imported:
                self.layers.item(i).setCheckState(QtCore.Qt.Checked)
        return True

    def export_file(self, path: str) -> bool:
        layers = self.chosen_layers()
        if not layers:
            self.say("Export: tick at least one layer")
            return False
        try:
            report = exporter.export_p3d(path, layers, self.options())
        except (reader.SceneError, atb_p3d.P3DError, OSError) as error:
            self.say("Export failed: %s" % error)
            return False
        self.say(exporter.summary(report))
        return True

    def pick_import(self) -> None:
        start = settings.get("lastDir")
        path, _kind = QtWidgets.QFileDialog.getOpenFileName(self, "Import p3d", start, P3D_FILTER + ";;All files (*.*)")
        if path:
            settings.put("lastDir", os.path.dirname(path))
            self.import_file(os.path.normpath(path))

    def pick_export(self) -> None:
        start = settings.get("lastDir")
        path, _kind = QtWidgets.QFileDialog.getSaveFileName(self, "Export p3d", start, P3D_FILTER)
        if path:
            settings.put("lastDir", os.path.dirname(path))
            self.export_file(os.path.normpath(path))

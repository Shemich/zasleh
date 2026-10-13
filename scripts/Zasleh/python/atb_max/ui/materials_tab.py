import os

import pymxs
from PySide2 import QtCore, QtGui, QtWidgets

from atb_p3d import rvmat

from .. import materials, settings
from .model_tab import PathRow

rt = pymxs.runtime
COLUMNS = ("Material", "Type", "Colour map", "N", "S", "Status")
COLOURS = {materials.OK: "#7fc97f", materials.WARN: "#e6c35c", materials.BAD: "#e06c6c"}
MAPS_TIP = "Y: in the material, f: a file next to the colour map"


def _button(text: str, slot, tip: str) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setToolTip(tip)
    button.clicked.connect(lambda _checked=False: slot())
    return button


class MaterialsTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say
        self.found = []             # materials, one per table row

        self.root = PathRow("texRoot", "Texture root", True, "Your project's texture root, e.g. P:\\")
        if not self.root.text():
            self.root.edit.setText(settings.default_texture_root())
        self.selected_only = QtWidgets.QCheckBox("Selected objects only")
        self.selected_only.toggled.connect(lambda _on: self.scan())
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.selected_only, 1)
        top.addWidget(_button("Scan", self.scan, "Read the materials of the scene again"))

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setToolTip("Materials the scene's geometry uses. Double click: open in the material editor")
        for column in (3, 4):
            self.table.horizontalHeaderItem(column).setToolTip(MAPS_TIP)
        self.table.itemDoubleClicked.connect(lambda item: materials.to_editor(self.found[item.row()]))
        self.table.itemSelectionChanged.connect(self.show_paths)

        self.preset = QtWidgets.QComboBox()
        self.preset.addItems(rvmat.PRESETS)
        self.preset.setCurrentText(settings.get("rvmatPreset", rvmat.DEFAULT))
        self.preset.setToolTip("Shader and stages of the .rvmat files. Export > Generate .rvmat uses it too")
        self.preset.currentTextChanged.connect(lambda name: settings.put("rvmatPreset", name))
        maps = QtWidgets.QHBoxLayout()
        maps.addWidget(_button("Find maps", self.find_maps, "Put the _nohq and _smdi pictures lying next to the colour map "
                                                            "into the free slots. Picked rows, or all of them"))
        maps.addWidget(_button("Write .rvmat", self.write_rvmats, "An .rvmat next to the colour map. Picked rows, or all of them"))
        maps.addWidget(self.preset)

        self.texture = QtWidgets.QLineEdit()
        self.rvmat = QtWidgets.QLineEdit()
        own = QtWidgets.QGroupBox("Paths written to the p3d")
        own_form = QtWidgets.QFormLayout(own)
        own_form.addRow("Texture", self.texture)
        own_form.addRow("Rvmat", self.rvmat)
        own_buttons = QtWidgets.QHBoxLayout()
        own_buttons.addWidget(_button("Set", self.set_paths, "The picked materials write these paths as they are, "
                                                             "whatever maps they have"))
        own_buttons.addWidget(_button("Automatic", self.clear_paths, "The picked materials take the paths from their maps again"))
        own_form.addRow(own_buttons)

        self.find = QtWidgets.QLineEdit()
        self.find.setPlaceholderText("find in paths, e.g. D:\\old\\")
        self.replacement = QtWidgets.QLineEdit()
        self.replacement.setPlaceholderText("replace with, e.g. P:\\mine\\")
        paths = QtWidgets.QHBoxLayout()
        paths.addWidget(self.find)
        paths.addWidget(self.replacement)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(_button("Replace in picked", lambda: self.replace(False), "In the texture paths of the picked rows"))
        buttons.addWidget(_button("Replace in all", lambda: self.replace(True), "In the texture paths of every listed material"))
        buttons.addWidget(_button("Select objects", self.select_objects, "Select the objects that use the picked materials"))

        form = QtWidgets.QFormLayout()
        form.addRow("Tex root", self.root)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(maps)
        layout.addWidget(own)
        layout.addLayout(paths)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        self.scan()

    def scan(self) -> None:
        before = self.picked()
        self.found = materials.scene_materials(self.selected_only.isChecked())
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for material in self.found:
            row = materials.describe(material, self.root.text())
            at = self.table.rowCount()
            self.table.insertRow(at)
            cells = (row["name"], row["type"], os.path.basename(row["diffuse"].replace("\\", "/")),
                     row["normal"] or "-", row["specular"] or "-", row["status"])
            for column, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(MAPS_TIP if column in (3, 4) else row["diffuse"])
                if column == len(cells) - 1:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(COLOURS[row["level"]])))
                self.table.setItem(at, column, item)
        self.table.resizeColumnsToContents()
        rows = QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
        for at, material in enumerate(self.found):
            if any(material == picked for picked in before):
                self.table.selectionModel().select(self.table.model().index(at, 0), rows)
        self.table.blockSignals(False)
        self.show_paths()

    def statuses(self) -> list:
        return [(self.table.item(row, 0).text(), self.table.item(row, 5).text()) for row in range(self.table.rowCount())]

    def picked(self) -> list:
        return [self.found[row] for row in sorted({index.row() for index in self.table.selectedIndexes()})]

    def confirm(self, question: str) -> bool:
        return QtWidgets.QMessageBox.question(self, "Materials", question) == QtWidgets.QMessageBox.Yes

    def show_paths(self) -> None:
        """The paths of the first picked material: its own, or greyed what its maps give"""
        chosen = self.picked()
        own = materials.arma_attributes(chosen[0]) if chosen else None
        auto = materials.derived(chosen[0], self.root.text()) if chosen and own is None else ("", "")
        for edit, value, hint in ((self.texture, own[0] if own else "", auto[0] and "from the maps: " + auto[0]),
                                  (self.rvmat, own[1] if own else "", auto[1] and "with Generate .rvmat: " + auto[1])):
            edit.setText(value)
            edit.setPlaceholderText(hint)

    def set_paths(self) -> int:
        chosen = self.picked()
        texture, path = self.texture.text().strip(), self.rvmat.text().strip()
        if not chosen:
            self.say("Materials: pick rows first")
            return 0
        if not texture and not path:
            self.say("Materials: fill Texture or Rvmat")
            return 0
        for material in chosen:
            materials.set_arma(material, texture, path)
        self.say("Materials: %d material(s) write these paths as they are" % len(chosen))
        self.scan()
        return len(chosen)

    def clear_paths(self) -> int:
        chosen = [material for material in self.picked() if materials.arma_attributes(material) is not None]
        if not chosen:
            self.say("Materials: none of the picked materials has paths of its own")
            return 0
        if not self.confirm("%d material(s) will take the paths from their maps again.\nFor a material imported from a p3d "
                            "that is the picture shown in the viewport, not the path of the file. Go on?" % len(chosen)):
            return 0
        for material in chosen:
            materials.clear_arma(material)
        self.say("Materials: %d material(s) take the paths from their maps" % len(chosen))
        self.scan()
        return len(chosen)

    def find_maps(self) -> dict:
        counts = materials.find_maps(self.picked() or self.found)
        note = "; %d lie there as .paa only, which 3ds Max can't show" % counts["paa_only"] if counts["paa_only"] else ""
        self.say("Materials: %d normal and %d specular map(s) put in%s" % (counts["normal"], counts["specular"], note))
        self.scan()
        return counts

    def write_rvmats(self) -> dict:
        chosen = self.picked() or self.found
        there = sum(1 for _material, path in materials.rvmat_files(chosen) if os.path.isfile(path))
        replace = bool(there) and self.confirm("%d .rvmat file(s) are there already. Replace them?\n"
                                               "No keeps them as they are." % there)
        done = materials.generate_rvmats(chosen, self.preset.currentText(), self.root.text(), replace)
        left = ", %d material(s) left out (no colour map, or paths of their own)" % done["skipped"] if done["skipped"] else ""
        self.say("Materials: %d .rvmat written (%s), %d kept%s" % (done["written"], self.preset.currentText(), done["kept"], left))
        for note in done["notes"]:
            self.say("  " + note)
        return done

    def replace(self, everything: bool) -> int:
        chosen = self.found if everything else self.picked()
        if not self.find.text():
            self.say("Materials: fill the find field")
            return 0
        if not chosen:
            self.say("Materials: pick rows first")
            return 0
        changed = materials.replace_paths(chosen, self.find.text(), self.replacement.text())
        self.say("Materials: %d texture path(s) changed" % changed)
        self.scan()
        return changed

    def select_objects(self) -> int:
        chosen = self.picked()
        if not chosen:
            self.say("Materials: pick rows first")
            return 0
        hits = materials.objects_using(chosen)
        if hits:
            rt.select(rt.Array(*hits))
        self.say("Materials: %d object(s) use the picked material(s)" % len(hits))
        return len(hits)

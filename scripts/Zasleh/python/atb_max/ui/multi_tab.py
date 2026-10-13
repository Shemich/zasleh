import os

import pymxs
from PySide2 import QtWidgets

from .. import multistruct, settings

rt = pymxs.runtime


class MultiTab(QtWidgets.QWidget):
    def __init__(self, say, export_options):
        super().__init__()
        self.say = say
        self.export_options = export_options        # the options of the Model tab
        self.parts = multistruct.Parts()

        self.prefix = QtWidgets.QLineEdit("pos_")
        self.prefix.setToolTip("Memory point of a part: this prefix + the part's name")
        self.prefix.editingFinished.connect(self.prefix_changed)
        self.list = QtWidgets.QListWidget()
        self.list.setToolTip("Parts: object -> memory point [class]")
        self.list.currentRowChanged.connect(self.row_changed)
        self.cls = QtWidgets.QLineEdit()
        self.cls.setPlaceholderText("class of the picked part")
        self.mass = QtWidgets.QDoubleSpinBox()
        self.mass.setRange(0.0, 1e8)
        self.mass.setSuffix(" kg")
        self.mass.setToolTip("Geometry mass of the picked part (0: the common value below)")

        def row(*widgets):
            line = QtWidgets.QHBoxLayout()
            for widget in widgets:
                line.addWidget(widget, 1 if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QListWidget)) else 0)
            return line

        self.autocenter = QtWidgets.QCheckBox("Set autocenter = 0")
        self.autocenter.setChecked(True)
        self.autocenter.setToolTip("Needed for the parts to line up: with autocenter=1 the engine re-centres each part")
        self.geometry = QtWidgets.QCheckBox("Include Geometry LOD")
        self.geometry.setToolTip("From the objects of the Geometry layer named <part> or <part>_...")
        self.geo_props = QtWidgets.QLineEdit()
        self.geo_props.setPlaceholderText("Geometry properties: class=house; sbsource=shadowvolume")
        self.mass_all = QtWidgets.QDoubleSpinBox()
        self.mass_all.setRange(0.0, 1e8)
        self.mass_all.setSuffix(" kg")
        self.mass_all.setToolTip("Geometry mass of every part that has none of its own (0: keep what the objects have)")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(row(QtWidgets.QLabel("Point prefix"), self.prefix))
        layout.addWidget(self.list, 1)
        layout.addLayout(row(self.button("Add selected", self.add_selected, "Add the selected objects as parts"),
                             self.button("Remove", self.remove, "Take the picked part off the list"),
                             self.button("Clear", self.clear, "Empty the list")))
        layout.addLayout(row(self.cls, self.mass, self.button("Set", self.set_part, "Class and mass of the picked part")))
        layout.addLayout(row(self.button("Build points", self.build_points, "Memory point pos_<name> at every part's centre"),
                             self.button("Centre", self.centre, "Move the picked part to the origin, as it is exported"),
                             self.button("Restore", self.restore, "Move it back to its memory point")))
        layout.addWidget(self.autocenter)
        layout.addWidget(self.geometry)
        layout.addWidget(self.geo_props)
        layout.addLayout(row(QtWidgets.QLabel("Mass, all parts"), self.mass_all))
        layout.addLayout(row(self.button("Verify", self.verify, "Check the points and the autocenter risk; see the log"),
                             self.button("Config line", self.cfg_line, "multiStructureParts[] to the clipboard"),
                             self.button("Export parts...", self.pick_export, "One p3d per part, with the Model tab's options")))

    def button(self, text, slot, tip):
        button = QtWidgets.QPushButton(text)
        button.setToolTip(tip)
        button.clicked.connect(lambda _checked=False: slot())
        return button

    def refresh(self) -> None:
        self.parts = multistruct.Parts.load()
        self.prefix.setText(self.parts.prefix)
        self.fill()

    def fill(self) -> None:
        at = self.list.currentRow()
        self.list.clear()
        for part in self.parts.items:
            text = "%s  ->  %s   [%s]" % (part.node.name, self.parts.point_name(part), part.cls)
            self.list.addItem(text + ("   %g kg" % part.mass if part.mass > 0 else ""))
        if 0 <= at < self.list.count():
            self.list.setCurrentRow(at)

    def changed(self) -> None:
        self.parts.save()
        self.fill()

    def current(self):
        at = self.list.currentRow()
        return self.parts.items[at] if 0 <= at < len(self.parts.items) else None

    def row_changed(self, _row) -> None:
        part = self.current()
        if part is not None:
            self.cls.setText(part.cls)
            self.mass.setValue(part.mass)

    def prefix_changed(self) -> None:
        self.parts.prefix = self.prefix.text().strip()
        self.changed()

    def add_selected(self) -> None:
        added = self.parts.add_selected()
        self.say("Multi-structure: %d part(s) added" % added if added else "Multi-structure: select geometry that is not a part yet")
        self.changed()

    def remove(self) -> None:
        part = self.current()
        if part is not None:
            self.parts.items.remove(part)
            self.changed()

    def clear(self) -> None:
        self.parts.items = []
        self.changed()

    def set_part(self) -> None:
        part = self.current()
        if part is not None:
            part.cls = self.cls.text().strip() or str(part.node.name)
            part.mass = self.mass.value()
            self.changed()

    def build_points(self) -> None:
        self.say("Multi-structure: %d memory point(s) on the Memory layer" % multistruct.build_points(self.parts))

    def centre(self) -> None:
        part = self.current()
        if part is not None:
            multistruct.centre(part)
            rt.redrawViews()

    def restore(self) -> None:
        part = self.current()
        if part is not None and not multistruct.restore(self.parts, part):
            self.say("Multi-structure: no memory point for this part yet - build the points first")
        rt.redrawViews()

    def verify(self) -> None:
        self.say("\n".join(["Multi-structure check:"] + multistruct.verify(self.parts)))

    def cfg_line(self) -> str:
        line = self.parts.cfg_line()
        QtWidgets.QApplication.clipboard().setText(line)
        self.say(line)
        return line

    def export_to(self, folder: str) -> dict:
        report = multistruct.export_parts(self.parts, folder, self.export_options(), self.autocenter.isChecked(),
                                          self.geometry.isChecked(), self.geo_props.text(), self.mass_all.value())
        lines = ["Multi-structure: %d part(s) written to %s, %d failed" % (len(report["ok"]), folder, len(report["failed"]))]
        lines += ["  failed - " + line for line in report["failed"]]
        if report["no_geometry"]:
            lines.append("  no Geometry-layer objects for: " + ", ".join(report["no_geometry"]))
        lines += ["  " + note for note in report["notes"]]
        self.say("\n".join(lines))
        return report

    def pick_export(self) -> None:
        if not self.parts.items:
            self.say("Multi-structure: the part list is empty")
            return
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder for the part p3d files", settings.get("lastDir"))
        if folder:
            settings.put("lastDir", folder)
            self.export_to(os.path.normpath(folder))

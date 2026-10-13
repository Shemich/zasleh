import pymxs
from PySide2 import QtCore, QtWidgets

from .. import hitpoints, reader
from .. import registry as reg

rt = pymxs.runtime
COLUMNS = ("Selection", "Points", "Radius")
OTHERS = "(all other points)"
ASK_FROM = 20000


class HitPointsTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setToolTip("Selections of the HitPoints LOD, with the radius of their hit point if one is set")

        self.name = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("selection of the new points; empty: the object's name")
        self.spacing = [QtWidgets.QDoubleSpinBox() for _axis in "xyz"]
        cloud_row = QtWidgets.QHBoxLayout()
        for box, axis in zip(self.spacing, "XYZ"):
            box.setRange(0.01, 100.0)
            box.setDecimals(2)
            box.setSingleStep(0.05)
            box.setValue(0.2)
            box.setPrefix(axis + " ")
            box.setToolTip("Distance between the points along %s of the object" % axis)
            cloud_row.addWidget(box)
        fill = QtWidgets.QPushButton("Fill object")
        fill.setToolTip("Points on a grid inside the selected closed objects, as one selection of the HitPoints LOD")
        fill.clicked.connect(lambda _checked=False: self.fill())
        cloud_row.addWidget(fill)
        self.pieces = QtWidgets.QCheckBox("Each piece on its own grid")
        self.pieces.setChecked(True)
        self.pieces.setToolTip("An object put together from several closed pieces: every piece is filled along its own sides,\n"
                               "with the same room left on all of them. Off: one grid along the axes of the object")
        cloud_box = QtWidgets.QGroupBox("Point cloud")
        cloud = QtWidgets.QVBoxLayout(cloud_box)
        cloud.addWidget(self.name)
        cloud.addLayout(cloud_row)
        cloud.addWidget(self.pieces)

        self.radius = QtWidgets.QDoubleSpinBox()
        self.radius.setRange(0.0, 100.0)
        self.radius.setDecimals(3)
        self.radius.setSingleStep(0.05)
        self.radius.setValue(0.15)
        self.radius.setToolTip("How far a hit point reaches: radius of its class in the config. 0 takes the radius away")
        set_button = QtWidgets.QPushButton("Set")
        set_button.setToolTip("Give this radius to the picked selections; with none picked, to all points that have no radius of their own")
        set_button.clicked.connect(lambda _checked=False: self.set_radius())
        load = QtWidgets.QPushButton("From config...")
        load.setToolTip("Read a config.cpp: every hit point class with a name and a radius gives its radius to that selection")
        load.clicked.connect(lambda _checked=False: self.pick_config())
        self.show_button = QtWidgets.QPushButton("Show")
        self.show_button.setCheckable(True)
        self.show_button.setToolTip("Draw a sphere of its radius around every hit point. For the eye only: not exported")
        self.show_button.toggled.connect(self.show_toggled)
        radius_row = QtWidgets.QHBoxLayout()
        radius_row.addWidget(self.radius, 1)
        for button in (set_button, load, self.show_button):
            radius_row.addWidget(button)
        radius_box = QtWidgets.QGroupBox("Radius")
        QtWidgets.QVBoxLayout(radius_box).addLayout(radius_row)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(cloud_box)
        layout.addWidget(radius_box)

    def confirm(self, question: str) -> bool:
        return QtWidgets.QMessageBox.question(self, "Hit points", question) == QtWidgets.QMessageBox.Yes

    def rows(self) -> list:
        return [tuple(self.table.item(row, column).text() for column in range(len(COLUMNS))) for row in range(self.table.rowCount())]

    def picked(self) -> list:
        """Names of the picked selections (OTHERS left out)"""
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [self.table.item(row, 0).text() for row in rows if self.table.item(row, 0).text() != OTHERS]

    def refresh(self) -> None:
        try:
            found = hitpoints.selections()
            known = hitpoints.radii()
        except (reader.SceneError, reg.OldScene) as error:
            self.say("Hit points: %s" % error)
            found, known = [], {}
        before = set(self.picked())
        self.table.setRowCount(0)
        listed = sorted(found, key=lambda row: row[0].lower()) + ([(OTHERS, "")] if hitpoints.ANY in known else [])
        for name, count in listed:
            at = self.table.rowCount()
            self.table.insertRow(at)
            radius = known.get(hitpoints.ANY if name == OTHERS else name.lower())
            for column, text in enumerate((name, str(count), "%g" % radius if radius else "")):
                self.table.setItem(at, column, QtWidgets.QTableWidgetItem(text))
            if name in before:
                self.table.selectionModel().select(self.table.model().index(at, 0),
                                                   QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        self.table.resizeColumnsToContents()
        self.show_button.blockSignals(True)
        self.show_button.setChecked(hitpoints.shown())
        self.show_button.blockSignals(False)

    def fill(self) -> int:
        sources = [node for node in rt.selection if rt.superClassOf(node) == rt.GeometryClass]
        try:
            if not sources:
                raise hitpoints.HitPointError("Select the closed object to fill with points.")
            found, skipped, pieces = [], 0, 0
            for source in sources:
                inside, holes, count = hitpoints.cloud(source, [box.value() for box in self.spacing], self.pieces.isChecked())
                found += inside
                skipped += holes
                pieces += count
            what = str(sources[0].name) if len(sources) == 1 else "%d objects" % len(sources)
            if not found:
                raise hitpoints.HitPointError("No grid point is inside %s: is it closed? Try a smaller spacing." % what)
            if len(found) > ASK_FROM and not self.confirm("%d points would be made. Go on?" % len(found)):
                return 0
            name = self.name.text().strip() or str(sources[0].name)
            hitpoints.make_cloud(found, name)
        except hitpoints.HitPointError as error:
            self.say("Hit points: %s" % error)
            return 0
        note = "; %d line(s) of the grid skipped, the mesh is not closed there" % skipped if skipped else ""
        self.say("Hit points: %d point(s) inside %s (%d piece(s)), selection %s%s" % (len(found), what, pieces, name, note))
        self.refresh()
        return len(found)

    def set_radius(self) -> None:
        names = self.picked()
        hitpoints.set_radii({name: self.radius.value() for name in (names or [hitpoints.ANY])})
        self.say("Hit points: radius %g for %s" % (self.radius.value(), ", ".join(names) if names else "all points without their own"))
        self.refresh()

    def load_radii(self, path: str) -> list:
        try:
            with open(path, encoding="utf-8", errors="replace") as stream:
                done = hitpoints.radii_from_config(stream.read())
        except OSError as error:
            self.say("Hit points: %s" % error)
            return []
        self.say("Hit points: radius taken from %s for %s" % (path, ", ".join(done)) if done else
                 "Hit points: no hit point class of %s names a selection of this LOD with a radius" % path)
        self.refresh()
        return done

    def pick_config(self) -> None:
        path, _kind = QtWidgets.QFileDialog.getOpenFileName(self, "Config with the hit points", "",
                                                            "Config (*.cpp *.hpp *.cfg);;All files (*.*)")
        if path:
            self.load_radii(path)

    def show_toggled(self, on: bool) -> None:
        try:
            made = hitpoints.show(on)
        except hitpoints.HitPointError as error:
            self.say("Hit points: %s" % error)
            made = 0
        if on:
            self.say("Hit points: %d sphere(s) drawn" % made if made else
                     "Hit points: nothing to draw - no selection has a radius yet (Set, or From config...)")
        self.refresh()

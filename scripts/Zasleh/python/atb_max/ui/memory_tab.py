import pymxs
from PySide2 import QtWidgets

import atb_p3d

from .. import exporter, memory
from ..scene import layer_resolution

rt = pymxs.runtime


class MemoryTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say
        self.rows = []              # (node, names) per list row
        self.filling = False

        self.layer = QtWidgets.QComboBox()
        self.layer.setToolTip("The point LOD to work on")
        self.layer.currentIndexChanged.connect(lambda _index: self.refresh())
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list.setToolTip("Memory points. Picking them here selects them in the scene")
        self.list.itemSelectionChanged.connect(self.list_picked)
        self.list.itemDoubleClicked.connect(lambda _item: self.do("rename"))

        self.name = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("point name, e.g. pos_driver")
        self.size = QtWidgets.QDoubleSpinBox()
        self.size.setRange(1.0, 200.0)
        self.size.setValue(10.0)
        self.size.setToolTip("Size of the markers")
        self.size.valueChanged.connect(lambda value: memory.set_size(value, self.layer_name()))
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(self.name, 1)
        name_row.addWidget(QtWidgets.QLabel("Size"))
        name_row.addWidget(self.size)

        grid = QtWidgets.QGridLayout()
        buttons = (("At centre", "centre", "One point in the middle of the picked verts or selected objects"),
                   ("At verts", "verts", "A point on every picked vert"),
                   ("Place...", "place", "Click in the viewport to place points; right click ends"),
                   ("Rename", "rename", "Give the picked points the name typed above (several names: a, b)"),
                   ("Make axis", "axis", "Two picked points get the name typed above"),
                   ("Delete", "delete", "Delete the picked points"))
        for at, (text, action, tip) in enumerate(buttons):
            button = QtWidgets.QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, a=action: self.do(a))
            grid.addWidget(button, at // 3, at % 3)

        self.hide_points = self.toggle("Hide points", lambda on: memory.view(hide_points=on))
        self.hide_geometry = self.toggle("Hide geometry", lambda on: memory.view(hide_geometry=on))
        self.xray = self.toggle("X-ray", lambda on: memory.view(xray=on), "See the points through the geometry")
        view_row = QtWidgets.QHBoxLayout()
        for button in (self.hide_points, self.hide_geometry, self.xray):
            view_row.addWidget(button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.layer)
        layout.addWidget(self.list, 1)
        layout.addLayout(name_row)
        layout.addLayout(grid)
        layout.addLayout(view_row)

    def toggle(self, text, slot, tip=""):
        button = QtWidgets.QPushButton(text)
        button.setCheckable(True)
        button.setToolTip(tip)
        button.toggled.connect(slot)
        return button

    def layer_name(self) -> str:
        return self.layer.currentText() or memory.DEFAULT_LAYER

    def picked(self) -> list:
        return [self.rows[index.row()][0] for index in self.list.selectedIndexes()]

    def refresh(self) -> None:
        if self.filling:
            return
        self.filling = True
        current = self.layer_name()
        names = [memory.DEFAULT_LAYER]
        for candidate in exporter.candidate_layers(include_empty=True):
            found = rt.LayerManager.getLayerFromName(candidate["layer"])
            resolution = layer_resolution(found)
            if resolution is not None and atb_p3d.is_point_lod(resolution) and candidate["layer"] not in names:
                names.append(candidate["layer"])
        self.layer.blockSignals(True)
        self.layer.clear()
        self.layer.addItems(names)
        self.layer.setCurrentIndex(names.index(current) if current in names else 0)
        self.layer.blockSignals(False)

        selected = {int(rt.getHandleByAnim(node)) for node in rt.selection}
        found = memory.points(self.layer_name())
        self.rows = [(node, names) for node, names, _position in found]
        self.list.clear()
        for node, names, position in found:
            item = QtWidgets.QListWidgetItem(", ".join(names) or "(no name)")
            item.setToolTip("%.3f, %.3f, %.3f" % position)
            self.list.addItem(item)
            item.setSelected(int(rt.getHandleByAnim(node)) in selected)
        self.filling = False

    def list_picked(self) -> None:
        if self.filling:
            return
        self.filling = True                     # our own scene selection comes back as a callback
        memory.select(self.picked())
        self.filling = False
        picked = self.list.selectedItems()
        if len(picked) == 1 and picked[0].text() != "(no name)":
            self.name.setText(picked[0].text())

    def confirm(self, question: str) -> bool:
        return QtWidgets.QMessageBox.question(self, "Memory points", question) == QtWidgets.QMessageBox.Yes

    def do(self, action: str) -> None:
        name = self.name.text().strip()
        layer = self.layer_name()
        picked = self.picked()
        try:
            if action == "centre":
                memory.add_at_centre(name, layer)
                self.say("Memory: a point at the centre of the selection")
            elif action == "verts":
                self.say("Memory: %d point(s) added" % len(memory.add_at_verts(name, layer)))
            elif action == "place":
                self.say("Memory: click in the viewport to place points, right click to finish")
                memory.place(name, layer, self.refresh)
            elif action == "rename":
                if not picked:
                    raise memory.MemoryError_("Pick the points to rename in the list.")
                for node in picked:
                    memory.set_names(node, name.split(","))
                self.say("Memory: %d point(s) renamed" % len(picked))
            elif action == "axis":
                memory.make_axis(picked, name)
                self.say("Memory: axis %s" % name)
            elif action == "delete":
                if picked and self.confirm("Delete %d memory point(s)?" % len(picked)):
                    self.say("Memory: %d point(s) deleted" % memory.delete(picked))
        except memory.MemoryError_ as error:
            self.say(str(error))
        self.refresh()

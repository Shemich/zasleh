import os

import pymxs
from PySide2 import QtCore, QtWidgets

from zasleh.formats import modelcfg
from zasleh.formats.modelcfg import Animation, ModelCfg

from .. import parts, settings, skeleton
from .. import registry as reg

rt = pymxs.runtime

COLUMNS = ("name", "type", "source", "selection", "axis", "memory", "min", "max", "from", "to")
NAME, TYPE, SOURCE, SELECTION, AXIS, MEMORY, MIN, MAX, FROM, TO = range(10)
CFG_FILTER = "model.cfg (*.cfg);;All files (*.*)"
SOURCES = ("user", "time", "damage", "hit", "reload", "revolving", "ammo", "isSelected", "hasOptics", "mainTurret",
           "mainGun", "obsTurret", "obsGun", "wheel", "wheelL", "wheelR", "drivingWheel", "damper", "door", "gear",
           "rotor", "rotorH", "rotorV", "speed", "rpm", "fuel", "altRadar", "horizonBank", "horizonDive", "recoil")


class Names(QtWidgets.QStyledItemDelegate):
    """Offers names while a cell is typed"""

    def __init__(self, parent, names):
        super().__init__(parent)
        self.names = names              # a function giving the list

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        completer = QtWidgets.QCompleter(list(self.names()), editor)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchContains)
        editor.setCompleter(completer)
        return editor


def range_keys(kind: str) -> tuple:
    """Which properties the from / to columns stand for"""
    kind = kind.lower()
    if kind.startswith("rotation"):
        return "angle0", "angle1"
    if kind.startswith("translation"):
        return "offset0", "offset1"
    if kind == "hide":
        return "hideValue", "unHideValue"
    return "", ""


class ConfigTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say

        self.model = QtWidgets.QLineEdit()
        self.skeleton = QtWidgets.QLineEdit()
        names = QtWidgets.QFormLayout()
        names.addRow("Model class", self.model)
        names.addRow("Skeleton class", self.skeleton)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.setToolTip("Bones. Drag one onto another to make it its child; double click to rename")
        bone_buttons = QtWidgets.QGridLayout()
        for at, (text, slot, tip) in enumerate((
                ("From selections", self.from_selections, "Add the scene's selections that are not bones yet"),
                ("From links", self.from_links, "Take bones and parents from the linked objects of the scene"),
                ("To scene", self.to_scene, "The selection of every bone becomes an object of its own, linked to the object "
                                            "of its parent bone.\nAn export joins the objects again"),
                ("Add", self.add_bone, "A new bone under the picked one"),
                ("Remove", self.remove_bones, "Remove the picked bones; their children move up"))):
            bone_buttons.addWidget(self.button(text, slot, tip), at // 3, at % 3)
        bones_box = QtWidgets.QGroupBox("Skeleton")
        box = QtWidgets.QVBoxLayout(bones_box)
        box.addWidget(self.tree, 1)
        box.addLayout(bone_buttons)

        self.sections = QtWidgets.QPlainTextEdit()
        self.sections.setPlaceholderText("sections, one per line: camo1, zasleh ...")
        self.sections.setMaximumHeight(70)

        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.memory_names: list = []
        self.table.setItemDelegateForColumn(SOURCE, Names(self.table, lambda: SOURCES))
        self.table.setItemDelegateForColumn(SELECTION, Names(self.table, lambda: [name for name, _parent in self.bones()]))
        self.table.setItemDelegateForColumn(AXIS, Names(self.table, lambda: self.memory_names))
        self.table.horizontalHeaderItem(FROM).setToolTip("angle0 / offset0 / hideValue, by type")
        self.table.horizontalHeaderItem(TO).setToolTip("angle1 / offset1 / unHideValue, by type")
        animation_buttons = QtWidgets.QHBoxLayout()
        animation_buttons.addWidget(self.button("Add", lambda: self.add_animation(Animation("NewAnimation")), "A new animation"))
        animation_buttons.addWidget(self.button("Remove", self.remove_animations, "Remove the picked animations"))
        animation_buttons.addStretch(1)
        animations_box = QtWidgets.QGroupBox("Animations")
        box = QtWidgets.QVBoxLayout(animations_box)
        box.addWidget(self.table, 1)
        box.addLayout(animation_buttons)

        file_buttons = QtWidgets.QHBoxLayout()
        file_buttons.addWidget(self.button("Load...", self.pick_load, "Read a model.cfg"))
        file_buttons.addWidget(self.button("Preview", self.preview, "Show the model.cfg in the log below"))
        file_buttons.addWidget(self.button("Save...", self.pick_save, "Write the model.cfg"))

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(names)
        layout.addWidget(bones_box, 3)
        layout.addWidget(self.sections)
        layout.addWidget(animations_box, 2)
        layout.addLayout(file_buttons)

    def button(self, text, slot, tip):
        button = QtWidgets.QPushButton(text)
        button.setToolTip(tip)
        button.clicked.connect(lambda _checked=False: slot())
        return button

    def refresh(self) -> None:
        if not self.model.text():
            self.model.setText(skeleton.model_name())
        if not self.skeleton.text():
            self.skeleton.setText(self.model.text() + "_skeleton")
        self.memory_names = skeleton.scene_names()[1]

    # -- bones

    def _item(self, name: str) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem([name])
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        return item

    def _walk(self, parent=None):
        root = self.tree.invisibleRootItem() if parent is None else parent
        for i in range(root.childCount()):
            child = root.child(i)
            yield child, ("" if parent is None else parent.text(0))
            yield from self._walk(child)

    def bones(self) -> list:
        return [(item.text(0).strip(), parent) for item, parent in self._walk() if item.text(0).strip()]

    def set_bones(self, pairs) -> None:
        self.tree.clear()
        items = {}
        pairs = modelcfg.sorted_bones(list(pairs))
        for name, _parent in pairs:
            items.setdefault(name.lower(), self._item(name))
        for name, parent in pairs:
            holder = items.get(parent.lower()) if parent else None
            if holder is None or holder is items[name.lower()]:
                self.tree.addTopLevelItem(items[name.lower()])
            else:
                holder.addChild(items[name.lower()])
        self.tree.expandAll()

    def from_selections(self) -> None:
        names, _memory = skeleton.scene_names()
        have = {name.lower() for name, _parent in self.bones()}
        fresh = [name for name in names if name.lower() not in have]
        self.set_bones(self.bones() + [(name, "") for name in fresh])
        self.say("model.cfg: %d bone(s) added from the scene's selections" % len(fresh))

    def from_links(self) -> None:
        pairs = skeleton.bones_from_links()
        if not pairs:
            self.say("model.cfg: no linked objects in the scene")
            return
        self.set_bones(pairs)
        self.say("model.cfg: %d bone(s) from the linked objects" % len(pairs))

    def to_scene(self) -> int:
        bones = self.bones()
        if not bones:
            self.say("model.cfg: there are no bones to lay out")
            return 0
        try:
            made, links = parts.by_bones(bones)
        except reg.OldScene as error:
            self.say("model.cfg: %s" % error)
            return 0
        count = sum(made.values())
        if not count and not links:
            self.say("model.cfg: no bone has faces of its own in the scene (or the objects are there already)")
        else:
            self.say("model.cfg: %d object(s) made of the bones' selections, %d link(s)" % (count, links))
        rt.redrawViews()
        return count

    def add_bone(self) -> None:
        item = self._item("new_bone")
        picked = self.tree.currentItem()
        if picked is not None:
            picked.addChild(item)
            picked.setExpanded(True)
        else:
            self.tree.addTopLevelItem(item)
        self.tree.setCurrentItem(item)

    def remove_bones(self) -> None:
        for item in self.tree.selectedItems():
            holder = item.parent() or self.tree.invisibleRootItem()
            at = holder.indexOfChild(item)
            children = item.takeChildren()
            holder.takeChild(at)
            holder.insertChildren(at, children)

    # -- animations

    def add_animation(self, animation: Animation) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        kind = QtWidgets.QComboBox()
        kind.addItems(modelcfg.ANIMATION_TYPES)
        kind.setEditable(True)
        kind.setCurrentText(animation.type)
        memory = QtWidgets.QCheckBox()
        memory.setChecked(animation.memory)
        self.table.setCellWidget(row, TYPE, kind)
        self.table.setCellWidget(row, MEMORY, memory)
        extra = dict(animation.extra)
        low, high = range_keys(animation.type)
        cells = {NAME: animation.name, SOURCE: animation.source, SELECTION: animation.selection, AXIS: animation.axis,
                 MIN: "%g" % animation.min_value, MAX: "%g" % animation.max_value,
                 FROM: extra.pop(low, "") if low else "", TO: extra.pop(high, "") if high else ""}
        for column, text in cells.items():
            self.table.setItem(row, column, QtWidgets.QTableWidgetItem(text))
        self.table.item(row, NAME).setData(QtCore.Qt.UserRole, extra)      # what has no column of its own
        return row

    def remove_animations(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def animations(self) -> list:
        found = []
        for row in range(self.table.rowCount()):
            text = lambda column: (self.table.item(row, column).text().strip() if self.table.item(row, column) else "")  # noqa: E731
            if not text(NAME):
                continue
            kind = self.table.cellWidget(row, TYPE).currentText().strip()
            extra = dict(self.table.item(row, NAME).data(QtCore.Qt.UserRole) or {})
            animation = Animation(text(NAME), kind, text(SOURCE), text(SELECTION), text(AXIS),
                                  self.table.cellWidget(row, MEMORY).isChecked())
            for column, target, key in ((MIN, "min_value", "minValue"), (MAX, "max_value", "maxValue")):
                try:
                    setattr(animation, target, float(text(column) or 0.0))
                except ValueError:                      # "rad 90" and the like
                    extra[key] = text(column)
            low, high = range_keys(kind)
            ranged = {}
            if low and text(FROM):
                ranged[low] = text(FROM)
            if high and text(TO):
                ranged[high] = text(TO)
            animation.extra = {**ranged, **extra}
            found.append(animation)
        return found

    # -- the whole thing

    def collect(self) -> ModelCfg:
        sections = [line.strip() for line in self.sections.toPlainText().replace(",", "\n").split("\n") if line.strip()]
        return ModelCfg(model=self.model.text().strip(), skeleton=self.skeleton.text().strip(), bones=self.bones(),
                        sections=sections, animations=self.animations())

    def fill(self, cfg: ModelCfg) -> None:
        self.model.setText(cfg.model)
        self.skeleton.setText(cfg.skeleton)
        self.set_bones(cfg.bones)
        self.sections.setPlainText("\n".join(cfg.sections))
        self.table.setRowCount(0)
        for animation in cfg.animations:
            self.add_animation(animation)

    def preview(self) -> str:
        text = modelcfg.generate(self.collect())
        self.say(text)
        return text

    def save_file(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8", newline="\r\n") as stream:
                stream.write(modelcfg.generate(self.collect()))
        except OSError as error:
            self.say("model.cfg not saved: %s" % error)
            return False
        self.say("model.cfg saved: %s" % path)
        return True

    def load_file(self, path: str) -> bool:
        try:
            with open(path, encoding="utf-8", errors="replace") as stream:
                found = modelcfg.parse(stream.read())
        except (OSError, modelcfg.CfgError) as error:
            self.say("model.cfg not read: %s" % error)
            return False
        if not found:
            self.say("model.cfg: no models or skeletons in %s" % path)
            return False
        chosen = found[0]
        if len(found) > 1:
            name = self.choose([cfg.model or cfg.skeleton for cfg in found])
            if not name:
                return False
            chosen = next(cfg for cfg in found if (cfg.model or cfg.skeleton) == name)
        self.fill(chosen)
        self.say("model.cfg read: %s%s" % (path, "" if len(found) == 1 else " (%s, one of %d)" % (chosen.model, len(found))))
        return True

    def choose(self, names: list) -> str:
        name, ok = QtWidgets.QInputDialog.getItem(self, "model.cfg", "Model:", names, 0, False)
        return name if ok else ""

    def pick_load(self) -> None:
        path, _kind = QtWidgets.QFileDialog.getOpenFileName(self, "Load model.cfg", settings.get("lastDir"), CFG_FILTER)
        if path:
            self.load_file(os.path.normpath(path))

    def pick_save(self) -> None:
        start = os.path.join(settings.get("lastDir"), "model.cfg")
        path, _kind = QtWidgets.QFileDialog.getSaveFileName(self, "Save model.cfg", start, CFG_FILTER)
        if path:
            self.save_file(os.path.normpath(path))

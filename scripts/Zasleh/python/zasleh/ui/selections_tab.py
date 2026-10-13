import os

import pymxs
from PySide2 import QtCore, QtGui, QtWidgets

from zasleh.formats import namesets

from .. import selections, settings
from .. import registry as reg

rt = pymxs.runtime
NO_OBJECT = "Object: (select one Editable Poly)"
NO_SET = "(no name set)"


def name_sets_folder() -> str:
    return os.path.join(str(rt.getDir(rt.Name("scripts"))), "Zasleh", "data", "NameSets")


def known_names(name_set: str = "") -> list:
    """Names to offer while typing: the scene's selections and those of the chosen name set"""
    names = {name for name, _what in namesets.read(name_sets_folder(), name_set)} if name_set else set()
    try:
        registry = reg.Registry.load()
        names.update(registry.names)
        names.update(n for n, e in registry.slots.items() if e["kind"] == reg.WEIGHTED)
    except reg.OldScene:
        pass
    return sorted((n for n in names if n and not n.startswith("#")), key=str.lower)


class SelectionsTab(QtWidgets.QWidget):
    def __init__(self, say):
        super().__init__()
        self.say = say
        self.names = []             # the object's selections: the first rows of the list
        self.offered = []           # then the ones of the name set it doesn't have yet

        self.object_label = QtWidgets.QLabel(NO_OBJECT)
        self.name_set = QtWidgets.QComboBox()
        self.name_set.setToolTip("The selections a model of this kind usually has. Those the object lacks are listed in grey:\n"
                                 "pick verts or polys and double click one to assign them. The sets are text files, "
                                 "see the list's menu")
        self.fill_name_sets()
        self.name_set.currentTextChanged.connect(self.name_set_chosen)
        self.list = QtWidgets.QListWidget()
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.open_menu)
        self.list.itemClicked.connect(self.item_clicked)
        self.list.itemDoubleClicked.connect(self.item_double_clicked)

        self.name = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("selection name")
        self.completer = QtWidgets.QCompleter([], self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.setFilterMode(QtCore.Qt.MatchContains)
        self.name.setCompleter(self.completer)

        self.texture = QtWidgets.QLineEdit()
        self.texture.setPlaceholderText("texture of its faces, e.g. proj\\data\\hull_co.paa")
        self.rvmat = QtWidgets.QLineEdit()
        self.rvmat.setPlaceholderText("material of its faces, e.g. proj\\data\\hull.rvmat")
        for edit in (self.texture, self.rvmat):
            edit.setToolTip("What the faces of the picked selection carry, as the p3d names it.\n"
                            "Type other paths and press Set to give them to these faces")
        self.weight = QtWidgets.QDoubleSpinBox()
        self.weight.setRange(0.0, 1.0)
        self.weight.setSingleStep(0.05)
        self.weight.setValue(1.0)
        self.mass = QtWidgets.QDoubleSpinBox()
        self.mass.setRange(0.0, 1e7)
        self.mass.setDecimals(1)
        self.mass.setSuffix(" kg")

        self.colour = self.button("Show in colour", None, "Paint the selection on the mesh: grey outside, blue to red by weight")
        self.colour.setCheckable(True)
        self.colour.toggled.connect(self.colour_toggled)
        self.status = QtWidgets.QLabel("Right click the list: New, Delete, Rename, Redefine, Refresh")
        self.status.setWordWrap(True)

        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(self.object_label, 1)
        top_row.addWidget(self.name_set)
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(self.name, 1)
        name_row.addWidget(QtWidgets.QLabel("Weight"))
        name_row.addWidget(self.weight)

        faces_row = QtWidgets.QHBoxLayout()
        faces_row.addWidget(self.texture, 1)
        faces_row.addWidget(self.rvmat, 1)
        set_button = self.button("Set", None, "Give this texture and this .rvmat to the faces of the selection")
        set_button.clicked.connect(lambda _checked=False: self.set_faces())
        faces_row.addWidget(set_button)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(self.button("Assign", "assign", "Put the picked verts / polys (or the whole object) into the selection"), 0, 0)
        grid.addWidget(self.button("Remove", "remove", "Take the picked verts / polys out of the selection"), 0, 1)
        grid.addWidget(self.button("Select", "select", "Select its verts and polys. Ctrl adds to the current selection, Alt subtracts"), 0, 2)
        grid.addWidget(self.button("Find components", "components", "Every separate piece of the mesh becomes ComponentNN"), 1, 0)
        grid.addWidget(self.button("Check", "check", "Look for verts and polys that fell out of their selections"), 1, 1)
        grid.addWidget(self.button("Ungrouped", "ungrouped", "Select the verts that are in no selection"), 1, 2)
        grid.addWidget(self.colour, 2, 0, 1, 2)
        grid.addWidget(self.button("Undo", "undo", "Take back the last change made here (Ctrl+Z does not see these)"), 2, 2)

        mass_row = QtWidgets.QHBoxLayout()
        mass_row.addWidget(QtWidgets.QLabel("Mass"))
        mass_row.addWidget(self.mass, 1)
        mass_row.addWidget(self.button("Set", "mass_set", "Spread this mass over the picked verts (the whole object at object level)"))
        mass_row.addWidget(self.button("Get", "mass_get", "Mass of the picked verts"))

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.list, 1)
        layout.addLayout(name_row)
        layout.addLayout(faces_row)
        layout.addLayout(grid)
        layout.addLayout(mass_row)
        layout.addWidget(self.status)

    def button(self, text, action, tip):
        button = QtWidgets.QPushButton(text)
        button.setToolTip(tip)
        if action:
            button.clicked.connect(lambda _checked=False: self.do(action))
        return button

    # -- name sets

    def fill_name_sets(self) -> None:
        chosen = settings.get("nameSet")
        self.name_set.blockSignals(True)
        self.name_set.clear()
        self.name_set.addItems([NO_SET] + namesets.available(name_sets_folder()))
        self.name_set.setCurrentText(chosen if self.name_set.findText(chosen) >= 0 else NO_SET)
        self.name_set.blockSignals(False)

    def chosen_set(self) -> str:
        return "" if self.name_set.currentIndex() <= 0 else self.name_set.currentText()

    def name_set_chosen(self, _text: str) -> None:
        settings.put("nameSet", self.chosen_set())
        self.refresh()

    # -- actions

    def current(self) -> str:
        """The picked selection of the object; nothing while a grey row is picked"""
        row = self.list.currentRow()
        return self.names[row] if 0 <= row < len(self.names) else ""

    def do(self, action: str, name: str = None, new_name: str = "") -> dict:
        mode = "replace"
        if action == "select":
            keys = QtWidgets.QApplication.keyboardModifiers()
            mode = "add" if keys & QtCore.Qt.ControlModifier else "subtract" if keys & QtCore.Qt.AltModifier else "replace"
        state = selections.run(action, self.name.text() if name is None else name, new_name,
                               self.weight.value(), mode, self.mass.value())
        self.apply(state, select=new_name or (self.name.text() if name is None else name))
        if action == "mass_get":
            self.mass.setValue(state["kilograms"])
        if state["report"]:
            self.say(state["report"])
        return state

    def refresh(self) -> None:
        self.apply(selections.run("auto"), select=self.name.text())
        self.completer.setModel(QtCore.QStringListModel(known_names(self.chosen_set()), self.completer))

    def apply(self, state: dict, select: str = "") -> None:
        self.names = list(state["names"])
        entries = namesets.read(name_sets_folder(), self.chosen_set()) if self.chosen_set() else []
        what = {name.lower(): description for name, description in entries}
        have = {name.lower() for name in self.names}
        self.offered = [name for name, _description in entries if name.lower() not in have] if state["object"] else []
        self.list.clear()
        for name in self.names:
            item = QtWidgets.QListWidgetItem(name + ("   [weighted]" if name in state["weighted"] else ""))
            item.setToolTip(what.get(name.lower(), ""))
            self.list.addItem(item)
        grey = QtGui.QBrush(self.palette().color(QtGui.QPalette.Disabled, QtGui.QPalette.Text))
        for name in self.offered:
            item = QtWidgets.QListWidgetItem("+ %s   - %s" % (name, what[name.lower()]) if what[name.lower()] else "+ " + name)
            item.setForeground(grey)
            item.setToolTip("Not on this object yet. Pick verts or polys and double click to assign them")
            self.list.addItem(item)
        if select in self.names:
            self.list.setCurrentRow(self.names.index(select))
        self.object_label.setText("Object: " + state["object"] if state["object"] else NO_OBJECT)
        if state["status"]:
            self.status.setText(state["status"])
        self.colour.blockSignals(True)
        self.colour.setChecked(bool(state["shown"]))
        self.colour.blockSignals(False)

    def offered_at(self, row: int) -> str:
        """The name of a grey row"""
        at = row - len(self.names)
        return self.offered[at] if 0 <= at < len(self.offered) else ""

    def item_clicked(self, item) -> None:
        self.name.setText(self.current() or self.offered_at(self.list.row(item)))
        if self.colour.isChecked() and self.current():
            self.do("show")
        self.show_faces()

    def show_faces(self) -> None:
        """Texture and .rvmat of the picked selection's faces into the two fields"""
        found = selections.face_materials(self.current()) if self.current() else {"pairs": [], "status": ""}
        texture, path = found["pairs"][0][:2] if found["pairs"] else ("", "")
        self.texture.setText(texture)
        self.rvmat.setText(path)
        if len(found["pairs"]) > 1:
            self.status.setText(found["status"])
            self.say("\n".join(["%s:" % self.current()] + ["  %d face(s): %s  |  %s" % (count, t or "(no texture)", m or "(no rvmat)")
                                                           for t, m, count in found["pairs"]]))

    def set_faces(self) -> str:
        name = self.current() or self.name.text().strip()
        if not name:
            self.status.setText("Pick the selection whose faces get the texture")
            return ""
        status = selections.set_face_materials(name, self.texture.text(), self.rvmat.text())
        self.status.setText(status)
        return status

    def item_double_clicked(self, item) -> None:
        offered = self.offered_at(self.list.row(item))
        if offered:                     # a grey row: what is picked on the mesh becomes this selection
            self.name.setText(offered)
            self.do("assign")
        else:
            self.do("select")

    def colour_toggled(self, on: bool) -> None:
        if on and not self.name.text():
            self.status.setText("Pick the selection to show in the list")
            self.colour.blockSignals(True)
            self.colour.setChecked(False)
            self.colour.blockSignals(False)
            return
        self.do("show" if on else "hide")

    # -- the list's menu

    def ask(self, title: str, initial: str = "") -> str:
        text, ok = QtWidgets.QInputDialog.getText(self, title, "Name:", QtWidgets.QLineEdit.Normal, initial)
        return text.strip() if ok else ""

    def confirm(self, question: str) -> bool:
        return QtWidgets.QMessageBox.question(self, "Selections", question) == QtWidgets.QMessageBox.Yes

    def menu(self, action: str) -> None:
        picked = self.current()
        if action == "new":
            name = self.ask("New selection")
            if name:
                self.name.setText(name)
                self.do("new")
        elif action == "refresh":
            self.fill_name_sets()
            self.do("refresh")
        elif action == "name_sets":
            os.startfile(name_sets_folder())
        elif action == "edit_set":
            if self.chosen_set():
                os.startfile(os.path.join(name_sets_folder(), self.chosen_set() + namesets.EXTENSION))
        elif not picked:
            return
        elif action == "delete":
            self.do("clear", picked)
        elif action == "delete_all":
            if self.confirm("Take \"%s\" out of every object of the scene?" % picked):
                self.do("delete", picked)
        elif action == "redefine":
            self.do("set", picked)
        elif action in ("rename", "rename_all"):
            name = self.ask("Rename (All LODs)" if action == "rename_all" else "Rename", picked)
            if name:
                self.do("rename" if action == "rename_all" else "rename_here", picked, name)
                self.name.setText(name if name in self.names else self.name.text())

    def open_menu(self, position) -> None:
        item = self.list.itemAt(position)
        if item is not None:
            self.list.setCurrentItem(item)
            self.name.setText(self.current() or self.offered_at(self.list.row(item)))
        own = bool(self.current())
        menu = QtWidgets.QMenu(self)
        entries = (("New", "new", True), None, ("Delete", "delete", own), ("Delete (All LODs)", "delete_all", own),
                   ("Rename", "rename", own), ("Rename (All LODs)", "rename_all", own), None,
                   ("Redefine", "redefine", own), None, ("Refresh", "refresh", True), None,
                   ("Edit this name set", "edit_set", bool(self.chosen_set())), ("Name sets folder", "name_sets", True))
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            text, action, enabled = entry
            added = menu.addAction(text)
            added.setEnabled(enabled)
            added.triggered.connect(lambda _checked=False, a=action: self.menu(a))
        menu.exec_(self.list.mapToGlobal(position))

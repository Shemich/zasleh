import os

from PySide2 import QtWidgets

from .. import settings

# key, label, a folder?, what it is for
PATHS = (
    ("texRoot", "Tex root", True, "Your project drive, usually P:\\. Texture paths of a p3d are relative to it"),
    ("gameRoot", "Game data", True, "The folder with your unpacked game data (it holds a3\\...): "
                                    "textures of the game are shown on imported models"),
    ("debinarizer", "Debinarizer", False, "A program that turns a binarized (ODOL) p3d into an editable one, called as\n"
                                          "\"program inFolder outFolder\" (P3DDebinarizer does). "
                                          "Binarized models go through it on import"),
    ("imageToPaa", "ImageToPAA", False, "ImageToPAA.exe of Arma 3 Tools: converts textures to .paa when they are deployed on export"),
    ("texConv", "Texconv", False, "texconv.exe of DirectXTex: needed only when deployed textures come from .dds"),
)


class PathRow(QtWidgets.QWidget):
    """A path kept in the settings: a field and a button to browse"""

    def __init__(self, key: str, caption: str, pick_folder: bool, tip: str):
        super().__init__()
        self.key, self.caption, self.pick_folder = key, caption, pick_folder
        self.edit = QtWidgets.QLineEdit(settings.get(key))
        self.edit.setToolTip(tip)
        self.edit.editingFinished.connect(lambda: settings.put(key, self.edit.text().strip()))
        browse = QtWidgets.QToolButton()
        browse.setText("...")
        browse.clicked.connect(self.browse)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)

    def browse(self) -> None:
        if self.pick_folder:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, self.caption, self.edit.text())
        else:
            path, _kind = QtWidgets.QFileDialog.getOpenFileName(self, self.caption, self.edit.text(), "Programs (*.exe)")
        if path:
            self.edit.setText(os.path.normpath(path))
            settings.put(self.key, self.edit.text())


class SettingsDialog(QtWidgets.QDialog):
    """Folders and tools the plugin is told about once"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zasleh settings")
        self.rows = {}
        form = QtWidgets.QFormLayout()
        for key, label, folder, tip in PATHS:
            self.rows[key] = PathRow(key, label, folder, tip)
            form.addRow(label, self.rows[key])
        if not self.rows["texRoot"].edit.text():
            self.rows["texRoot"].edit.setPlaceholderText(settings.default_texture_root())
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(close)
        self.setMinimumWidth(520)

    def accept(self) -> None:
        for key, row in self.rows.items():              # a field left with the cursor in it counts too
            settings.put(key, row.edit.text().strip())
        super().accept()

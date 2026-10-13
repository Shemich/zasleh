from PySide2 import QtCore, QtWidgets

from .. import __version__

from .config_tab import ConfigTab
from .hitpoints_tab import HitPointsTab
from .materials_tab import MaterialsTab
from .memory_tab import MemoryTab
from .model_tab import ModelTab
from .multi_tab import MultiTab
from .selections_tab import SelectionsTab
from .settings_dialog import SettingsDialog

ABOUT = "Zasleh %s: Arma 3 p3d tools for 3ds Max" % __version__


class Panel(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Zasleh", parent)
        self.setObjectName("zaslehPanel")
        self.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)

        self.model = ModelTab(self.say)
        self.selections = SelectionsTab(self.say)
        self.memory = MemoryTab(self.say)
        self.hitpoints = HitPointsTab(self.say)
        self.materials = MaterialsTab(self.say)
        self.config = ConfigTab(self.say)
        self.multi = MultiTab(self.say, self.model.options)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.model, "Model")
        self.tabs.addTab(self.selections, "Selections")
        self.tabs.addTab(self.memory, "Memory")
        self.tabs.addTab(self.hitpoints, "Hit points")
        self.tabs.addTab(self.materials, "Materials")
        self.tabs.addTab(self.config, "Config")
        self.tabs.addTab(self.multi, "Multi")
        self.tabs.currentChanged.connect(lambda _index: self.refresh())

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.log.setMaximumHeight(220)
        self.log.hide()
        self.log_toggle = QtWidgets.QToolButton()
        self.log_toggle.setCheckable(True)
        self.log_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.log_toggle.setToolTip("Show / hide the log")
        self.log_toggle.toggled.connect(self.show_log)
        self.last = QtWidgets.QLabel(ABOUT)
        self.last.setToolTip(ABOUT)
        self.last.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        settings_button = QtWidgets.QToolButton()
        settings_button.setText("Settings")
        settings_button.setToolTip("Tex root, game data, debinarizer, ImageToPAA, texconv")
        settings_button.clicked.connect(lambda _checked=False: self.open_settings())
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(self.log_toggle)
        bar.addWidget(self.last, 1)
        bar.addWidget(settings_button)

        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bar)
        layout.addWidget(self.log)
        self.setWidget(body)
        self.setMinimumWidth(260)

    def show_log(self, on: bool) -> None:
        self.log.setVisible(on)
        self.log_toggle.setArrowType(QtCore.Qt.DownArrow if on else QtCore.Qt.RightArrow)

    def say(self, text: str) -> None:
        self.log.appendPlainText(text)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())
        lines = [line for line in text.split("\n") if line.strip()]
        if lines:
            self.last.setText(lines[0].strip())
            self.last.setToolTip(text)
        if len(lines) > 1:                  # a report: worth seeing whole
            self.log_toggle.setChecked(True)

    def open_settings(self) -> None:
        SettingsDialog(self).exec_()
        self.refresh()

    def refresh(self) -> None:
        self.tabs.currentWidget().refresh()

    def selection_changed(self) -> None:
        if self.tabs.currentWidget() in (self.selections, self.memory):
            self.tabs.currentWidget().refresh()

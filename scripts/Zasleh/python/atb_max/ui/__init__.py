"""The toolbox panel (Qt)"""

import pymxs

rt = pymxs.runtime
_panel = None
_CALLBACK = "zaslehPanel"


def instance():
    return _panel


def _dock(main, panel) -> None:
    """Left side; as a tab of the scene explorer if one is docked there, so it takes no extra width"""
    from PySide2 import QtCore, QtWidgets
    left = QtCore.Qt.LeftDockWidgetArea
    main.addDockWidget(left, panel)
    for dock in main.findChildren(QtWidgets.QDockWidget):
        if dock is panel or not dock.isVisible() or dock.isFloating() or main.dockWidgetArea(dock) != left:
            continue
        if "explorer" in (dock.windowTitle() + " " + dock.objectName()).lower():
            main.tabifyDockWidget(dock, panel)
            break


def show():
    """Open the panel, or bring it back if it is open already"""
    global _panel
    import qtmax
    from .panel import Panel
    if _panel is None:
        main = qtmax.GetQMaxMainWindow()
        _panel = Panel(main)
        if main is not None:
            _dock(main, _panel)
        rt.callbacks.removeScripts(id=rt.Name(_CALLBACK))
        rt.callbacks.addScript(rt.Name("selectionSetChanged"),
                               "python.Execute \"import atb_max.ui as u; u.selection_changed()\"",
                               id=rt.Name(_CALLBACK))
    _panel.show()
    _panel.raise_()
    _panel.refresh()
    return _panel


def close():
    global _panel
    rt.callbacks.removeScripts(id=rt.Name(_CALLBACK))
    if _panel is not None:
        _panel.close()
        _panel.deleteLater()
        _panel = None


def selection_changed():
    if _panel is not None and _panel.isVisible():
        _panel.selection_changed()

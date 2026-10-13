-- Zasleh: opens the panel (python\zasleh\ui)
python.Execute ("import sys\np = r'" + (getDir #scripts) + "\\Zasleh\\python'\nif p not in sys.path: sys.path.insert(0, p)\nimport zasleh.ui\nzasleh.ui.show()")

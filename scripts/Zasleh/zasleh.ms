-- Zasleh: opens the panel (python\atb_max\ui)
python.Execute ("import sys\np = r'" + (getDir #scripts) + "\\Zasleh\\python'\nif p not in sys.path: sys.path.insert(0, p)\nimport atb_max.ui\natb_max.ui.show()")

-- toolbar button of the Zasleh panel
macroScript zasleh category:"Zasleh" buttonText:"Zasleh" tooltip:"Zasleh: Arma 3 p3d tools" icon:#("zasleh", 1)
(
    on execute do fileIn ((getDir #scripts) + "\\Zasleh\\zasleh.ms")
)

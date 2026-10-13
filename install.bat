@echo off
rem ----------------------------------------------------------------------------
rem  Zasleh - install into 3ds Max
rem
rem    install.bat ["path to the 3ds Max folder"]
rem
rem  Links <3ds Max>\scripts\Zasleh to this folder, so the plugin 3ds Max runs
rem  is always the one here, and copies the toolbar icon and the macroscript.
rem  Run it as administrator if 3ds Max does not let you write to its folder.
rem ----------------------------------------------------------------------------
setlocal
set "HERE=%~dp0"
set "MAXROOT=%~1"
if "%MAXROOT%"=="" set "MAXROOT=C:\Program Files\Autodesk\3ds Max 2024"

if not exist "%MAXROOT%\3dsmax.exe" (
    echo 3ds Max was not found in "%MAXROOT%".
    echo Give its folder: install.bat "C:\Program Files\Autodesk\3ds Max 2024"
    exit /b 1
)

if exist "%MAXROOT%\scripts\Zasleh\zasleh.ms" (
    echo scripts\Zasleh is already there - left as it is.
) else (
    rem an empty folder left from an earlier install would be in the way
    if exist "%MAXROOT%\scripts\Zasleh" rmdir "%MAXROOT%\scripts\Zasleh"
    mklink /J "%MAXROOT%\scripts\Zasleh" "%HERE%scripts\Zasleh"
    if errorlevel 1 (
        echo Could not link scripts\Zasleh. Run this file as administrator.
        exit /b 1
    )
)

copy /y "%HERE%ui\icons\zasleh_*.bmp" "%MAXROOT%\ui\icons\" >nul
copy /y "%HERE%ui\macroscripts\zasleh.mcr" "%MAXROOT%\ui\macroscripts\" >nul

echo Installed into "%MAXROOT%".
echo In 3ds Max: Customize - Customize User Interface - Toolbars, category Zasleh.
endlocal

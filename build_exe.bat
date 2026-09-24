@echo off
rem Construieste ImportTematica.exe (PyInstaller, varianta folder) in dist\ImportTematica si arhiva
rem dist\ImportTematica.zip. config.yaml, Data\Images si exemplul se copiaza langa .exe (se pot edita fara rebuild).
setlocal
cd /d "%~dp0"

py -m pip install -q -r requirements.txt pyinstaller || goto :eroare

py -m PyInstaller --noconfirm --clean --windowed --name ImportTematica ^
    --collect-submodules winrt --collect-submodules comtypes --hidden-import pywinauto ^
    --distpath dist --workpath build --specpath build gui.py || goto :eroare

set DEST=dist\ImportTematica
copy /y config.yaml "%DEST%\" >nul
copy /y .env.example "%DEST%\" >nul
xcopy /y /e /i /q Data\Images "%DEST%\Data\Images" >nul
xcopy /y /e /i /q Data\Input "%DEST%\Data\Input" >nul
copy /y LEAME_EXE.txt "%DEST%\" >nul

rem verificarea executabilului (fara Pentana): scrie selftest.txt langa .exe
"%DEST%\ImportTematica.exe" --selftest
type "%DEST%\selftest.txt"
del "%DEST%\selftest.txt"

powershell -NoProfile -Command "Compress-Archive -Force -Path '%DEST%' -DestinationPath 'dist\ImportTematica.zip'"
echo.
echo Gata: %DEST%\ImportTematica.exe  (arhiva: dist\ImportTematica.zip)
exit /b 0

:eroare
echo Constructia a esuat.
exit /b 1

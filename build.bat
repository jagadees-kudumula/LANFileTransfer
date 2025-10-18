@echo off
echo Installing dependencies...
pip install flask flask-socketio flask-cors qrcode[pil] pyqt5 pyinstaller

echo Cleaning previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "LANFileServer.spec" del "LANFileServer.spec"

echo Building executable...
pyinstaller --onefile --windowed --name "LANFileServer" --add-data "react-build;react-build" --add-data "server.py;." --hidden-import=engineio.async_drivers.threading --hidden-import=server main.py

echo Build complete! Check the 'dist' folder for LANFileServer.exe
pause
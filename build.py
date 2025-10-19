#!/usr/bin/env python3
import os
import platform
import subprocess
import sys

def build_app():
    system = platform.system()
    print(f"🔨 Building LAN File Server for {system}...")
    
    # Install dependencies
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", 
                          "flask", "flask-socketio", "flask-cors", 
                          "qrcode[pil]", "pyinstaller"])
    
    # Clean previous builds
    print("Cleaning previous builds...")
    for item in ["dist", "build", "LANFileServer.spec"]:
        if os.path.exists(item):
            if os.path.isdir(item):
                import shutil
                shutil.rmtree(item)
            else:
                os.remove(item)
    
    # Build command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name", "LANFileServer" if system == "Windows" else "lanfileserver",
        "--add-data", f"react-build{os.pathsep}react-build",
        "--add-data", f"server.py{os.pathsep}.",
        "--hidden-import=engineio.async_drivers.threading",
        "--hidden-import=server",
        "main.py"
    ]
    
    # Platform-specific options
    if system == "Windows":
        cmd.insert(2, "--windowed")
    
    print("Building executable...")
    subprocess.check_call(cmd)
    
    # Make executable on Unix-like systems
    if system != "Windows":
        exe_path = "dist/lanfileserver"
        os.chmod(exe_path, 0o755)
        print(f"✅ Made executable: {exe_path}")
    
    print(f"✅ Build complete! Check the 'dist' folder")
    
    if system == "Windows":
        print("🚀 Run with: dist\\LANFileServer.exe")
    else:
        print("🚀 Run with: ./dist/lanfileserver")

if __name__ == "__main__":
    build_app()
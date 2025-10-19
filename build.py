#!/usr/bin/env python3
import os
import platform
import subprocess
import sys
from PIL import Image  # For icon conversion

def convert_icon_for_windows():
    """Convert PNG to ICO for Windows"""
    try:
        if os.path.exists("icon.png"):
            img = Image.open("icon.png")
            # Resize to multiple sizes for better quality
            sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
            img.save("icon.ico", format='ICO', sizes=sizes)
            print("✅ Converted icon.png to icon.ico for Windows")
            return "icon.ico"
    except Exception as e:
        print(f"⚠️  Could not convert icon: {e}")
    return None

def build_app():
    system = platform.system()
    print(f"🔨 Building LAN File Server for {system}...")
    
    # Install dependencies
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", 
                          "flask", "flask-socketio", "flask-cors", 
                          "qrcode[pil]", "pyinstaller", "pillow", "psutil"])
    
    # Clean previous builds
    print("Cleaning previous builds...")
    for item in ["dist", "build", "LANFileServer.spec"]:
        if os.path.exists(item):
            if os.path.isdir(item):
                import shutil
                shutil.rmtree(item)
            else:
                os.remove(item)
    
    # Handle icons
    icon_path = None
    if system == "Windows":
        # Convert PNG to ICO for Windows
        icon_path = convert_icon_for_windows() or "icon.png"
    else:
        # Linux/Mac can use PNG directly
        if os.path.exists("icon.png"):
            icon_path = "icon.png"
    
    # Build command - FIXED: Properly include server.py and add all required hidden imports
    cmd = [
        "pyinstaller",
        "--onefile",
        "--name", "LANFileServer" if system == "Windows" else "lanfileserver",
        "--add-data", f"react-build{os.pathsep}react-build",
        "--add-data", f"server.py{os.pathsep}.",
        "--hidden-import=engineio.async_drivers.threading",
        "--hidden-import=server",
        "--hidden-import=flask",
        "--hidden-import=flask_socketio",
        "--hidden-import=flask_cors",
        "--hidden-import=qrcode",
        "--hidden-import=psutil",
        "--hidden-import=PIL",
        "--hidden-import=PIL._imaging",
        "--collect-all", "flask_socketio",
        "--collect-all", "engineio",
        "--collect-all", "socketio",
    ]
    
    # Add icon if available
    if icon_path and os.path.exists(icon_path):
        cmd.extend(["--icon", icon_path])
        print(f"✅ Using icon: {icon_path}")
    
    # Platform-specific options
    if system == "Windows":
        cmd.append("--windowed")
    
    # Add main.py at the end
    cmd.append("main.py")
    
    print("Building executable...")
    print("Command:", " ".join(cmd))
    subprocess.check_call(cmd)
    
    # Make executable on Unix-like systems
    if system != "Windows":
        exe_path = "dist/lanfileserver"
        os.chmod(exe_path, 0o755)
        print(f"✅ Made executable: {exe_path}")
    
    # Clean up temporary ICO file (keep PNG)
    if system == "Windows" and os.path.exists("icon.ico"):
        os.remove("icon.ico")
        print("✅ Cleaned up temporary icon.ico")
    
    print(f"✅ Build complete! Check the 'dist' folder")
    
    if system == "Windows":
        print("🚀 Run with: dist\\LANFileServer.exe")
    else:
        print("🚀 Run with: ./dist/lanfileserver")

if __name__ == "__main__":
    build_app()
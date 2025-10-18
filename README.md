# LAN File Server

>A cross-platform LAN file server with a modern web interface for browsing, uploading, downloading files, and sharing clipboard text between devices on the same network.

---

## Features

- **File Browser:** Browse, view, upload, and download files/folders on the server.
- **Shared Clipboard:** Instantly share text between devices via a web clipboard.
- **QR Code Access:** Scan a QR code to connect quickly from mobile or desktop.
- **Real-Time Updates:** Powered by Socket.IO for instant changes.
- **Simple UI:** Responsive React-based interface in a single HTML file.
- **Standalone Build:** Easily create a Windows executable for distribution.

---

## Quick Start

### Prerequisites
- Python 3.x
- (Optional) Virtual environment (`myenv/`)

### Setup & Run
1. (Optional) Activate the virtual environment:
	```powershell
	.\myenv\Scripts\Activate.ps1
	```
2. Install dependencies:
	```powershell
	pip install -r requirements.txt
	```
3. Start the server:
	```powershell
	python server.py
	```
4. Open the web interface using the provided IP address and token (scan QR code).

---

## Building Standalone Executable

Use `build.bat` to package the server as a Windows executable:

```powershell
.\build.bat
```

**What `build.bat` does:**
- Installs all required Python packages (Flask, Flask-SocketIO, Flask-CORS, qrcode[pil], PyQt5, PyInstaller, etc.)
- Cleans up previous build artifacts (`dist`, `build`, `LANFileServer.spec`)
- Runs PyInstaller to bundle the backend and frontend into a single executable (`LANFileServer.exe`)
- The executable is placed in the `dist` folder and can be run on any Windows machine without Python installed.

---

## Project Structure

- `main.py` — Optional PyQt5 launcher for a desktop experience and QR code display
- `server.py` — Main Flask backend (file API, clipboard, Socket.IO, QR code, authentication)
- `react-build/index.html` — React-based frontend (single HTML file, no build step required)
- `build.bat` — Windows batch script to build a standalone executable
- `requirements.txt` — All Python dependencies
- `myenv/` — Python virtual environment (optional, not tracked in git)
- `build/`, `dist/` — Build artifacts (not tracked in git)

---

## Security

- Access is protected by a random token (see QR code or URL parameter)
- Do not share your token publicly
- All file and clipboard operations require the token for authentication

---

## Customization

- To change the frontend, edit `react-build/index.html` (uses React, ReactDOM, Babel, and Socket.IO via CDN)
- To change backend logic, edit `server.py` (Flask app)
- To add more dependencies, update `requirements.txt` and `build.bat` if needed

---

## License

MIT

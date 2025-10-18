from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import os
import socket
import qrcode
import zipfile
import secrets
import threading
import time
import atexit
import base64
from io import BytesIO
import psutil

# Configuration
PORT = 8080
HOST = '0.0.0.0'
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
CLIPBOARD_FILE = os.path.join(DESKTOP_PATH, "clipboard.txt")
QR_CODE_FILE = os.path.join(DESKTOP_PATH, "lan_server_qr.png")
TEMP_ZIP_FOLDER = os.path.join(DESKTOP_PATH, "temp_zips")

# Optimized chunk size for speed (8MB chunks)
CHUNK_SIZE = 16 * 1024 * 1024

os.makedirs(TEMP_ZIP_FOLDER, exist_ok=True)

# Flask setup
app = Flask(__name__, static_folder='react-build', static_url_path='')
CORS(app)
app.config['SECRET_KEY'] = secrets.token_urlsafe(32)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 * 1024  # 100GB max file size
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

AUTH_TOKEN = os.environ.get('AUTH_TOKEN', secrets.token_urlsafe(16))
temp_zip_files = set()

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_qr_code():
    try:
        HOST_IP = get_ip()
        qr_data = f"http://{HOST_IP}:{PORT}/?token={AUTH_TOKEN}"  # Include token in QR
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(QR_CODE_FILE)
        print(f"✅ QR code generated: {QR_CODE_FILE}")
        print(f"🔐 Access token: {AUTH_TOKEN}")
        return True
    except Exception as e:
        print(f"❌ QR code generation failed: {e}")
        return False

def generate_qr_base64():
    try:
        HOST_IP = get_ip()
        qr_data = f"http://{HOST_IP}:{PORT}/?token={AUTH_TOKEN}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"QR base64 generation failed: {e}")
        return ""

def get_drives():
    """Get all available drives on Windows"""
    drives = []
    try:
        for partition in psutil.disk_partitions():
            try:
                if os.name == 'nt':  # Windows
                    if 'cdrom' in partition.opts:
                        continue
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({
                    'name': f"{partition.mountpoint}",
                    'path': partition.mountpoint,
                    'isDir': True,
                    'size': usage.total,
                    'free': usage.free,
                    'used': usage.used,
                    'modified': time.time()
                })
            except:
                continue
    except Exception as e:
        print(f"Error getting drives: {e}")
    return drives

# Clipboard functionality
clipboard_content = ""
clipboard_file_modified_time = 0

def load_clipboard():
    global clipboard_file_modified_time
    try:
        if os.path.exists(CLIPBOARD_FILE):
            current_mtime = os.path.getmtime(CLIPBOARD_FILE)
            with open(CLIPBOARD_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                clipboard_file_modified_time = current_mtime
                return content
    except Exception as e:
        print(f"Error loading clipboard: {e}")
    return ""

def save_clipboard(text):
    global clipboard_file_modified_time
    try:
        with open(CLIPBOARD_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        clipboard_file_modified_time = os.path.getmtime(CLIPBOARD_FILE)
        return True
    except Exception as e:
        print(f"Error saving clipboard: {e}")
        return False

def monitor_clipboard_file():
    global clipboard_content, clipboard_file_modified_time
    while True:
        try:
            if os.path.exists(CLIPBOARD_FILE):
                current_mtime = os.path.getmtime(CLIPBOARD_FILE)
                if current_mtime > clipboard_file_modified_time:
                    new_content = load_clipboard()
                    if new_content != clipboard_content:
                        clipboard_content = new_content
                        socketio.emit('clipboard_update', {'text': clipboard_content})
        except Exception as e:
            print(f"File monitor error: {e}")
        time.sleep(1)

# Initialize clipboard
clipboard_content = load_clipboard()
threading.Thread(target=monitor_clipboard_file, daemon=True).start()

# API Routes
@app.route('/')
def serve_react():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/files/')
@app.route('/api/files/<path:filepath>')
def list_files(filepath=''):
    try:
        # If root path, return drives
        if filepath == '':
            drives = get_drives()
            return jsonify({
                'path': '',
                'files': drives,
                'isRoot': True
            })

        # Handle path with backslashes
        abs_path = filepath.replace('/', '\\') if os.name == 'nt' else filepath
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            return jsonify({'error': 'Path not found'}), 404

        entries = []
        for item in sorted(os.listdir(abs_path)):
            if item.startswith('.'):
                continue
                
            full_path = os.path.join(abs_path, item)
            try:
                stat = os.stat(full_path)
                entries.append({
                    'name': item,
                    'path': full_path,
                    'isDir': os.path.isdir(full_path),
                    'size': stat.st_size if not os.path.isdir(full_path) else 0,
                    'modified': stat.st_mtime
                })
            except OSError:
                continue

        return jsonify({
            'path': filepath,
            'files': entries,
            'isRoot': False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_chunked_file(filepath, chunk_size=CHUNK_SIZE):
    """Generator function for chunked file transfer"""
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

@app.route('/api/download/<path:filepath>')
def download_file(filepath):
    try:
        # Handle path with backslashes for Windows
        abs_path = filepath.replace('/', '\\') if os.name == 'nt' else filepath
        if not os.path.exists(abs_path):
            return jsonify({'error': 'File not found'}), 404

        filename = os.path.basename(abs_path)
        
        if os.path.isdir(abs_path):
            # Fast zip creation with minimal compression for speed
            zip_filename = f"{filename}_{int(time.time())}.zip"
            zip_path = os.path.join(TEMP_ZIP_FOLDER, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:  # STORED = no compression for speed
                for root, dirs, files in os.walk(abs_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, abs_path)
                        zipf.write(file_path, arcname)
            
            temp_zip_files.add(zip_path)
            
            # Chunked transfer for zip files
            file_size = os.path.getsize(zip_path)
            response = Response(
                generate_chunked_file(zip_path),
                mimetype='application/zip',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}.zip"',
                    'Content-Length': str(file_size)
                }
            )
            return response
        else:
            # Chunked transfer for single files
            file_size = os.path.getsize(abs_path)
            response = Response(
                generate_chunked_file(abs_path),
                mimetype='application/octet-stream',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Content-Length': str(file_size)
                }
            )
            return response
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        current_path = request.form.get('path', '')
        # Handle path with backslashes for Windows
        target_dir = current_path.replace('/', '\\') if os.name == 'nt' else current_path
        
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        uploaded = []
        
        for file in files:
            if file.filename:
                filename = os.path.basename(file.filename)
                save_path = os.path.join(target_dir, filename)
                
                # Stream the file directly to disk
                file.save(save_path)
                uploaded.append(filename)

        return jsonify({'message': f'Uploaded {len(uploaded)} files', 'files': uploaded})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clipboard', methods=['GET', 'POST'])
def handle_clipboard():
    global clipboard_content
    if request.method == 'GET':
        return jsonify({'content': clipboard_content})
    else:
        data = request.json
        clipboard_content = data.get('content', '')
        save_clipboard(clipboard_content)
        socketio.emit('clipboard_update', {'text': clipboard_content})
        return jsonify({'message': 'Clipboard updated'})

# ---------- Strict Authentication ----------
@app.before_request
def check_auth():
    # Skip auth for static files and socket.io
    if request.path.startswith('/static/') or request.path.startswith('/socket.io/'):
        return
    
    # Skip auth for server-info (needed for initial token validation)
    if request.path == '/api/server-info':
        return
    
    # ALL other routes require token - including the main page
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        return jsonify({'error': 'Invalid or missing access token'}), 403

# ---------- Server Info (public but validates token) ----------
@app.route('/api/server-info')
def server_info():
    # Validate token for server-info as well
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        return jsonify({'error': 'Invalid access token'}), 403
    
    ip = get_ip()
    qr_base64 = generate_qr_base64()
    return jsonify({
        'ip': ip,
        'port': PORT,
        'localUrl': f'http://localhost:{PORT}/?token={AUTH_TOKEN}',
        'networkUrl': f'http://{ip}:{PORT}/?token={AUTH_TOKEN}',
        'qrBase64': qr_base64,
        'token': AUTH_TOKEN
    })

# Serve static files correctly
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# SocketIO events
@socketio.on('connect')
def handle_connect():
    emit('clipboard_update', {'text': clipboard_content})

@socketio.on('clipboard_update')
def handle_clipboard_update(data):
    global clipboard_content
    clipboard_content = data.get('text', '')
    save_clipboard(clipboard_content)
    emit('clipboard_update', {'text': clipboard_content}, broadcast=True)

# Serve local SocketIO client
@app.route('/socket.io.js')
def serve_socketio():
    return send_file(os.path.join(app.static_folder, 'socket.io.js'))

# Cleanup
def cleanup():
    for zip_file in temp_zip_files:
        try:
            if os.path.exists(zip_file):
                os.remove(zip_file)
        except:
            pass

@app.route('/api/view/<path:filepath>')
def view_file(filepath):
    try:
        # Check token first
        token = request.args.get('token')
        if token != AUTH_TOKEN:
            return jsonify({'error': 'Invalid or missing access token'}), 403
        
        abs_path = filepath.replace('/', '\\') if os.name == 'nt' else filepath
        if not os.path.exists(abs_path) or os.path.isdir(abs_path):
            return jsonify({'error': 'File not found or is a directory'}), 404

        # For media files, use direct file serving (not chunked) for instant playback
        media_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mp3', '.wav', '.ogg', '.flac', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        file_ext = os.path.splitext(abs_path)[1].lower()
        
        if file_ext in media_extensions:
            # Direct file serving for instant video playback
            return send_file(abs_path)
        else:
            # Chunked transfer for other files
            file_size = os.path.getsize(abs_path)
            response = Response(
                generate_chunked_file(abs_path),
                headers={
                    "Content-Disposition": f'inline; filename="{os.path.basename(abs_path)}"',
                    "Content-Length": str(file_size)
                }
            )
            
            # Set appropriate content type
            import mimetypes
            mimetype, _ = mimetypes.guess_type(abs_path)
            if mimetype:
                response.headers['Content-Type'] = mimetype
            
            return response
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

atexit.register(cleanup)

if __name__ == '__main__':
    print("🚀 Starting LAN File Server...")
    print(f"📁 Desktop path: {DESKTOP_PATH}")
    
    # Generate QR code
    if generate_qr_code():
        print(f"✅ QR code saved to desktop: {QR_CODE_FILE}")
    else:
        print("❌ Failed to generate QR code")
    
    print(f"🌐 Server starting on http://{get_ip()}:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)
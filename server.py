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
import logging
from logging.handlers import RotatingFileHandler
import platform
from pathlib import Path
import sys

# Configuration
PORT = 8080
HOST = '0.0.0.0'

# Platform-specific paths
if platform.system() == "Windows":
    HOME_PATH = os.path.expanduser("~")
    DESKTOP_PATH = os.path.join(HOME_PATH, "Desktop")
else:
    HOME_PATH = os.path.expanduser("~")
    DESKTOP_PATH = os.path.join(HOME_PATH, "Desktop") if os.path.exists(os.path.join(HOME_PATH, "Desktop")) else HOME_PATH

CLIPBOARD_FILE = os.path.join(DESKTOP_PATH, "clipboard.txt")
QR_CODE_FILE = os.path.join(DESKTOP_PATH, "lan_server_qr.png")
TEMP_ZIP_FOLDER = os.path.join(DESKTOP_PATH, "temp_zips")

# Optimized chunk size for speed (16MB chunks)
CHUNK_SIZE = 16 * 1024 * 1024

# Create necessary directories
os.makedirs(TEMP_ZIP_FOLDER, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('server.log', maxBytes=10485760, backupCount=5),  # 10MB per file, 5 backups
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask setup
app = Flask(__name__, static_folder='react-build', static_url_path='')
CORS(app)
app.config['SECRET_KEY'] = secrets.token_urlsafe(32)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 * 1024  # 100GB max file size
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

AUTH_TOKEN = os.environ.get('AUTH_TOKEN', secrets.token_urlsafe(16))

# Thread-safe data structures
import threading
temp_zip_files = set()
temp_zip_files_lock = threading.Lock()
clipboard_lock = threading.Lock()

def get_ip():
    """Get the local IP address with pure Python methods"""
    try:
        # Method 1: Socket connection (works on all platforms)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logger.warning(f"Primary IP detection failed: {e}")
        
        # Method 2: Try getting IP from network interfaces (pure Python)
        try:
            # Get all network interfaces
            hostname = socket.gethostname()
            # Get all IP addresses associated with the hostname
            ip_list = socket.getaddrinfo(hostname, None)
            
            # Filter for IPv4 addresses that are not localhost
            for ip_info in ip_list:
                ip_address = ip_info[4][0]
                if (ip_address.startswith('192.168.') or 
                    ip_address.startswith('10.') or 
                    ip_address.startswith('172.') or
                    (ip_address.startswith('169.254.') and not ip_address == '169.254.0.0')):
                    return ip_address
                    
            # If no private IP found, return the first non-localhost IP
            for ip_info in ip_list:
                ip_address = ip_info[4][0]
                if ip_address != '127.0.0.1' and not ip_address.startswith('::'):
                    return ip_address
                    
        except Exception as e:
            logger.warning(f"Alternative IP detection failed: {e}")
            
        # Final fallback
        return '127.0.0.1'

def generate_qr_code():
    """Generate QR code with authentication token"""
    try:
        HOST_IP = get_ip()
        qr_data = f"http://{HOST_IP}:{PORT}/?token={AUTH_TOKEN}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(QR_CODE_FILE)
        logger.info(f"QR code generated: {QR_CODE_FILE}")
        logger.info(f"Access token: {AUTH_TOKEN}")
        return True
    except Exception as e:
        logger.error(f"QR code generation failed: {e}")
        return False

def generate_qr_base64():
    """Generate QR code as base64 for web display"""
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
        logger.error(f"QR base64 generation failed: {e}")
        return ""

def get_safe_path(path):
    """Convert and validate file paths safely"""
    try:
        abs_path = os.path.abspath(path)
        
        # Security: Prevent directory traversal
        if '../' in path or '..\\' in path:
            return None
            
        valid_drives = [partition.mountpoint for partition in psutil.disk_partitions()]
        valid_drives.append(HOME_PATH)
        
        # Allow access if path is within any valid drive
        for drive in valid_drives:
            if abs_path.startswith(drive):
                return abs_path
                
        # If we get here, the path is not within any valid drive
        return None
    
    except Exception:
        return None

def get_drives():
    """Get available drives/filesystems safely"""
    drives = []
    try:
        # Always start with home directory
        home_drive = {
            'name': "Home",
            'path': HOME_PATH,
            'isDir': True,
            'size': 0,
            'free': 0,
            'used': 0,
            'modified': time.time()
        }
        
        # Try to get actual disk usage for home directory
        try:
            usage = psutil.disk_usage(HOME_PATH)
            home_drive.update({
                'size': usage.total,
                'free': usage.free,
                'used': usage.used
            })
        except:
            pass
            
        drives.append(home_drive)
        
        # Add other drives (Windows) or mount points (Linux/Mac)
        for partition in psutil.disk_partitions():
            try:
                # Skip CD-ROM and special drives
                if 'cdrom' in partition.opts or partition.fstype == '':
                    continue
                    
                # Skip system partitions that might be sensitive
                if platform.system() == "Windows":
                    if partition.mountpoint in ['C:\\', 'A:\\', 'B:\\']:
                        # For C: drive, only show user-accessible areas
                        user_profile = {
                            'name': "User Profile",
                            'path': HOME_PATH,
                            'isDir': True,
                            'size': 0,
                            'free': 0,
                            'used': 0,
                            'modified': time.time()
                        }
                        try:
                            usage = psutil.disk_usage(HOME_PATH)
                            user_profile.update({
                                'size': usage.total,
                                'free': usage.free,
                                'used': usage.used
                            })
                        except:
                            pass
                        drives.append(user_profile)
                        continue
                
                # For other drives, include them
                if partition.mountpoint != HOME_PATH:
                    usage = psutil.disk_usage(partition.mountpoint)
                    drives.append({
                        'name': f"Drive {partition.mountpoint}",
                        'path': partition.mountpoint,
                        'isDir': True,
                        'size': usage.total,
                        'free': usage.free,
                        'used': usage.used,
                        'modified': time.time()
                    })
            except Exception as e:
                logger.warning(f"Failed to get info for {partition.mountpoint}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error getting drives: {e}")
    
    return drives

# Clipboard functionality with thread safety
clipboard_content = ""
clipboard_file_modified_time = 0

def load_clipboard():
    """Load clipboard content with thread safety"""
    global clipboard_file_modified_time
    with clipboard_lock:
        try:
            if os.path.exists(CLIPBOARD_FILE):
                current_mtime = os.path.getmtime(CLIPBOARD_FILE)
                with open(CLIPBOARD_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    clipboard_file_modified_time = current_mtime
                    return content
        except Exception as e:
            logger.error(f"Error loading clipboard: {e}")
        return ""

def save_clipboard(text):
    """Save clipboard content with thread safety"""
    global clipboard_file_modified_time
    with clipboard_lock:
        try:
            with open(CLIPBOARD_FILE, "w", encoding="utf-8") as f:
                f.write(text)
            clipboard_file_modified_time = os.path.getmtime(CLIPBOARD_FILE)
            return True
        except Exception as e:
            logger.error(f"Error saving clipboard: {e}")
            return False

def monitor_clipboard_file():
    """Monitor clipboard file for changes with thread safety"""
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
            logger.error(f"File monitor error: {e}")
        time.sleep(1)

# Initialize clipboard
clipboard_content = load_clipboard()
clipboard_monitor_thread = threading.Thread(target=monitor_clipboard_file, daemon=True)
clipboard_monitor_thread.start()

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

        # Get and validate safe path
        abs_path = get_safe_path(filepath)
        if not abs_path or not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            return jsonify({'error': 'Path not found or access denied'}), 404

        entries = []
        for item in sorted(os.listdir(abs_path)):
            if item.startswith('.'):
                continue
                
            full_path = os.path.join(abs_path, item)
            try:
                # Additional security check
                if not get_safe_path(full_path):
                    continue
                    
                stat = os.stat(full_path)
                entries.append({
                    'name': item,
                    'path': full_path,
                    'isDir': os.path.isdir(full_path),
                    'size': stat.st_size if not os.path.isdir(full_path) else 0,
                    'modified': stat.st_mtime
                })
            except (OSError, PermissionError) as e:
                logger.warning(f"Access denied to {full_path}: {e}")
                continue

        return jsonify({
            'path': filepath,
            'files': entries,
            'isRoot': False
        })
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def generate_chunked_file(filepath, chunk_size=CHUNK_SIZE):
    """Generator function for chunked file transfer with error handling"""
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        raise

@app.route('/api/download/<path:filepath>')
def download_file(filepath):
    try:
        # Get and validate safe path
        abs_path = get_safe_path(filepath)
        if not abs_path or not os.path.exists(abs_path):
            return jsonify({'error': 'File not found or access denied'}), 404

        filename = os.path.basename(abs_path)
        
        if os.path.isdir(abs_path):
            # Create temporary zip file with thread-safe management
            zip_filename = f"{filename}_{int(time.time())}_{secrets.token_hex(4)}.zip"
            zip_path = os.path.join(TEMP_ZIP_FOLDER, zip_filename)
            
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zipf:
                    for root, dirs, files in os.walk(abs_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if get_safe_path(file_path):  # Security check
                                arcname = os.path.relpath(file_path, abs_path)
                                zipf.write(file_path, arcname)
                
                # Thread-safe addition to temp files
                with temp_zip_files_lock:
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
                
            except Exception as e:
                logger.error(f"Error creating zip: {e}")
                return jsonify({'error': 'Failed to create zip file'}), 500
                
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
        logger.error(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        current_path = request.form.get('path', '')
        
        # Get and validate target directory
        target_dir = get_safe_path(current_path)
        if not target_dir or not os.path.isdir(target_dir):
            return jsonify({'error': 'Invalid target directory'}), 400
        
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        files = request.files.getlist('files')
        uploaded = []
        errors = []
        
        for file in files:
            if file.filename:
                # Sanitize filename
                filename = os.path.basename(file.filename)
                if not filename or filename.startswith('.'):
                    errors.append(f"Invalid filename: {filename}")
                    continue
                    
                save_path = os.path.join(target_dir, filename)
                
                # Additional security check
                if not get_safe_path(save_path):
                    errors.append(f"Access denied for: {filename}")
                    continue
                
                try:
                    file.save(save_path)
                    uploaded.append(filename)
                    logger.info(f"Uploaded: {filename} to {target_dir}")
                except Exception as e:
                    errors.append(f"Failed to upload {filename}: {str(e)}")
                    logger.error(f"Upload failed for {filename}: {e}")

        result = {
            'message': f'Uploaded {len(uploaded)} files',
            'files': uploaded
        }
        if errors:
            result['errors'] = errors
            
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500

@app.route('/api/clipboard', methods=['GET', 'POST'])
def handle_clipboard():
    global clipboard_content
    if request.method == 'GET':
        return jsonify({'content': clipboard_content})
    else:
        try:
            data = request.json
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            new_content = data.get('content', '')
            with clipboard_lock:
                clipboard_content = new_content
                save_clipboard(clipboard_content)
                socketio.emit('clipboard_update', {'text': clipboard_content})
            return jsonify({'message': 'Clipboard updated'})
        except Exception as e:
            logger.error(f"Clipboard update error: {e}")
            return jsonify({'error': 'Clipboard update failed'}), 500

# ---------- Strict Authentication ----------
@app.before_request
def check_auth():
    # Skip auth for static files and socket.io
    if request.path.startswith('/static/') or request.path.startswith('/socket.io/'):
        return
    
    # Skip auth for server-info (needed for initial token validation)
    if request.path == '/api/server-info':
        return
    
    # ALL other routes require token
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        logger.warning(f"Authentication failed for {request.path} from {request.remote_addr}")
        return jsonify({'error': 'Invalid or missing access token'}), 403

# ---------- Server Info ----------
@app.route('/api/server-info')
def server_info():
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

# Serve static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# SocketIO events
@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")
    emit('clipboard_update', {'text': clipboard_content})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('clipboard_update')
def handle_clipboard_update(data):
    global clipboard_content
    try:
        new_content = data.get('text', '')
        with clipboard_lock:
            clipboard_content = new_content
            save_clipboard(clipboard_content)
            emit('clipboard_update', {'text': clipboard_content}, broadcast=True)
    except Exception as e:
        logger.error(f"SocketIO clipboard error: {e}")

# Serve local SocketIO client
@app.route('/socket.io.js')
def serve_socketio():
    return send_file(os.path.join(app.static_folder, 'socket.io.js'))

@app.route('/api/view/<path:filepath>')
def view_file(filepath):
    try:
        token = request.args.get('token')
        if token != AUTH_TOKEN:
            return jsonify({'error': 'Invalid or missing access token'}), 403
        
        abs_path = get_safe_path(filepath)
        if not abs_path or not os.path.exists(abs_path) or os.path.isdir(abs_path):
            return jsonify({'error': 'File not found or is a directory'}), 404

        # For media files, use direct file serving
        media_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mp3', '.wav', '.ogg', '.flac', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        file_ext = os.path.splitext(abs_path)[1].lower()
        
        if file_ext in media_extensions:
            return send_file(abs_path)
        else:
            file_size = os.path.getsize(abs_path)
            response = Response(
                generate_chunked_file(abs_path),
                headers={
                    "Content-Disposition": f'inline; filename="{os.path.basename(abs_path)}"',
                    "Content-Length": str(file_size)
                }
            )
            
            import mimetypes
            mimetype, _ = mimetypes.guess_type(abs_path)
            if mimetype:
                response.headers['Content-Type'] = mimetype
            
            return response
            
    except Exception as e:
        logger.error(f"View file error: {e}")
        return jsonify({'error': 'File view failed'}), 500

# Enhanced cleanup with thread safety
def cleanup():
    """Cleanup temporary files with thread safety"""
    logger.info("Cleaning up temporary files...")
    with temp_zip_files_lock:
        for zip_file in list(temp_zip_files):
            try:
                if os.path.exists(zip_file):
                    os.remove(zip_file)
                    logger.info(f"Removed temporary file: {zip_file}")
            except Exception as e:
                logger.error(f"Failed to remove {zip_file}: {e}")
        temp_zip_files.clear()

# Register cleanup handlers
atexit.register(cleanup)

# Handle graceful shutdown
import signal
def signal_handler(sig, frame):
    logger.info("Received shutdown signal, cleaning up...")
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# Replace with production server setup:
def run_production_server():
    """Run with production-ready server"""
    try:
        # Try eventlet first (better performance)
        try:
            import eventlet
            eventlet.monkey_patch()
            logger.info("🚀 Starting production server with Eventlet...")
            socketio.run(app, host=HOST, port=PORT, debug=False)
            
        except ImportError:
            # Fallback to gevent (modern approach)
            try:
                from gevent import monkey
                monkey.patch_all()
                
                logger.info("🚀 Starting production server with Gevent...")
                # Use Flask-SocketIO's built-in gevent support
                socketio.run(app, host=HOST, port=PORT, debug=False)
                
            except ImportError:
                # Final fallback: warn about development mode
                logger.warning("⚠️  Running in DEVELOPMENT MODE - Install eventlet for production")
                logger.warning("📦 Run: pip install eventlet")
                socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)
                
    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        cleanup()
        sys.exit(1)

if __name__ == '__main__':
    logger.info("🚀 Starting Production LAN File Server...")
    logger.info(f"📁 Home directory: {HOME_PATH}")
    logger.info(f"🔑 Authentication Token: {AUTH_TOKEN}")
    
    # Generate QR code
    if generate_qr_code():
        logger.info(f"✅ QR code saved: {QR_CODE_FILE}")
    else:
        logger.error("❌ Failed to generate QR code")
    
    server_ip = get_ip()
    logger.info(f"🌐 Server starting on http://{server_ip}:{PORT}")
    logger.info("📝 Logs are being written to server.log")
    
    # Start production server
    run_production_server()
import os
import sys
import threading
import time
import webbrowser
import socket
import io
import base64
from pathlib import Path

# Try to import PyQt5, fallback to console mode
try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QTextEdit, QWidget, QMessageBox,
                               QSizePolicy, QDialog, QScrollArea)
    from PyQt5.QtGui import QFont, QPixmap, QImage
    from PyQt5.QtCore import QTimer, Qt, QByteArray
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

class QRCodeDialog(QDialog):
    def __init__(self, qr_image_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LAN File Server - QR Code")
        self.setFixedSize(550, 600)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Scan QR Code to Connect")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # QR Code Image
        qr_label = QLabel()
        qr_pixmap = QPixmap()
        qr_pixmap.loadFromData(qr_image_data)
        qr_label.setPixmap(qr_pixmap)
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setStyleSheet("padding: 20px; background: white; border: 2px solid #ccc;")
        layout.addWidget(qr_label)
        
        # URL
        url_label = QLabel("Or visit the URL directly")
        url_label.setStyleSheet("font-size: 12px; color: #666; padding: 5px;")
        url_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(url_label)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2980b9;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

class ServerManager:
    def __init__(self):
        self.server_thread = None
        self.qr_image_data = None
        self.server_url = None
        self.auth_token = self.generate_auth_token()
        
    def generate_auth_token(self):
        """Generate a secure authentication token"""
        import secrets
        return secrets.token_urlsafe(16)
    
    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '127.0.0.1'
    
    def generate_qr_code(self):
        """Generate QR code with authentication token and return image data"""
        try:
            import qrcode
            ip = self.get_ip()
            self.server_url = f"http://{ip}:8080/?token={self.auth_token}"
            
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(self.server_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to bytes instead of saving to file
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            self.qr_image_data = buffer.getvalue()
            
            print(f"✅ QR code generated for: {self.server_url}")
            return True
        except Exception as e:
            print(f"❌ QR code generation failed: {e}")
            return False
    
    def start_server(self):
        def run_server():
            try:
                # Set the authentication token as environment variable
                os.environ['AUTH_TOKEN'] = self.auth_token
                from server import app, socketio
                print("🚀 Starting LAN File Server...")
                print(f"🔑 Authentication Token: {self.auth_token}")
                socketio.run(app, host='0.0.0.0', port=8080, debug=False, allow_unsafe_werkzeug=True, use_reloader=False)
            except Exception as e:
                print(f"❌ Server error: {e}")
        
        # Generate QR code before starting server
        if self.generate_qr_code():
            print("✅ QR code ready to display")
        else:
            print("❌ Failed to generate QR code")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        time.sleep(2)
        
    def get_server_info(self):
        ip = self.get_ip()
        url = f"http://{ip}:8080/?token={self.auth_token}"
        return {
            'localUrl': f'http://localhost:8080/?token={self.auth_token}',
            'networkUrl': url,
            'ip': ip,
            'url': url,
            'authToken': self.auth_token
        }

if PYQT_AVAILABLE:
    class ServerGUI(QMainWindow):
        def __init__(self, server_manager):
            super().__init__()
            self.server_manager = server_manager
            self.init_ui()
            self.start_server()
            
        def init_ui(self):
            self.setWindowTitle('LAN File Server')
            self.setMinimumSize(700, 600)
            self.resize(800, 700)
            
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            layout.setContentsMargins(25, 25, 25, 25)
            layout.setSpacing(20)
            
            # Header
            header = QLabel('🌐 LAN File Server')
            header.setStyleSheet("""
                QLabel {
                    font-size: 28px;
                    font-weight: bold;
                    color: white;
                    padding: 20px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                              stop:0 #3498db, stop:1 #2c3e50);
                    border-radius: 10px;
                    text-align: center;
                }
            """)
            header.setAlignment(Qt.AlignCenter)
            layout.addWidget(header)
            
            # Status Section
            status_widget = QWidget()
            status_widget.setStyleSheet("""
                QWidget {
                    background: #f8f9fa;
                    border-radius: 8px;
                    padding: 15px;
                    border: 2px solid #e9ecef;
                }
            """)
            status_layout = QVBoxLayout(status_widget)
            
            self.status_label = QLabel('🔄 Starting server...')
            self.status_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #6c757d;
                    padding: 8px;
                }
            """)
            self.status_label.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(self.status_label)
            
            layout.addWidget(status_widget)
            
            # Quick Actions
            actions_group = QLabel('🚀 Quick Actions')
            actions_group.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #2c3e50;
                    padding: 10px 5px;
                }
            """)
            layout.addWidget(actions_group)
            
            # Action Buttons - Four buttons in a grid
            action_layout = QHBoxLayout()
            
            # Button 1: Maximize
            maximize_action_btn = QPushButton('📺 Maximize')
            maximize_action_btn.setStyleSheet("""
                QPushButton {
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 15px 10px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background: #2980b9;
                }
                QPushButton:disabled {
                    background: #95a5a6;
                    color: #7f8c8d;
                }
            """)
            maximize_action_btn.clicked.connect(self.toggle_maximize)
            action_layout.addWidget(maximize_action_btn)
            
            # Button 2: Stop Server
            stop_action_btn = QPushButton('🛑 Stop Server')
            stop_action_btn.setStyleSheet("""
                QPushButton {
                    background: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 15px 10px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background: #c0392b;
                }
                QPushButton:disabled {
                    background: #95a5a6;
                    color: #7f8c8d;
                }
            """)
            stop_action_btn.clicked.connect(self.stop_server)
            action_layout.addWidget(stop_action_btn)
            
            # Button 3: Show QR Code
            self.qr_btn = QPushButton('📱 Show QR Code')
            self.qr_btn.setStyleSheet("""
                QPushButton {
                    background: #e67e22;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 15px 10px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background: #d35400;
                }
                QPushButton:disabled {
                    background: #95a5a6;
                    color: #7f8c8d;
                }
            """)
            self.qr_btn.clicked.connect(self.show_qr_code)
            self.qr_btn.setEnabled(False)
            action_layout.addWidget(self.qr_btn)
            
            # Button 4: Copy URL
            self.copy_btn = QPushButton('📋 Copy URL')
            self.copy_btn.setStyleSheet("""
                QPushButton {
                    background: #9b59b6;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 15px 10px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background: #8e44ad;
                }
                QPushButton:disabled {
                    background: #95a5a6;
                    color: #7f8c8d;
                }
            """)
            self.copy_btn.clicked.connect(self.copy_url)
            self.copy_btn.setEnabled(False)
            action_layout.addWidget(self.copy_btn)
            
            layout.addLayout(action_layout)
            
            # Server Info
            info_group = QLabel('📊 Server Information')
            info_group.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #2c3e50;
                    padding: 10px 5px;
                }
            """)
            layout.addWidget(info_group)
            
            self.info_text = QTextEdit()
            self.info_text.setStyleSheet("""
                QTextEdit {
                    background: white;
                    border: 2px solid #bdc3c7;
                    border-radius: 10px;
                    padding: 20px;
                    font-family: 'Consolas', monospace;
                    font-size: 13px;
                    color: #2c3e50;
                    line-height: 1.4;
                }
            """)
            self.info_text.setReadOnly(True)
            self.info_text.setMinimumHeight(180)
            layout.addWidget(self.info_text)
            
            # Footer
            footer = QLabel('💡 Files served from home directory • Close window to stop server')
            footer.setStyleSheet("""
                QLabel {
                    color: #7f8c8d;
                    font-size: 12px;
                    padding: 15px;
                    text-align: center;
                    background: #ecf0f1;
                    border-radius: 8px;
                    margin-top: 10px;
                }
            """)
            footer.setAlignment(Qt.AlignCenter)
            layout.addWidget(footer)
            
            # Make layout expandable
            layout.setStretchFactor(self.info_text, 1)
            
        def toggle_maximize(self):
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
                
        def start_server(self):
            self.server_manager.start_server()
            QTimer.singleShot(1000, self.check_server)
            
        def check_server(self):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 8080))
                sock.close()
                
                if result == 0:
                    self.status_label.setText('✅ Server running on port 8080')
                    self.status_label.setStyleSheet("""
                        QLabel {
                            font-size: 16px;
                            font-weight: bold;
                            color: #27ae60;
                            padding: 8px;
                        }
                    """)
                    self.qr_btn.setEnabled(True)
                    self.copy_btn.setEnabled(True)
                    self.update_server_info()
                else:
                    QTimer.singleShot(1000, self.check_server)
            except:
                QTimer.singleShot(1000, self.check_server)
                
        def update_server_info(self):
            info = self.server_manager.get_server_info()
            text = f"""🌐 SERVER INFORMATION

📍 Local URL: {info['localUrl']}
🌍 Network URL: {info['networkUrl']}
📡 IP Address: {info['ip']}
🔑 Auth Token: {info['authToken']}

🔒 Secure token authentication enabled
📱 QR code ready to share

💡 To access from other devices:
   1. Ensure they're on the same network
   2. Scan the QR code or visit the URL with token
   3. Start sharing files instantly!

⚡ Features:
   • Fast file transfers (16MB chunks)
   • Real-time clipboard sharing
   • Mobile-friendly interface
   • Secure token-based access"""
            
            self.info_text.setText(text)
            
        def show_qr_code(self):
            if self.server_manager.qr_image_data:
                qr_dialog = QRCodeDialog(self.server_manager.qr_image_data, self)
                qr_dialog.exec_()
            else:
                QMessageBox.warning(self, "QR Code", 
                                  "QR code is not available. The server may not have started properly.")
                
        def copy_url(self):
            info = self.server_manager.get_server_info()
            clipboard = QApplication.clipboard()
            clipboard.setText(info['networkUrl'])
            QMessageBox.information(self, "Copied", "URL copied to clipboard!")
            
        def show_token(self):
            info = self.server_manager.get_server_info()
            QMessageBox.information(self, "Authentication Token", 
                                  f"Your authentication token is:\n\n{info['authToken']}\n\n"
                                  f"Share this with trusted users to grant access.")
            
        def refresh_server(self):
            self.status_label.setText('🔄 Refreshing server...')
            self.status_label.setStyleSheet("""
                QLabel {
                    font-size: 16px;
                    font-weight: bold;
                    color: #6c757d;
                    padding: 8px;
                }
            """)
            self.qr_btn.setEnabled(False)
            self.copy_btn.setEnabled(False)
            self.token_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            
            # Regenerate token and restart
            self.server_manager.auth_token = self.server_manager.generate_auth_token()
            self.server_manager.start_server()
            QTimer.singleShot(1000, self.check_server)
                
        def stop_server(self):
            reply = QMessageBox.question(self, 'Stop Server', 
                                       'Are you sure you want to stop the server?',
                                       QMessageBox.Yes | QMessageBox.No, 
                                       QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                QApplication.quit()
                
        def closeEvent(self, event):
            reply = QMessageBox.question(self, 'Quit', 
                                       'Are you sure you want to stop the server and quit?',
                                       QMessageBox.Yes | QMessageBox.No, 
                                       QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()

    def run_gui():
        app = QApplication(sys.argv)
        
        # Set modern font
        font = QFont("Segoe UI", 10)
        app.setFont(font)
        
        server_manager = ServerManager()
        window = ServerGUI(server_manager)
        window.show()
        
        sys.exit(app.exec_())

else:
    def run_console():
        server_manager = ServerManager()
        server_manager.start_server()
        
        info = server_manager.get_server_info()
        print("=" * 60)
        print("🚀 LAN File Server Started!")
        print("=" * 60)
        print(f"📍 Local URL: {info['localUrl']}")
        print(f"🌍 Network URL: {info['networkUrl']}")
        print(f"📡 IP Address: {info['ip']}")
        print(f"🔑 Auth Token: {info['authToken']}")
        print("=" * 60)
        print("📱 QR code generated in application")
        print("🔒 Secure token authentication enabled")
        print("=" * 60)
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 60)
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping server...")

if __name__ == '__main__':
    if PYQT_AVAILABLE and '--console' not in sys.argv:
        run_gui()
    else:
        run_console()
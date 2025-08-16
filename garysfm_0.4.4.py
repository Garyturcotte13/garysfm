#!/usr/bin/env python3
"""
Gary's Simple File Manager (garysfm) - Cross-platform Edition
Version: 0.4.4

A cross-platform file manager built with PyQt5, supporting Windows, macOS, and Linux.

CROSS-PLATFORM SETUP:
=====================

Required dependencies:
- Python 3.6+
- PyQt5 (pip install PyQt5)

Optional dependencies for enhanced functionality:
- send2trash (pip install send2trash) - Cross-platform trash/recycle bin support
- winshell (Windows only: pip install winshell) - Enhanced Windows Recycle Bin support

Platform-specific notes:

Windows:
- Terminal support: Windows Terminal, Command Prompt, PowerShell
- File operations: Full Windows Explorer integration
- Trash support: Recycle Bin via PowerShell or winshell

macOS:
- Terminal support: Terminal.app via AppleScript
- File operations: Finder integration
- Trash support: Trash via AppleScript
- System requirements: macOS 10.10+

Linux:
- Terminal support: Auto-detection of gnome-terminal, konsole, xfce4-terminal, etc.
- File operations: XDG-compliant file managers (nautilus, dolphin, thunar, etc.)
- Trash support: gio trash command (usually pre-installed)
- Desktop environment integration via XDG utilities

Usage:
python garysfm_0.4.4.py

Author: turkokards
License: MIT
"""

import sys
import os
import shutil
import shlex
import subprocess
import json
import webbrowser
import mimetypes
import datetime
import platform
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QFileSystemModel, QListView, QTableView,
    QVBoxLayout, QWidget, QHBoxLayout, QMessageBox, QGridLayout, QSplitter,
    QSizePolicy, QLabel, QAction, QPushButton, QScrollArea, QMenu, QInputDialog, QFileIconProvider,
    QDialog, QLineEdit, QRadioButton, QButtonGroup, QTextEdit, QCheckBox, QStatusBar, QShortcut,
    QComboBox, QToolBar, QFrame, QSlider, QSpinBox, QTabWidget, QPlainTextEdit, QHeaderView, QProgressBar,
    QGroupBox, QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem, QProgressDialog, QStyle
)
from PyQt5.QtCore import QDir, Qt, pyqtSignal, QFileInfo, QPoint, QRect, QTimer, QThread, QStringListModel, QSortFilterProxyModel, QModelIndex, QSize, QMimeData, QUrl
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QKeySequence, QFont, QTextDocument, QSyntaxHighlighter, QTextCharFormat, QStandardItemModel, QStandardItem, QColor, QDesktopServices

# Cross-platform utility functions
class PlatformUtils:
    """
    Cross-platform utility functions for better OS compatibility
    
    CROSS-PLATFORM IMPROVEMENTS MADE:
    =================================
    
    1. Platform Detection:
       - Unified platform detection using platform.system()
       - Support for Windows, macOS, Linux, and other Unix-like systems
       
    2. File Operations:
       - Cross-platform file opening with default applications
       - Platform-specific file manager reveal functionality
       - Improved safety checks for different file systems
       
    3. Terminal Integration:
       - Windows: Support for Windows Terminal, cmd, PowerShell
       - macOS: Terminal.app integration via AppleScript
       - Linux: Auto-detection of common terminal emulators
       
    4. Keyboard Shortcuts:
       - macOS: Cmd-based shortcuts (Cmd+C, Cmd+V, etc.)
       - Windows/Linux: Ctrl-based shortcuts
       - Platform-appropriate window management shortcuts
       
    5. Trash/Recycle Bin Support:
       - Windows: PowerShell-based Recycle Bin support
       - macOS: AppleScript Finder integration
       - Linux: gio trash command support
       - Fallback to send2trash library if available
       
    6. Path Handling:
       - Cross-platform user directory detection
       - XDG compliance on Linux for Documents, Downloads, Desktop
       - Windows and macOS standard folder locations
       
    7. File System Filtering:
       - macOS: Filter out .DS_Store and resource fork files
       - Windows: Filter out Thumbs.db and desktop.ini
       - Linux: Standard hidden file handling
       
    8. Application Integration:
       - High DPI support for all platforms
       - Platform-specific application properties
       - Proper window management and taskbar integration
    """
    
    @staticmethod
    def get_platform():
        """Get the current platform in a standardized way"""
        system = platform.system().lower()
        if system == 'windows':
            return 'windows'
        elif system == 'darwin':
            return 'macos'
        elif system in ('linux', 'freebsd', 'openbsd', 'netbsd'):
            return 'linux'
        else:
            return 'unknown'
    
    @staticmethod
    def is_windows():
        """Check if running on Windows"""
        return PlatformUtils.get_platform() == 'windows'
    
    @staticmethod
    def is_macos():
        """Check if running on macOS"""
        return PlatformUtils.get_platform() == 'macos'
    
    @staticmethod
    def is_linux():
        """Check if running on Linux/Unix"""
        return PlatformUtils.get_platform() == 'linux'
    
    @staticmethod
    def get_modifier_key():
        """Get the primary modifier key for the platform"""
        return "Cmd" if PlatformUtils.is_macos() else "Ctrl"
    
    @staticmethod
    def get_alt_modifier_key():
        """Get the alternative modifier key for the platform"""
        return "Cmd" if PlatformUtils.is_macos() else "Alt"
    
    @staticmethod
    def get_navigation_modifier():
        """Get the navigation modifier key (for back/forward)"""
        return "Cmd" if PlatformUtils.is_macos() else "Alt"
    
    @staticmethod
    def open_file_with_default_app(file_path):
        """Open a file with the default system application"""
        try:
            if PlatformUtils.is_windows():
                os.startfile(file_path)
            elif PlatformUtils.is_macos():
                subprocess.run(["open", file_path], check=True)
            else:  # Linux/Unix
                subprocess.run(["xdg-open", file_path], check=True)
            return True
        except (subprocess.CalledProcessError, OSError, FileNotFoundError) as e:
            print(f"Error opening file {file_path}: {e}")
            return False
    
    @staticmethod
    def reveal_in_file_manager(file_path):
        """Reveal/show a file or folder in the system file manager"""
        try:
            if PlatformUtils.is_windows():
                # Use Windows Explorer to select the file
                subprocess.run(["explorer", "/select,", file_path], check=True)
            elif PlatformUtils.is_macos():
                # Use Finder to reveal the file
                subprocess.run(["open", "-R", file_path], check=True)
            else:  # Linux/Unix
                # Try different file managers
                file_managers = [
                    ["nautilus", "--select", file_path],  # GNOME
                    ["dolphin", "--select", file_path],   # KDE
                    ["thunar", file_path],                # XFCE
                    ["pcmanfm", file_path],               # LXDE
                    ["xdg-open", os.path.dirname(file_path)]  # Fallback
                ]
                
                for fm_cmd in file_managers:
                    try:
                        subprocess.run(fm_cmd, check=True)
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
            return True
        except Exception as e:
            print(f"Error revealing file {file_path}: {e}")
            return False
    
    @staticmethod
    def open_terminal_at_path(path):
        """Open system terminal at the specified path"""
        try:
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            if PlatformUtils.is_windows():
                # Try Windows Terminal first, then fall back to cmd
                try:
                    subprocess.Popen(["wt", "-d", path], shell=True)
                except FileNotFoundError:
                    # Fall back to Command Prompt
                    subprocess.Popen(["cmd"], cwd=path, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            elif PlatformUtils.is_macos():
                # Use AppleScript to open Terminal
                script = f'tell application "Terminal" to do script "cd {shlex.quote(path)}"'
                subprocess.run(["osascript", "-e", script], check=True)
            else:  # Linux/Unix
                # Try different terminal emulators
                terminals = [
                    ["gnome-terminal", "--working-directory", path],
                    ["konsole", "--workdir", path],
                    ["xfce4-terminal", "--working-directory", path],
                    ["lxterminal", "--working-directory", path],
                    ["mate-terminal", "--working-directory", path],
                    ["terminator", "--working-directory", path],
                    ["xterm", "-cd", path],
                    ["urxvt", "-cd", path]
                ]
                
                for term_cmd in terminals:
                    try:
                        subprocess.Popen(term_cmd, cwd=path)
                        break
                    except FileNotFoundError:
                        continue
                else:
                    raise FileNotFoundError("No suitable terminal emulator found")
            return True
        except Exception as e:
            print(f"Error opening terminal at {path}: {e}")
            return False
    
    @staticmethod
    def get_trash_command():
        """Get the appropriate command to move files to trash"""
        if PlatformUtils.is_windows():
            return None  # Will use send2trash library or manual implementation
        elif PlatformUtils.is_macos():
            return ["trash"]  # Requires 'trash' command to be installed
        else:  # Linux
            return ["gio", "trash"]  # Modern Linux systems
    
    @staticmethod
    def get_home_directory():
        """Get user's home directory in a cross-platform way"""
        return os.path.expanduser("~")
    
    @staticmethod
    def get_documents_directory():
        """Get user's documents directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Documents")
        elif PlatformUtils.is_macos():
            return os.path.join(home, "Documents")
        else:  # Linux
            # Try XDG user dirs first
            try:
                result = subprocess.run(["xdg-user-dir", "DOCUMENTS"], 
                                      capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Documents")
    
    @staticmethod
    def get_downloads_directory():
        """Get user's downloads directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Downloads")
        elif PlatformUtils.is_macos():
            return os.path.join(home, "Downloads")
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "DOWNLOAD"], 
                                      capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Downloads")
    
    @staticmethod
    def get_desktop_directory():
        """Get user's desktop directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Desktop")
        elif PlatformUtils.is_macos():
            return os.path.join(home, "Desktop")
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "DESKTOP"], 
                                      capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Desktop")

class ClipboardHistoryManager:
    """Advanced clipboard manager with history tracking"""
    def __init__(self):
        self.history = []
        self.max_history = 50
        self.current_operation = None  # 'cut' or 'copy'
        self.current_paths = []
    
    def add_to_history(self, operation, paths, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        entry = {
            'operation': operation,
            'paths': paths.copy(),
            'timestamp': timestamp,
            'valid': all(os.path.exists(path) for path in paths)
        }
        
        self.history.insert(0, entry)
        if len(self.history) > self.max_history:
            self.history.pop()
    
    def set_current_operation(self, operation, paths):
        self.current_operation = operation
        self.current_paths = paths.copy()
        self.add_to_history(operation, paths)
    
    def get_current_operation(self):
        return self.current_operation, self.current_paths
    
    def clear_current(self):
        self.current_operation = None
        self.current_paths = []
    
    def get_history(self):
        return self.history

class PreviewPane(QWidget):
    """File preview pane with support for text, images, and basic info"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.current_file = None
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Header
        self.header_label = QLabel("Preview")
        self.header_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.header_label)
        
        # Tabbed preview area
        self.preview_tabs = QTabWidget()
        
        # Content tab
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        
        # Preview area (for images, text, etc.)
        self.preview_area = QScrollArea()
        self.preview_content = QLabel()
        self.preview_content.setAlignment(Qt.AlignCenter)
        self.preview_content.setWordWrap(True)
        self.preview_area.setWidget(self.preview_content)
        self.content_layout.addWidget(self.preview_area)
        
        # Text editor for text files
        self.text_editor = QPlainTextEdit()
        self.text_editor.setReadOnly(True)
        self.text_editor.hide()
        self.content_layout.addWidget(self.text_editor)
        
        self.content_widget.setLayout(self.content_layout)
        self.preview_tabs.addTab(self.content_widget, "Content")
        
        # Properties tab
        self.properties_widget = QWidget()
        self.properties_layout = QVBoxLayout()
        self.properties_text = QTextEdit()
        self.properties_text.setReadOnly(True)
        self.properties_layout.addWidget(self.properties_text)
        self.properties_widget.setLayout(self.properties_layout)
        self.preview_tabs.addTab(self.properties_widget, "Properties")
        
        layout.addWidget(self.preview_tabs)
        self.setLayout(layout)
    
    def preview_file(self, file_path):
        if not os.path.exists(file_path):
            self.clear_preview()
            return
            
        self.current_file = file_path
        file_info = QFileInfo(file_path)
        
        # Update header
        self.header_label.setText(f"Preview: {file_info.fileName()}")
        
        # Update properties
        self.update_properties(file_info)
        
        # Update content preview
        if file_info.isFile():
            self.update_content_preview(file_path)
        else:
            self.update_folder_preview(file_path)
    
    def update_content_preview(self, file_path):
        self.text_editor.hide()
        self.preview_area.show()
        
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type and mime_type.startswith('image/'):
            self.preview_image(file_path)
        elif mime_type and mime_type.startswith('text/'):
            self.preview_text_file(file_path)
        else:
            self.preview_generic_file(file_path)
    
    def preview_image(self, file_path):
        try:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                # Scale image to fit preview area
                scaled_pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_content.setPixmap(scaled_pixmap)
            else:
                self.preview_content.setText("Cannot preview this image format")
        except Exception as e:
            self.preview_content.setText(f"Error previewing image: {str(e)}")
    
    def preview_text_file(self, file_path):
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 1024 * 1024:  # 1MB limit
                self.preview_content.setText("File too large to preview")
                return
                
            self.preview_area.hide()
            self.text_editor.show()
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Limit to first 10000 characters
                if len(content) == 10000:
                    content += "\n\n... (truncated)"
                self.text_editor.setPlainText(content)
        except Exception as e:
            self.preview_content.setText(f"Error previewing text: {str(e)}")
    
    def preview_generic_file(self, file_path):
        file_info = QFileInfo(file_path)
        info_text = f"File: {file_info.fileName()}\n"
        info_text += f"Size: {self.format_size(file_info.size())}\n"
        info_text += f"Type: {file_info.suffix().upper() if file_info.suffix() else 'Unknown'}\n"
        info_text += "\nPreview not available for this file type"
        self.preview_content.setText(info_text)
    
    def update_folder_preview(self, folder_path):
        self.text_editor.hide()
        self.preview_area.show()
        
        try:
            items = os.listdir(folder_path)
            file_count = sum(1 for item in items if os.path.isfile(os.path.join(folder_path, item)))
            dir_count = sum(1 for item in items if os.path.isdir(os.path.join(folder_path, item)))
            
            info_text = f"Folder: {os.path.basename(folder_path)}\n\n"
            info_text += f"Contains:\n"
            info_text += f"  {dir_count} folders\n"
            info_text += f"  {file_count} files\n"
            info_text += f"  {len(items)} total items"
            
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading folder: {str(e)}")
    
    def update_properties(self, file_info):
        props = []
        props.append(f"Name: {file_info.fileName()}")
        props.append(f"Path: {file_info.absoluteFilePath()}")
        props.append(f"Size: {self.format_size(file_info.size())}")
        props.append(f"Modified: {file_info.lastModified().toString()}")
        props.append(f"Type: {file_info.suffix().upper() if file_info.suffix() else 'Folder' if file_info.isDir() else 'File'}")
        
        if file_info.isFile():
            mime_type, _ = mimetypes.guess_type(file_info.absoluteFilePath())
            if mime_type:
                props.append(f"MIME Type: {mime_type}")
        
        self.properties_text.setText("\n".join(props))
    
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def clear_preview(self):
        self.header_label.setText("Preview")
        self.preview_content.clear()
        self.text_editor.clear()
        self.properties_text.clear()
        self.current_file = None

class SearchFilterWidget(QWidget):
    """Search and filter widget with advanced filtering options"""
    searchRequested = pyqtSignal(str, dict)  # search_text, filter_options
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Search input
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search terms...")
        self.search_input.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_button)
        
        layout.addLayout(search_layout)
        
        # Filter options
        filter_group = QFrame()
        filter_group.setFrameStyle(QFrame.StyledPanel)
        filter_layout = QVBoxLayout()
        
        filter_layout.addWidget(QLabel("Filters:"))
        
        # File type filter
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Files Only", "Folders Only", "Images", "Documents", "Videos", "Audio"])
        self.type_combo.currentTextChanged.connect(self.on_filter_changed)
        type_layout.addWidget(self.type_combo)
        filter_layout.addLayout(type_layout)
        
        # Size filter
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["Any Size", "Small (<1MB)", "Medium (1-10MB)", "Large (10-100MB)", "Very Large (>100MB)"])
        self.size_combo.currentTextChanged.connect(self.on_filter_changed)
        size_layout.addWidget(self.size_combo)
        filter_layout.addLayout(size_layout)
        
        # Date filter
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Modified:"))
        self.date_combo = QComboBox()
        self.date_combo.addItems(["Any Time", "Today", "This Week", "This Month", "This Year"])
        self.date_combo.currentTextChanged.connect(self.on_filter_changed)
        date_layout.addWidget(self.date_combo)
        filter_layout.addLayout(date_layout)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        self.setLayout(layout)
    
    def on_search_changed(self):
        if len(self.search_input.text()) >= 2 or len(self.search_input.text()) == 0:
            self.perform_search()
    
    def on_filter_changed(self):
        self.perform_search()
    
    def perform_search(self):
        search_text = self.search_input.text()
        filter_options = {
            'type': self.type_combo.currentText(),
            'size': self.size_combo.currentText(),
            'date': self.date_combo.currentText()
        }
        self.searchRequested.emit(search_text, filter_options)

class ViewModeManager:
    """Manages different view modes for the file display"""
    ICON_VIEW = "icon"
    LIST_VIEW = "list"
    DETAIL_VIEW = "detail"
    
    def __init__(self):
        self.current_mode = self.ICON_VIEW
        self.view_widgets = {}
    
    def set_mode(self, mode):
        if mode in [self.ICON_VIEW, self.LIST_VIEW, self.DETAIL_VIEW]:
            self.current_mode = mode
    
    def get_mode(self):
        return self.current_mode

class IconWidget(QWidget):
    clicked = pyqtSignal(str, object)  # Pass the event modifiers
    doubleClicked = pyqtSignal(str)
    rightClicked = pyqtSignal(str, QPoint)

    def __init__(self, file_name, full_path, is_dir, thumbnail_size=64, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.full_path = full_path
        self.is_dir = is_dir
        self.thumbnail_size = thumbnail_size
        self.dark_mode = False  # Default value, will be updated by parent
        
        layout = QVBoxLayout()
        # Optimize spacing for compact layout
        layout.setSpacing(1)  # Minimal spacing between icon and label
        layout.setContentsMargins(2, 2, 2, 2)  # Minimal margins
        
        # Create icon or thumbnail
        pixmap = self.create_icon_or_thumbnail(full_path, is_dir)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        
        # Create label with filename
        self.label = QLabel(file_name)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        # Make the text smaller and more compact
        font = self.label.font()
        font.setPointSize(8)  # Smaller font for more compact layout
        self.label.setFont(font)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setToolTip(full_path)
        self.setStyleSheet("QWidget { border: 2px solid transparent; }")

    def update_style_for_theme(self, dark_mode):
        """Update the widget style based on the current theme"""
        self.dark_mode = dark_mode
        if dark_mode:
            self.label.setStyleSheet("QLabel { color: #ffffff; }")
        else:
            self.label.setStyleSheet("")

    def create_icon_or_thumbnail(self, full_path, is_dir):
        """Create either a file icon or an image thumbnail"""
        size = self.thumbnail_size
        
        # Create a consistent-sized frame for all icons
        framed_pixmap = QPixmap(size, size)
        framed_pixmap.fill(Qt.transparent)
        
        painter = QPainter(framed_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            if is_dir:
                # Create folder preview with thumbnails
                folder_preview = self.create_folder_preview(full_path, size)
                painter.drawPixmap(0, 0, folder_preview)
            else:
                # Check if it's an image file with cross-platform considerations
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'}
                # Add SVG support with platform-specific handling
                if not PlatformUtils.is_macos():
                    image_extensions.add('.svg')
                
                file_ext = os.path.splitext(full_path)[1].lower()
                
                if file_ext in image_extensions and self.is_safe_image_file(full_path):
                    try:
                        # Try to create thumbnail from image
                        original_pixmap = QPixmap(full_path)
                        if not original_pixmap.isNull() and original_pixmap.width() > 0 and original_pixmap.height() > 0:
                            # Scale to thumbnail size while maintaining aspect ratio
                            thumbnail = original_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            
                            # Center the thumbnail
                            x = (size - thumbnail.width()) // 2
                            y = (size - thumbnail.height()) // 2
                            painter.drawPixmap(x, y, thumbnail)
                            
                            # Draw a subtle border around the thumbnail
                            pen = QPen(Qt.lightGray, 1)
                            painter.setPen(pen)
                            painter.drawRect(x, y, thumbnail.width() - 1, thumbnail.height() - 1)
                        else:
                            # Fall back to default file icon if image can't be loaded
                            self.draw_default_file_icon(painter, full_path, size)
                    except Exception:
                        # Fall back to default file icon if thumbnail creation fails
                        self.draw_default_file_icon(painter, full_path, size)
                else:
                    # Use default file icon for non-images
                    self.draw_default_file_icon(painter, full_path, size)
        except Exception:
            # Ultimate fallback: draw a simple generic icon
            self.draw_generic_file_icon(painter, size, is_dir)
        
        painter.end()
        return framed_pixmap

    def is_safe_image_file(self, file_path):
        """Check if the file is safe to load as an image on the current platform"""
        try:
            # Check file size - avoid very large files that could cause memory issues
            if os.path.getsize(file_path) > 50 * 1024 * 1024:  # 50MB limit
                return False
            
            # Platform-specific safety checks
            if PlatformUtils.is_macos():
                # Skip files with resource forks or other macOS-specific attributes
                if file_path.endswith('.DS_Store') or '._' in os.path.basename(file_path):
                    return False
                
                # Check if file is readable
                if not os.access(file_path, os.R_OK):
                    return False
            elif PlatformUtils.is_windows():
                # Windows-specific checks
                # Skip system files and thumbnails
                filename = os.path.basename(file_path).lower()
                if filename in ('thumbs.db', 'desktop.ini'):
                    return False
            else:  # Linux/Unix
                # Unix-specific checks
                if not os.access(file_path, os.R_OK):
                    return False
            
            return True
        except Exception:
            return False

    def draw_default_file_icon(self, painter, full_path, size):
        """Draw the default system file icon"""
        try:
            icon_provider = QFileIconProvider()
            icon = icon_provider.icon(QFileInfo(full_path))
            
            # Ensure icon is valid before using
            if not icon.isNull():
                file_pixmap = icon.pixmap(size, size)
                if not file_pixmap.isNull() and file_pixmap.width() > 0 and file_pixmap.height() > 0:
                    # Center the file icon
                    x = (size - file_pixmap.width()) // 2
                    y = (size - file_pixmap.height()) // 2
                    painter.drawPixmap(x, y, file_pixmap)
                    return
        except Exception:
            pass
        
        # If all else fails, draw a generic icon
        self.draw_generic_file_icon(painter, size, False)

    def draw_generic_file_icon(self, painter, size, is_dir):
        """Draw a simple generic icon when system icons fail"""
        try:
            # Set colors based on current theme
            if self.dark_mode:
                border_color = Qt.white
                fill_color = Qt.darkGray
            else:
                border_color = Qt.black
                fill_color = Qt.lightGray
            
            pen = QPen(border_color, 2)
            painter.setPen(pen)
            painter.setBrush(fill_color)
            
            if is_dir:
                # Draw a simple folder shape
                rect_height = size * 0.6
                rect_width = size * 0.8
                x = (size - rect_width) // 2
                y = (size - rect_height) // 2 + size * 0.1
                
                # Draw folder tab
                tab_width = rect_width * 0.3
                tab_height = rect_height * 0.2
                painter.drawRect(int(x), int(y - tab_height), int(tab_width), int(tab_height))
                
                # Draw folder body
                painter.drawRect(int(x), int(y), int(rect_width), int(rect_height))
            else:
                # Draw a simple file shape
                rect_height = size * 0.7
                rect_width = size * 0.6
                x = (size - rect_width) // 2
                y = (size - rect_height) // 2
                
                # Draw file rectangle
                painter.drawRect(int(x), int(y), int(rect_width), int(rect_height))
                
                # Draw corner fold
                fold_size = rect_width * 0.2
                painter.drawLine(int(x + rect_width - fold_size), int(y),
                               int(x + rect_width), int(y + fold_size))
        except Exception:
            # Ultimate fallback: just draw a simple rectangle
            painter.setPen(QPen(Qt.gray, 1))
            painter.drawRect(size//4, size//4, size//2, size//2)

    def create_folder_preview(self, folder_path, size):
        """Create a folder icon with preview thumbnails of images inside"""
        preview_pixmap = QPixmap(size, size)
        preview_pixmap.fill(Qt.transparent)
        
        painter = QPainter(preview_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Start with the default folder icon as background
        try:
            icon_provider = QFileIconProvider()
            folder_icon = icon_provider.icon(QFileIconProvider.Folder)
            
            if not folder_icon.isNull():
                folder_pixmap = folder_icon.pixmap(size, size)
                if not folder_pixmap.isNull() and folder_pixmap.width() > 0 and folder_pixmap.height() > 0:
                    # Center and draw the folder icon
                    x = (size - folder_pixmap.width()) // 2
                    y = (size - folder_pixmap.height()) // 2
                    painter.drawPixmap(x, y, folder_pixmap)
                else:
                    # Draw generic folder if system icon fails
                    self.draw_generic_file_icon(painter, size, True)
            else:
                self.draw_generic_file_icon(painter, size, True)
        except Exception:
            self.draw_generic_file_icon(painter, size, True)
        
        # Try to find image files in the folder for preview
        try:
            # Platform-specific image extensions for folder previews
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
            # Add more extensions for non-macOS systems
            if not PlatformUtils.is_macos():
                image_extensions.update({'.tiff', '.tif', '.webp', '.ico'})
            
            image_files = []
            
            # Get first few image files from the folder
            try:
                files = os.listdir(folder_path)
                # Platform-specific file filtering
                if PlatformUtils.is_macos():
                    files = [f for f in files if not f.startswith('.') and not f.startswith('._')]
                elif PlatformUtils.is_windows():
                    files = [f for f in files if f.lower() not in ('thumbs.db', 'desktop.ini')]
                else:  # Linux/Unix
                    files = [f for f in files if not f.startswith('.')]
                
                for file_name in files:
                    if len(image_files) >= 4:  # Limit to 4 images max
                        break
                    file_ext = os.path.splitext(file_name)[1].lower()
                    if file_ext in image_extensions:
                        file_path = os.path.join(folder_path, file_name)
                        if os.path.isfile(file_path) and self.is_safe_image_file(file_path):
                            image_files.append(file_path)
            except (OSError, PermissionError):
                # If we can't read the folder, just show the folder icon
                painter.end()
                return preview_pixmap
            
            # If we found images, create small previews
            if image_files:
                preview_size = max(8, size // 4)  # Ensure minimum size, each preview is 1/4 the size
                positions = [
                    (size - preview_size - 2, 2),  # Top right
                    (size - preview_size - 2, preview_size + 4),  # Middle right
                    (size - preview_size * 2 - 4, 2),  # Top, second from right
                    (size - preview_size * 2 - 4, preview_size + 4)  # Middle, second from right
                ]
                
                for i, img_path in enumerate(image_files[:4]):
                    try:
                        img_pixmap = QPixmap(img_path)
                        if not img_pixmap.isNull() and img_pixmap.width() > 0 and img_pixmap.height() > 0:
                            # Scale to preview size
                            thumbnail = img_pixmap.scaled(preview_size, preview_size, 
                                                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            
                            # Create a small frame for the preview
                            preview_frame = QPixmap(preview_size, preview_size)
                            preview_frame.fill(Qt.white)
                            
                            frame_painter = QPainter(preview_frame)
                            frame_painter.setRenderHint(QPainter.Antialiasing)
                            
                            # Center thumbnail in frame
                            thumb_x = (preview_size - thumbnail.width()) // 2
                            thumb_y = (preview_size - thumbnail.height()) // 2
                            frame_painter.drawPixmap(thumb_x, thumb_y, thumbnail)
                            
                            # Draw border
                            pen = QPen(Qt.darkGray, 1)
                            frame_painter.setPen(pen)
                            frame_painter.drawRect(0, 0, preview_size - 1, preview_size - 1)
                            frame_painter.end()
                            
                            # Draw the preview on the folder icon
                            pos_x, pos_y = positions[i]
                            painter.drawPixmap(pos_x, pos_y, preview_frame)
                    except Exception:
                        continue  # Skip this image if there's an error
        except Exception:
            pass  # If we can't read the folder, just show the regular folder icon
        
        painter.end()
        return preview_pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.full_path, event.modifiers())
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self.full_path, event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.full_path)

class IconContainer(QWidget):
    emptySpaceClicked = pyqtSignal()
    emptySpaceRightClicked = pyqtSignal(QPoint)
    selectionChanged = pyqtSignal(list)  # Emit list of selected paths

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout()
        # Add 10 pixels spacing between tiles
        layout.setSpacing(10)  # 10 pixels spacing between icons
        layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins
        layout.setSizeConstraint(QGridLayout.SetMinAndMaxSize)
        self.setLayout(layout)
        self.drag_start = None
        self.drag_end = None
        self.selection_rect = QRect()
        self.is_dragging = False
        self.selected_widgets = set()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if click was on empty space (not on a widget)
            clicked_widget = self.childAt(event.pos())
            if clicked_widget is None or clicked_widget == self:
                # Click was on empty space
                self.drag_start = event.pos()
                self.is_dragging = True
                # If not holding Ctrl, clear previous selection
                if not (event.modifiers() & Qt.ControlModifier):
                    self.clear_selection()
                self.emptySpaceClicked.emit()
            else:
                # Click was on a widget, let it handle the event
                super().mousePressEvent(event)
        elif event.button() == Qt.RightButton:
            # Check if right-click was on empty space
            clicked_widget = self.childAt(event.pos())
            if clicked_widget is None or clicked_widget == self:
                self.emptySpaceRightClicked.emit(event.globalPos())
            else:
                # Right-click was on a widget, let it handle the event
                super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.drag_start:
            self.drag_end = event.pos()
            self.selection_rect = QRect(self.drag_start, self.drag_end).normalized()
            self.update_selection()
            self.update()  # Trigger repaint

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.drag_start = None
            self.drag_end = None
            self.update()  # Clear selection rectangle

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_dragging and self.selection_rect.isValid():
            painter = QPainter(self)
            pen = QPen(Qt.blue, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect)

    def update_selection(self):
        layout = self.layout()
        newly_selected = set()
        
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                widget_rect = widget.geometry()
                
                if self.selection_rect.intersects(widget_rect):
                    newly_selected.add(widget)
                    widget.setStyleSheet("QWidget { border: 2px solid #0078d7; background-color: rgba(0, 120, 215, 0.2); }")
                elif widget not in self.selected_widgets:
                    widget.setStyleSheet("QWidget { border: 2px solid transparent; }")
        
        # Update selected widgets
        self.selected_widgets = newly_selected
        
        # Emit selection changed signal
        selected_paths = [w.full_path for w in self.selected_widgets]
        self.selectionChanged.emit(selected_paths)

    def clear_selection(self):
        layout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                widget.setStyleSheet("QWidget { border: 2px solid transparent; }")
        self.selected_widgets.clear()
        self.selectionChanged.emit([])

    def add_to_selection(self, widget):
        self.selected_widgets.add(widget)
        widget.setStyleSheet("QWidget { border: 2px solid #0078d7; background-color: rgba(0, 120, 215, 0.2); }")
        selected_paths = [w.full_path for w in self.selected_widgets]
        self.selectionChanged.emit(selected_paths)

    def remove_from_selection(self, widget):
        if widget in self.selected_widgets:
            self.selected_widgets.remove(widget)
            widget.setStyleSheet("QWidget { border: 2px solid transparent; }")
            selected_paths = [w.full_path for w in self.selected_widgets]
            self.selectionChanged.emit(selected_paths)

    def add_to_selection_by_path(self, path):
        """Add widget to selection by file path"""
        layout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'full_path') and widget.full_path == path:
                    self.add_to_selection(widget)
                    break

    def remove_from_selection_by_path(self, path):
        """Remove widget from selection by file path"""
        layout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, 'full_path') and widget.full_path == path:
                    self.remove_from_selection(widget)
                    break

    def add_widget_optimized(self, widget, thumbnail_size, icons_wide=0):
        """Add widget to grid layout with optimized positioning for icons per row"""
        layout = self.layout()
        
        # Calculate approximate widget width (thumbnail + padding + margins)
        # Include space for text label underneath
        widget_width = thumbnail_size + 10  # thumbnail + margins/padding
        widget_height = thumbnail_size + 30  # thumbnail + text height + margins
        
        # Add spacing between widgets to the width calculation
        spacing = layout.spacing()  # Get the layout spacing (10 pixels)
        effective_widget_width = widget_width + spacing
        
        # Determine icons per row
        if icons_wide > 0:
            # Fixed number of icons per row
            icons_per_row = icons_wide
        else:
            # Auto-calculate based on available space
            container_width = self.width()
            if container_width <= 0:
                # If width not available yet, use a reasonable default
                container_width = 800
            # Account for margins and spacing in calculation
            available_width = container_width - 10  # -10 for container margins
            icons_per_row = max(1, available_width // effective_widget_width)
        
        # Calculate current position
        current_count = layout.count()
        row = current_count // icons_per_row
        col = current_count % icons_per_row
        
        # Add widget at calculated position
        layout.addWidget(widget, row, col)
        
        # Set widget size constraints for consistent layout
        widget.setMinimumSize(widget_width, widget_height)
        widget.setMaximumWidth(widget_width + 20)  # Allow some flexibility

class BreadcrumbWidget(QWidget):
    """Breadcrumb navigation widget"""
    pathClicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        
        # Set fixed height for breadcrumb bar
        self.setFixedHeight(40)
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)
        
        # Set larger font for the breadcrumb widget
        font = self.font()
        font.setPointSize(font.pointSize() * 2)
        self.setFont(font)
        
    def set_path(self, path):
        """Set the current path and update breadcrumb buttons"""
        # Clear existing widgets
        for i in reversed(range(self.layout.count())):
            child = self.layout.itemAt(i).widget()
            if child:
                child.deleteLater()
        
        if not path:
            return
            
        # Split path into parts
        parts = []
        current = path
        
        while current and current != os.path.dirname(current):
            parts.append((os.path.basename(current) or current, current))
            current = os.path.dirname(current)
        
        # Add root if not already included
        if current and current not in [p[1] for p in parts]:
            parts.append((current, current))
        
        parts.reverse()
        
        # Create breadcrumb buttons
        for i, (name, full_path) in enumerate(parts):
            if i > 0:
                # Add separator with larger font
                separator = QLabel(" > ")
                separator.setStyleSheet("color: gray; font-weight: bold; font-size: 16px;")
                self.layout.addWidget(separator)
            
            # Create clickable button for path part
            button = QPushButton(name)
            button.setFlat(True)
            button.setStyleSheet("""
                QPushButton {
                    border: none;
                    padding: 4px 8px;
                    color: #0066cc;
                    text-decoration: underline;
                    text-align: left;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 102, 204, 0.1);
                }
                QPushButton:pressed {
                    background-color: rgba(0, 102, 204, 0.2);
                }
            """)
            button.clicked.connect(lambda checked, path=full_path: self.pathClicked.emit(path))
            self.layout.addWidget(button)
        
        # Add stretch to left-align breadcrumbs
        self.layout.addStretch()

class SimpleFileManager(QMainWindow):
    SETTINGS_FILE = "filemanager_settings.json"

    def __init__(self):
        super().__init__()
        self.clipboard_data = None
        self.thumbnail_size = 64  # Default thumbnail size
        self.dark_mode = False  # Default to light mode
        self.icons_wide = 0  # 0 means auto-calculate, >0 means fixed width
        
        # View panel states (default visible)
        self.show_tree_view = True
        self.show_preview_pane = True
        self.search_visible = False
        
        # Initialize managers first (needed for settings loading)
        self.clipboard_manager = ClipboardHistoryManager()
        self.view_mode_manager = ViewModeManager()
        
        self.last_dir = self.load_last_dir() or QDir.rootPath()
        self.current_folder = self.last_dir  # Track current folder for right-click actions
        self.selected_icon = None  # Track selected icon
        self.selected_items = []  # Track multiple selected items
        self.error_count = 0  # Track errors for improved error handling
        self.current_search_results = []
        
        # Main layout with splitter for resizable panes
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)
        
        # Toolbar for quick access
        self.create_toolbar()
        
        # Add breadcrumb navigation at the top
        self.breadcrumb = BreadcrumbWidget()
        self.breadcrumb.pathClicked.connect(self.navigate_to_path)
        self.main_layout.addWidget(self.breadcrumb)
        
        # Search and filter widget
        self.search_filter = SearchFilterWidget()
        self.search_filter.searchRequested.connect(self.perform_search)
        self.search_filter.hide()  # Initially hidden, can be toggled
        self.main_layout.addWidget(self.search_filter)
        
        # Main content splitter (horizontal)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.main_splitter)
        
        # Left pane: tree view and controls
        self.left_pane = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_pane.setLayout(self.left_layout)
        self.main_splitter.addWidget(self.left_pane)
        
        # Tree view setup
        self.setup_tree_view()
        
        # Middle splitter for main view and preview
        self.content_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.content_splitter)
        
        # Center pane: file view with multiple view modes
        self.center_pane = QWidget()
        self.center_layout = QVBoxLayout()
        self.center_pane.setLayout(self.center_layout)
        self.content_splitter.addWidget(self.center_pane)
        
        # View mode controls
        self.setup_view_mode_controls()
        
        # Multiple view widgets
        self.setup_multiple_views()
        
        # Right pane: preview pane
        self.preview_pane = PreviewPane()
        self.content_splitter.addWidget(self.preview_pane)
        
        # Set initial splitter proportions
        self.main_splitter.setSizes([200, 800])  # Tree view : Content
        self.content_splitter.setSizes([600, 300])  # File view : Preview
        
        # Make splitters collapsible
        self.main_splitter.setCollapsible(0, True)
        self.content_splitter.setCollapsible(1, True)
        
        self.setWindowTitle('garysfm - Enhanced File Manager')
        self.resize(1200, 700)
        
        # Initialize file system model
        self.setup_file_system_model()
        
        # Setup menus with enhanced options
        self.setup_enhanced_menus()
        
        # For right-click context menu
        self.current_right_clicked_path = None
        
        # Add status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Setup keyboard shortcuts
        self.setup_enhanced_keyboard_shortcuts()
        
        # Initialize view with last directory
        self.update_icon_view(self.last_dir)
        
        # Restore view states from settings
        self.restore_view_states()
        
        # Apply dark mode if it was saved
        self.apply_dark_mode()
        self.update_dark_mode_checkmark()
        QTimer.singleShot(100, self.refresh_all_themes)
        
        # Initialize status bar after everything is set up
        QTimer.singleShot(0, self.safe_update_status_bar)

    def create_toolbar(self):
        """Create the main toolbar"""
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)
        
        # Navigation buttons
        self.back_action = QAction("< Back", self)
        self.forward_action = QAction("> Forward", self)
        self.up_action = QAction("^ Up", self)
        self.refresh_action = QAction("@ Refresh", self)
        
        self.back_action.triggered.connect(self.go_back)
        self.forward_action.triggered.connect(self.go_forward)
        self.up_action.triggered.connect(self.go_up)
        self.refresh_action.triggered.connect(self.refresh_current_view)
        
        self.toolbar.addAction(self.back_action)
        self.toolbar.addAction(self.forward_action)
        self.toolbar.addAction(self.up_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.refresh_action)
        self.toolbar.addSeparator()
        
        # View mode buttons
        self.icon_view_action = QAction("# Icons", self, checkable=True, checked=True)
        self.list_view_action = QAction("= List", self, checkable=True)
        self.detail_view_action = QAction("+ Details", self, checkable=True)
        
        self.icon_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.ICON_VIEW))
        self.list_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.LIST_VIEW))
        self.detail_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.DETAIL_VIEW))
        
        self.toolbar.addAction(self.icon_view_action)
        self.toolbar.addAction(self.list_view_action)
        self.toolbar.addAction(self.detail_view_action)
        self.toolbar.addSeparator()
        
        # Search toggle
        self.search_toggle_action = QAction("? Search", self, checkable=True)
        self.search_toggle_action.triggered.connect(self.toggle_search_pane)
        self.toolbar.addAction(self.search_toggle_action)
        
        # Clipboard history
        self.clipboard_history_action = QAction("[] Clipboard", self)
        self.clipboard_history_action.triggered.connect(self.show_clipboard_history)
        self.toolbar.addAction(self.clipboard_history_action)

    def setup_tree_view(self):
        """Setup the tree view for folder navigation"""
        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.rootPath())
        
        # Platform-specific model configuration for better compatibility
        if PlatformUtils.is_macos():
            self.model.setReadOnly(True)
            self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        elif PlatformUtils.is_windows():
            # Windows-specific optimizations
            self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden)
        else:  # Linux/Unix
            self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        
        # Improved tree view setup with platform-aware defaults
        try:
            self.tree_view.setRootIndex(self.model.index(self.last_dir))
        except Exception:
            home_dir = PlatformUtils.get_home_directory()
            self.tree_view.setRootIndex(self.model.index(home_dir))
            self.last_dir = home_dir
            self.current_folder = home_dir
        
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_double_click)
        self.left_layout.addWidget(self.tree_view)

    def setup_view_mode_controls(self):
        """Setup view mode control buttons"""
        controls_layout = QHBoxLayout()
        
        # View mode buttons group
        self.view_group = QButtonGroup()
        
        # Thumbnail size slider for icon view
        controls_layout.addWidget(QLabel("Size:"))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(32, 256)
        self.size_slider.setValue(self.thumbnail_size)
        self.size_slider.valueChanged.connect(self.set_thumbnail_size)
        controls_layout.addWidget(self.size_slider)
        
        # Add some spacing and info
        controls_layout.addStretch()
        
        self.center_layout.addLayout(controls_layout)

    def setup_multiple_views(self):
        """Setup different view widgets for files"""
        # Create a stacked widget to switch between views
        from PyQt5.QtWidgets import QStackedWidget
        self.view_stack = QStackedWidget()
        self.center_layout.addWidget(self.view_stack)
        
        # Icon view (existing)
        self.icon_view_widget = QWidget()
        icon_layout = QVBoxLayout()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.icon_container = IconContainer()
        self.icon_container.emptySpaceClicked.connect(self.deselect_icons)
        self.icon_container.emptySpaceRightClicked.connect(self.empty_space_right_clicked)
        self.icon_container.selectionChanged.connect(self.on_selection_changed)
        self.icon_grid = self.icon_container.layout()
        self.scroll_area.setWidget(self.icon_container)
        icon_layout.addWidget(self.scroll_area)
        self.icon_view_widget.setLayout(icon_layout)
        self.view_stack.addWidget(self.icon_view_widget)
        
        # List view
        self.list_view = QListView()
        self.list_model = QFileSystemModel()
        self.list_view.setModel(self.list_model)
        self.list_view.clicked.connect(self.on_list_item_clicked)
        self.list_view.doubleClicked.connect(self.on_list_double_click)
        self.view_stack.addWidget(self.list_view)
        
        # Detail/Table view
        self.table_view = QTableView()
        self.table_model = QFileSystemModel()
        self.table_view.setModel(self.table_model)
        self.table_view.clicked.connect(self.on_table_item_clicked)
        self.table_view.doubleClicked.connect(self.on_table_double_click)
        # Configure table view
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSortingEnabled(True)
        self.view_stack.addWidget(self.table_view)
        
        # Set initial view
        self.view_stack.setCurrentWidget(self.icon_view_widget)

    def setup_file_system_model(self):
        """Initialize the file system model"""
        pass  # Models are set up in individual view setup methods

    def setup_enhanced_menus(self):
        """Setup enhanced menu system"""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        self.new_folder_action = QAction("New Folder", self)
        self.new_folder_action.setShortcut("Ctrl+Shift+N")
        self.new_folder_action.triggered.connect(self.create_new_folder)
        file_menu.addAction(self.new_folder_action)
        
        file_menu.addSeparator()
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)
        
        # Edit menu with enhanced clipboard
        edit_menu = menu_bar.addMenu("Edit")
        self.cut_action = QAction("Cut", self)
        self.copy_action = QAction("Copy", self)
        self.paste_action = QAction("Paste", self)
        self.delete_action = QAction("Delete", self)
        self.cut_action.triggered.connect(self.cut_action_triggered)
        self.copy_action.triggered.connect(self.copy_action_triggered)
        self.paste_action.triggered.connect(self.paste_action_triggered)
        self.delete_action.triggered.connect(self.delete_selected_items)
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)
        
        edit_menu.addSeparator()
        self.select_all_action = QAction("Select All", self)
        self.select_all_action.setShortcut("Ctrl+A")
        self.select_all_action.triggered.connect(self.select_all_items)
        edit_menu.addAction(self.select_all_action)
        
        edit_menu.addSeparator()
        self.bulk_rename_action = QAction("Bulk Rename...", self)
        self.bulk_rename_action.triggered.connect(self.show_bulk_rename_dialog)
        edit_menu.addAction(self.bulk_rename_action)
        
        self.advanced_operations_action = QAction("Advanced Operations...", self)
        self.advanced_operations_action.triggered.connect(self.show_advanced_operations)
        edit_menu.addAction(self.advanced_operations_action)
        
        # View menu with enhanced options
        view_menu = menu_bar.addMenu("View")
        
        # View mode submenu
        view_mode_menu = view_menu.addMenu("View Mode")
        self.icon_mode_action = QAction("Icon View", self, checkable=True, checked=True)
        self.list_mode_action = QAction("List View", self, checkable=True)
        self.detail_mode_action = QAction("Detail View", self, checkable=True)
        
        self.icon_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.ICON_VIEW))
        self.list_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.LIST_VIEW))
        self.detail_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.DETAIL_VIEW))
        
        view_mode_menu.addAction(self.icon_mode_action)
        view_mode_menu.addAction(self.list_mode_action)
        view_mode_menu.addAction(self.detail_mode_action)
        
        # Thumbnail size submenu (for icon view)
        thumbnail_menu = view_menu.addMenu("Thumbnail Size")
        self.small_thumb_action = QAction("Small (48px)", self, checkable=True)
        self.medium_thumb_action = QAction("Medium (64px)", self, checkable=True)
        self.large_thumb_action = QAction("Large (96px)", self, checkable=True)
        self.xlarge_thumb_action = QAction("Extra Large (128px)", self, checkable=True)
        
        self.medium_thumb_action.setChecked(True)
        
        self.small_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(48))
        self.medium_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(64))
        self.large_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(96))
        self.xlarge_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(128))
        
        thumbnail_menu.addAction(self.small_thumb_action)
        thumbnail_menu.addAction(self.medium_thumb_action)
        thumbnail_menu.addAction(self.large_thumb_action)
        thumbnail_menu.addAction(self.xlarge_thumb_action)
        
        # Icon layout submenu (for icon view)
        layout_menu = view_menu.addMenu("Icon Layout")
        self.auto_width_action = QAction("Auto Width", self, checkable=True, checked=True)
        self.fixed_4_wide_action = QAction("4 Icons Wide", self, checkable=True)
        self.fixed_6_wide_action = QAction("6 Icons Wide", self, checkable=True)
        self.fixed_8_wide_action = QAction("8 Icons Wide", self, checkable=True)
        self.fixed_10_wide_action = QAction("10 Icons Wide", self, checkable=True)
        self.fixed_12_wide_action = QAction("12 Icons Wide", self, checkable=True)
        
        self.auto_width_action.triggered.connect(lambda: self.set_icons_wide(0))
        self.fixed_4_wide_action.triggered.connect(lambda: self.set_icons_wide(4))
        self.fixed_6_wide_action.triggered.connect(lambda: self.set_icons_wide(6))
        self.fixed_8_wide_action.triggered.connect(lambda: self.set_icons_wide(8))
        self.fixed_10_wide_action.triggered.connect(lambda: self.set_icons_wide(10))
        self.fixed_12_wide_action.triggered.connect(lambda: self.set_icons_wide(12))
        
        layout_menu.addAction(self.auto_width_action)
        layout_menu.addAction(self.fixed_4_wide_action)
        layout_menu.addAction(self.fixed_6_wide_action)
        layout_menu.addAction(self.fixed_8_wide_action)
        layout_menu.addAction(self.fixed_10_wide_action)
        layout_menu.addAction(self.fixed_12_wide_action)
        
        view_menu.addSeparator()
        
        # Panel toggles
        self.toggle_tree_action = QAction("Show Tree View", self, checkable=True, checked=True)
        self.toggle_preview_action = QAction("Show Preview Pane", self, checkable=True, checked=True)
        self.toggle_search_action = QAction("Show Search Panel", self, checkable=True)
        
        self.toggle_tree_action.triggered.connect(self.toggle_tree_view)
        self.toggle_preview_action.triggered.connect(self.toggle_preview_pane)
        self.toggle_search_action.triggered.connect(self.toggle_search_pane)
        
        view_menu.addAction(self.toggle_tree_action)
        view_menu.addAction(self.toggle_preview_action)
        view_menu.addAction(self.toggle_search_action)
        
        view_menu.addSeparator()
        self.dark_mode_action = QAction("Dark Mode", self, checkable=True)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        view_menu.addAction(self.dark_mode_action)
        
        # Update menu checkmarks
        self.update_thumbnail_menu_checkmarks()
        self.update_layout_menu_checkmarks()
        self.update_dark_mode_checkmark()
        self.apply_theme()
        
        # Tools menu
        tools_menu = menu_bar.addMenu("Tools")
        
        self.clipboard_history_menu_action = QAction("Clipboard History...", self)
        self.clipboard_history_menu_action.triggered.connect(self.show_clipboard_history)
        tools_menu.addAction(self.clipboard_history_menu_action)
        
        self.search_files_action = QAction("Search Files...", self)
        self.search_files_action.setShortcut("Ctrl+F")
        self.search_files_action.triggered.connect(self.focus_search)
        tools_menu.addAction(self.search_files_action)
        
        # Info menu
        info_menu = menu_bar.addMenu("Info")
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        info_menu.addAction(self.about_action)
        
        self.contact_action = QAction("Contact Me", self)
        self.contact_action.triggered.connect(self.show_contact_dialog)
        info_menu.addAction(self.contact_action)
        
        self.website_action = QAction("Website", self)
        self.website_action.triggered.connect(self.open_website)
        info_menu.addAction(self.website_action)

    def setup_enhanced_keyboard_shortcuts(self):
        """Setup enhanced keyboard shortcuts with platform-specific modifiers"""
        # Use platform utilities for consistent modifier keys
        main_modifier = PlatformUtils.get_modifier_key()
        alt_modifier = PlatformUtils.get_alt_modifier_key()
        nav_modifier = PlatformUtils.get_navigation_modifier()
        
        # File operations
        QShortcut(QKeySequence(f"{main_modifier}+C"), self, self.copy_action_triggered)
        QShortcut(QKeySequence(f"{main_modifier}+X"), self, self.cut_action_triggered)
        QShortcut(QKeySequence(f"{main_modifier}+V"), self, self.paste_action_triggered)
        QShortcut(QKeySequence("Delete"), self, self.delete_selected_items)
        QShortcut(QKeySequence("F2"), self, self.rename_selected_item)
        QShortcut(QKeySequence(f"{main_modifier}+Shift+N"), self, self.create_new_folder)
        
        # Navigation
        QShortcut(QKeySequence(f"{nav_modifier}+Left"), self, self.go_back)
        QShortcut(QKeySequence(f"{nav_modifier}+Right"), self, self.go_forward)
        QShortcut(QKeySequence(f"{nav_modifier}+Up"), self, self.go_up)
        QShortcut(QKeySequence("Backspace"), self, self.go_up)
        QShortcut(QKeySequence(f"{main_modifier}+R"), self, self.refresh_current_view)
        QShortcut(QKeySequence("F5"), self, self.refresh_current_view)  # Keep F5 for cross-platform
        
        # View modes
        QShortcut(QKeySequence(f"{main_modifier}+1"), self, lambda: self.set_view_mode(ViewModeManager.ICON_VIEW))
        QShortcut(QKeySequence(f"{main_modifier}+2"), self, lambda: self.set_view_mode(ViewModeManager.LIST_VIEW))
        QShortcut(QKeySequence(f"{main_modifier}+3"), self, lambda: self.set_view_mode(ViewModeManager.DETAIL_VIEW))
        
        # Selection
        QShortcut(QKeySequence(f"{main_modifier}+A"), self, self.select_all_items)
        QShortcut(QKeySequence("Escape"), self, self.deselect_icons)
        
        # Search and panels
        QShortcut(QKeySequence(f"{main_modifier}+F"), self, self.focus_search)
        QShortcut(QKeySequence(f"{main_modifier}+H"), self, self.show_clipboard_history)
        QShortcut(QKeySequence("F3"), self, self.toggle_preview_pane)
        QShortcut(QKeySequence("F9"), self, self.toggle_tree_view)
        
        # Platform-specific window management
        if PlatformUtils.is_macos():
            # macOS-specific shortcuts
            QShortcut(QKeySequence("Cmd+W"), self, self.close)  # Close window
            QShortcut(QKeySequence("Cmd+Q"), self, self.close)  # Quit application
            QShortcut(QKeySequence("Cmd+,"), self, self.show_preferences)  # Preferences
            QShortcut(QKeySequence("Cmd+Shift+."), self, self.toggle_show_hidden_files)  # Show hidden files
            QShortcut(QKeySequence("Cmd+T"), self, self.open_new_tab)  # New tab (if implemented)
            QShortcut(QKeySequence("Cmd+Delete"), self, self.move_to_trash)  # Move to trash
        else:
            # Windows/Linux shortcuts
            QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
            if PlatformUtils.is_windows():
                QShortcut(QKeySequence("Alt+F4"), self, self.close)  # Windows standard
            QShortcut(QKeySequence("Ctrl+H"), self, self.toggle_show_hidden_files)  # Show hidden files
            QShortcut(QKeySequence("Ctrl+T"), self, self.open_new_tab)  # New tab
            QShortcut(QKeySequence("Shift+Delete"), self, self.move_to_trash)  # Move to trash
        
        # Cross-platform shortcuts
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(f"{main_modifier}+Plus"), self, self.increase_thumbnail_size)
        QShortcut(QKeySequence(f"{main_modifier}+Minus"), self, self.decrease_thumbnail_size)
        QShortcut(QKeySequence(f"{main_modifier}+0"), self, self.reset_thumbnail_size)  # Reset zoom
        
        # Additional cross-platform shortcuts
        QShortcut(QKeySequence(f"{main_modifier}+L"), self, self.focus_location_bar)  # Focus address bar
        QShortcut(QKeySequence(f"{main_modifier}+D"), self, self.go_to_desktop)  # Go to desktop
        QShortcut(QKeySequence(f"{main_modifier}+Shift+D"), self, self.go_to_downloads)  # Go to downloads
        QShortcut(QKeySequence(f"{main_modifier}+Shift+H"), self, self.go_to_home)  # Go to home

    # Enhanced Methods for New Features
    
    def set_view_mode(self, mode):
        """Switch between different view modes"""
        self.view_mode_manager.set_mode(mode)
        
        # Update toolbar buttons
        self.icon_view_action.setChecked(mode == ViewModeManager.ICON_VIEW)
        self.list_view_action.setChecked(mode == ViewModeManager.LIST_VIEW)
        self.detail_view_action.setChecked(mode == ViewModeManager.DETAIL_VIEW)
        
        # Update menu items
        self.icon_mode_action.setChecked(mode == ViewModeManager.ICON_VIEW)
        self.list_mode_action.setChecked(mode == ViewModeManager.LIST_VIEW)
        self.detail_mode_action.setChecked(mode == ViewModeManager.DETAIL_VIEW)
        
        # Switch the actual view
        if mode == ViewModeManager.ICON_VIEW:
            self.view_stack.setCurrentWidget(self.icon_view_widget)
            self.size_slider.show()
        elif mode == ViewModeManager.LIST_VIEW:
            self.view_stack.setCurrentWidget(self.list_view)
            self.size_slider.hide()
            self.update_list_view(self.current_folder)
        elif mode == ViewModeManager.DETAIL_VIEW:
            self.view_stack.setCurrentWidget(self.table_view)
            self.size_slider.hide()

    # Cross-platform navigation methods
    def reset_thumbnail_size(self):
        """Reset thumbnail size to default"""
        if hasattr(self, 'size_slider'):
            default_size = 64  # Default icon size
            self.size_slider.setValue(default_size)
            if hasattr(self, 'update_thumbnail_size'):
                self.update_thumbnail_size(default_size)
    
    def focus_location_bar(self):
        """Focus the location/address bar"""
        if hasattr(self, 'location_bar') and self.location_bar:
            self.location_bar.setFocus()
            self.location_bar.selectAll()
    
    def go_to_desktop(self):
        """Navigate to the desktop directory"""
        desktop_path = PlatformUtils.get_desktop_directory()
        if os.path.exists(desktop_path):
            self.navigate_to_folder(desktop_path)
        else:
            self.show_error_message("Error", "Desktop directory not found")
    
    def go_to_downloads(self):
        """Navigate to the downloads directory"""
        downloads_path = PlatformUtils.get_downloads_directory()
        if os.path.exists(downloads_path):
            self.navigate_to_folder(downloads_path)
        else:
            self.show_error_message("Error", "Downloads directory not found")
    
    def go_to_home(self):
        """Navigate to the home directory"""
        home_path = PlatformUtils.get_home_directory()
        if os.path.exists(home_path):
            self.navigate_to_folder(home_path)
        else:
            self.show_error_message("Error", "Home directory not found")
    
    def navigate_to_folder(self, folder_path):
        """Navigate to a specific folder"""
        try:
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                self.current_folder = folder_path
                self.update_views(folder_path)
                # Update address bar if it exists
                if hasattr(self, 'location_bar') and self.location_bar:
                    self.location_bar.setText(folder_path)
                # Update navigation history
                if hasattr(self, 'add_to_history'):
                    self.add_to_history(folder_path)
            else:
                self.show_error_message("Error", f"Cannot navigate to folder: {folder_path}")
        except Exception as e:
            self.show_error_message("Navigation Error", f"Cannot navigate to folder: {folder_path}", str(e))
    
    def update_views(self, folder_path):
        """Update all views with the new folder"""
        # Update icon view
        if hasattr(self, 'update_icon_view'):
            self.update_icon_view(folder_path)
        # Update list view
        if hasattr(self, 'update_list_view'):
            self.update_list_view(folder_path)
        # Update tree view
        if hasattr(self, 'tree_view') and self.tree_view:
            index = self.tree_model.index(folder_path)
            if index.isValid():
                self.tree_view.setCurrentIndex(index)
                self.tree_view.scrollTo(index)
    
    def show_reveal_in_file_manager_option(self, file_path):
        """Add reveal in file manager option to context menus"""
        try:
            PlatformUtils.reveal_in_file_manager(file_path)
            self.statusBar().showMessage(f"Revealed {os.path.basename(file_path)} in file manager", 2000)
        except Exception as e:
            self.show_error_message("Error", f"Cannot reveal file in file manager: {str(e)}")
            self.update_table_view(self.current_folder)
        
        # Save the view mode setting
        self.save_last_dir(self.current_folder)
    
    def update_list_view(self, folder_path):
        """Update the list view with current folder contents"""
        if os.path.exists(folder_path):
            self.list_model.setRootPath(folder_path)
            self.list_view.setRootIndex(self.list_model.index(folder_path))
    
    def update_table_view(self, folder_path):
        """Update the table view with current folder contents"""
        if os.path.exists(folder_path):
            self.table_model.setRootPath(folder_path)
            self.table_view.setRootIndex(self.table_model.index(folder_path))
    
    def on_list_item_clicked(self, index):
        """Handle list view item clicks"""
        file_path = self.list_model.filePath(index)
        self.preview_pane.preview_file(file_path)
        if self.list_model.isDir(index):
            self.selected_items = [file_path]
        else:
            self.selected_items = [file_path]
        self.safe_update_status_bar()
    
    def on_list_double_click(self, index):
        """Handle list view double clicks"""
        file_path = self.list_model.filePath(index)
        if self.list_model.isDir(index):
            self.update_icon_view(file_path)
            self.update_list_view(file_path)
            self.update_table_view(file_path)
        else:
            self.open_file(file_path)
    
    def on_table_item_clicked(self, index):
        """Handle table view item clicks"""
        file_path = self.table_model.filePath(index)
        self.preview_pane.preview_file(file_path)
        if self.table_model.isDir(index):
            self.selected_items = [file_path]
        else:
            self.selected_items = [file_path]
        self.safe_update_status_bar()
    
    def on_table_double_click(self, index):
        """Handle table view double clicks"""
        file_path = self.table_model.filePath(index)
        if self.table_model.isDir(index):
            self.update_icon_view(file_path)
            self.update_list_view(file_path)
            self.update_table_view(file_path)
        else:
            self.open_file(file_path)
    
    def perform_search(self, search_text, filter_options):
        """Perform search with filters"""
        if not search_text.strip() and filter_options['type'] == 'All':
            # If no search term and no filters, show all files in current folder
            self.update_icon_view(self.current_folder)
            return
        
        self.current_search_results = []
        search_folder = self.current_folder
        
        try:
            for root, dirs, files in os.walk(search_folder):
                # Search in directories
                for dir_name in dirs:
                    if self.matches_search_criteria(dir_name, os.path.join(root, dir_name), 
                                                   search_text, filter_options, is_dir=True):
                        self.current_search_results.append(os.path.join(root, dir_name))
                
                # Search in files
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    if self.matches_search_criteria(file_name, file_path, 
                                                   search_text, filter_options, is_dir=False):
                        self.current_search_results.append(file_path)
        except Exception as e:
            self.show_error_message("Search Error", f"Error during search: {str(e)}")
            return
        
        # Update view with search results
        self.display_search_results()
    
    def matches_search_criteria(self, name, full_path, search_text, filter_options, is_dir):
        """Check if item matches search criteria"""
        # Text search
        if search_text.strip():
            if search_text.lower() not in name.lower():
                return False
        
        # Type filter
        type_filter = filter_options.get('type', 'All')
        if type_filter == 'Files Only' and is_dir:
            return False
        elif type_filter == 'Folders Only' and not is_dir:
            return False
        elif type_filter in ['Images', 'Documents', 'Videos', 'Audio'] and is_dir:
            return False
        elif type_filter != 'All' and not is_dir:
            # Check file type
            if not self.matches_file_type(full_path, type_filter):
                return False
        
        # Size filter
        if not is_dir:
            size_filter = filter_options.get('size', 'Any Size')
            if not self.matches_size_filter(full_path, size_filter):
                return False
        
        # Date filter
        date_filter = filter_options.get('date', 'Any Time')
        if not self.matches_date_filter(full_path, date_filter):
            return False
        
        return True
    
    def matches_file_type(self, file_path, type_filter):
        """Check if file matches type filter"""
        _, ext = os.path.splitext(file_path.lower())
        
        type_extensions = {
            'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg', '.webp'],
            'Documents': ['.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf'],
            'Videos': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'],
            'Audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma']
        }
        
        return ext in type_extensions.get(type_filter, [])
    
    def matches_size_filter(self, file_path, size_filter):
        """Check if file matches size filter"""
        try:
            size_bytes = os.path.getsize(file_path)
            size_mb = size_bytes / (1024 * 1024)
            
            if size_filter == 'Small (<1MB)':
                return size_mb < 1
            elif size_filter == 'Medium (1-10MB)':
                return 1 <= size_mb <= 10
            elif size_filter == 'Large (10-100MB)':
                return 10 < size_mb <= 100
            elif size_filter == 'Very Large (>100MB)':
                return size_mb > 100
            else:  # Any Size
                return True
        except:
            return True
    
    def matches_date_filter(self, file_path, date_filter):
        """Check if file matches date filter"""
        try:
            mod_time = os.path.getmtime(file_path)
            mod_date = datetime.datetime.fromtimestamp(mod_time)
            now = datetime.datetime.now()
            
            if date_filter == 'Today':
                return mod_date.date() == now.date()
            elif date_filter == 'This Week':
                week_start = now - datetime.timedelta(days=now.weekday())
                return mod_date >= week_start
            elif date_filter == 'This Month':
                return mod_date.year == now.year and mod_date.month == now.month
            elif date_filter == 'This Year':
                return mod_date.year == now.year
            else:  # Any Time
                return True
        except:
            return True
    
    def display_search_results(self):
        """Display search results in current view"""
        # For now, update icon view with search results
        # Clear current icons
        layout = self.icon_grid
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add search result icons
        row = 0
        col = 0
        max_cols = 6
        
        for file_path in self.current_search_results:
            if os.path.exists(file_path):
                file_name = os.path.basename(file_path)
                is_dir = os.path.isdir(file_path)
                
                icon_widget = IconWidget(file_name, file_path, is_dir, self.thumbnail_size)
                icon_widget.clicked.connect(self.icon_clicked)
                icon_widget.doubleClicked.connect(self.icon_double_clicked)
                icon_widget.rightClicked.connect(self.icon_right_clicked)
                icon_widget.update_style_for_theme(self.dark_mode)
                
                layout.addWidget(icon_widget, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
        
        self.safe_update_status_bar()
    
    def toggle_search_pane(self):
        """Toggle the search pane visibility"""
        if self.search_filter.isVisible():
            self.search_filter.hide()
            self.search_toggle_action.setChecked(False)
            self.toggle_search_action.setChecked(False)
            self.search_visible = False
        else:
            self.search_filter.show()
            self.search_toggle_action.setChecked(True)
            self.toggle_search_action.setChecked(True)
            self.search_visible = True
        
        # Save the setting
        self.save_last_dir(self.current_folder)
    
    def focus_search(self):
        """Focus the search input"""
        if not self.search_filter.isVisible():
            self.toggle_search_pane()
        self.search_filter.search_input.setFocus()
        self.search_filter.search_input.selectAll()
    
    def restore_view_states(self):
        """Restore view panel states from settings"""
        # Restore tree view state
        if not self.show_tree_view:
            self.left_pane.hide()
            self.toggle_tree_action.setChecked(False)
        else:
            self.left_pane.show()
            self.toggle_tree_action.setChecked(True)
        
        # Restore preview pane state
        if not self.show_preview_pane:
            self.preview_pane.hide()
            self.toggle_preview_action.setChecked(False)
        else:
            self.preview_pane.show()
            self.toggle_preview_action.setChecked(True)
        
        # Restore search panel state
        if self.search_visible:
            self.search_filter.show()
            self.search_toggle_action.setChecked(True)
            self.toggle_search_action.setChecked(True)
        else:
            self.search_filter.hide()
            self.search_toggle_action.setChecked(False)
            self.toggle_search_action.setChecked(False)
    
    def toggle_tree_view(self):
        """Toggle tree view visibility"""
        if self.left_pane.isVisible():
            self.left_pane.hide()
            self.toggle_tree_action.setChecked(False)
            self.show_tree_view = False
        else:
            self.left_pane.show()
            self.toggle_tree_action.setChecked(True)
            self.show_tree_view = True
        
        # Save the setting
        self.save_last_dir(self.current_folder)
    
    def toggle_preview_pane(self):
        """Toggle preview pane visibility"""
        if self.preview_pane.isVisible():
            self.preview_pane.hide()
            self.toggle_preview_action.setChecked(False)
            self.show_preview_pane = False
        else:
            self.preview_pane.show()
            self.toggle_preview_action.setChecked(True)
            self.show_preview_pane = True
        
        # Save the setting
        self.save_last_dir(self.current_folder)
    
    def show_clipboard_history(self):
        """Show clipboard history dialog"""
        dialog = ClipboardHistoryDialog(self.clipboard_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_entry = dialog.get_selected_entry()
            if selected_entry:
                # Restore the selected clipboard entry
                self.clipboard_manager.set_current_operation(
                    selected_entry['operation'], 
                    selected_entry['paths']
                )
    
    def create_new_folder(self):
        """Create a new folder in the current directory"""
        folder_name, ok = QInputDialog.getText(
            self, 'New Folder', 'Enter folder name:', 
            text='New Folder'
        )
        if ok and folder_name.strip():
            new_folder_path = os.path.join(self.current_folder, folder_name.strip())
            try:
                os.makedirs(new_folder_path, exist_ok=False)
                self.refresh_current_view()
                self.show_info_message("Success", f"Folder '{folder_name}' created successfully")
            except FileExistsError:
                self.show_error_message("Error", f"Folder '{folder_name}' already exists")
            except Exception as e:
                self.show_error_message("Error", f"Could not create folder: {str(e)}")
    
    def show_advanced_operations(self):
        """Show advanced operations dialog"""
        dialog = AdvancedOperationsDialog(self.selected_items, self.current_folder, self)
        dialog.exec_()
    
    def go_back(self):
        """Navigate back in history"""
        # This would require implementing navigation history
        # For now, just go up
        self.go_up()
    
    def go_forward(self):
        """Navigate forward in history"""
        # This would require implementing navigation history
        # For now, do nothing
        pass
    
    def increase_thumbnail_size(self):
        """Increase thumbnail size"""
        new_size = min(256, self.thumbnail_size + 16)
        self.set_thumbnail_size(new_size)
    
    def decrease_thumbnail_size(self):
        """Decrease thumbnail size"""
        new_size = max(32, self.thumbnail_size - 16)
        self.set_thumbnail_size(new_size)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def open_file(self, file_path):
        """Open a file with the default application"""
        try:
            if not PlatformUtils.open_file_with_default_app(file_path):
                self.show_error_message("Error", f"Cannot open file: {file_path}")
        except Exception as e:
            self.show_error_message("Error", f"Cannot open file: {str(e)}")
    
    def show_info_message(self, title, message):
        """Show an information message"""
        QMessageBox.information(self, title, message)
    
    # Enhanced clipboard methods
    def cut_action_triggered(self):
        """Enhanced cut action with history"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation('cut', self.selected_items)
            self.show_info_message("Cut", f"Cut {len(self.selected_items)} item(s)")
    
    def copy_action_triggered(self):
        """Enhanced copy action with history"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation('copy', self.selected_items)
            self.show_info_message("Copy", f"Copied {len(self.selected_items)} item(s)")
    
    def paste_action_triggered(self):
        """Enhanced paste action with history"""
        operation, paths = self.clipboard_manager.get_current_operation()
        if not operation or not paths:
            return
        
        destination = self.current_folder
        success_count = 0
        
        for source_path in paths:
            if not os.path.exists(source_path):
                continue
            
            file_name = os.path.basename(source_path)
            dest_path = os.path.join(destination, file_name)
            
            try:
                if operation == 'copy':
                    if os.path.isdir(source_path):
                        shutil.copytree(source_path, dest_path)
                    else:
                        shutil.copy2(source_path, dest_path)
                elif operation == 'cut':
                    shutil.move(source_path, dest_path)
                success_count += 1
            except Exception as e:
                self.show_error_message("Paste Error", f"Could not paste {file_name}: {str(e)}")
        
        if operation == 'cut' and success_count > 0:
            self.clipboard_manager.clear_current()
        
        if success_count > 0:
            self.refresh_current_view()
            self.show_info_message("Paste", f"Successfully pasted {success_count} item(s)")

    def navigate_to_path(self, path):
        """Navigate to a specific path (called from breadcrumb)"""
        try:
            if os.path.exists(path) and os.path.isdir(path):
                index = self.model.index(path)
                self.tree_view.setCurrentIndex(index)
                self.tree_view.expand(index)
                self.update_icon_view(path)
            else:
                self.show_error_message("Navigation Error", f"Path no longer exists: {path}")
        except Exception as e:
            self.show_error_message("Navigation Error", f"Cannot navigate to {path}: {str(e)}")
            
    def safe_update_status_bar(self):
        """Safely update status bar with error protection"""
        try:
            if hasattr(self, 'status_bar') and self.status_bar is not None:
                self.update_status_bar()
        except Exception as e:
            print(f"Status bar update failed: {str(e)}")  # Debug output
            
    def update_status_bar(self):
        """Update status bar with current selection and folder info"""
        try:
            if not hasattr(self, 'status_bar') or self.status_bar is None:
                return
                
            selected_count = len(self.selected_items)
            if selected_count == 0:
                # Show folder info
                try:
                    items = os.listdir(self.current_folder)
                    file_count = sum(1 for item in items if os.path.isfile(os.path.join(self.current_folder, item)))
                    folder_count = sum(1 for item in items if os.path.isdir(os.path.join(self.current_folder, item)))
                    self.status_bar.showMessage(f"{folder_count} folders, {file_count} files")
                except Exception:
                    self.status_bar.showMessage("Ready")
            elif selected_count == 1:
                # Show single item info
                item_path = self.selected_items[0]
                try:
                    if os.path.isfile(item_path):
                        size = os.path.getsize(item_path)
                        size_str = self.format_file_size(size)
                        self.status_bar.showMessage(f"1 file selected ({size_str})")
                    else:
                        self.status_bar.showMessage("1 folder selected")
                except Exception:
                    self.status_bar.showMessage("1 item selected")
            else:
                # Show multiple items info
                self.status_bar.showMessage(f"{selected_count} items selected")
        except Exception as e:
            # Fallback status message
            if hasattr(self, 'status_bar') and self.status_bar is not None:
                self.status_bar.showMessage("Ready")

    def format_file_size(self, size):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def show_error_message(self, title, message, details=None):
        """Show an error message dialog with improved error handling"""
        try:
            self.error_count += 1
            if details:
                full_message = f"{message}\n\nDetails: {details}"
            else:
                full_message = message
            QMessageBox.critical(self, title, full_message)
        except Exception as e:
            # Fallback: print to console if GUI fails
            print(f"Error showing message: {title} - {message}")
            if details:
                print(f"Details: {details}")

    def closeEvent(self, event):
        """Save the current folder location when the application is closed"""
        self.save_last_dir(self.current_folder)
        event.accept()

    def save_last_dir(self, path):
        try:
            data = {
                "last_dir": path,
                "thumbnail_size": self.thumbnail_size,
                "dark_mode": self.dark_mode,
                "icons_wide": self.icons_wide,
                "view_mode": self.view_mode_manager.get_mode(),
                "show_tree_view": self.show_tree_view,
                "show_preview_pane": self.show_preview_pane,
                "search_visible": self.search_visible
            }
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_last_dir(self):
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    # Load thumbnail size if available
                    if "thumbnail_size" in data:
                        self.thumbnail_size = data["thumbnail_size"]
                    # Load dark mode setting if available
                    if "dark_mode" in data:
                        self.dark_mode = data["dark_mode"]
                    # Load icons wide setting if available
                    if "icons_wide" in data:
                        self.icons_wide = data["icons_wide"]
                    elif "max_icons_wide" in data:  # Backward compatibility
                        self.icons_wide = data["max_icons_wide"]
                    # Load view mode if available
                    if "view_mode" in data:
                        self.view_mode_manager.set_mode(data["view_mode"])
                    # Load view panel states if available
                    if "show_tree_view" in data:
                        self.show_tree_view = data["show_tree_view"]
                    if "show_preview_pane" in data:
                        self.show_preview_pane = data["show_preview_pane"]
                    if "search_visible" in data:
                        self.search_visible = data["search_visible"]
                    
                    last_dir = data.get("last_dir", None)
                    
                    # Additional validation for macOS 11.0.1
                    if last_dir and sys.platform == 'darwin':
                        # Verify the directory still exists and is accessible
                        if os.path.exists(last_dir) and os.access(last_dir, os.R_OK):
                            return last_dir
                    elif last_dir and os.path.exists(last_dir):
                        return last_dir
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        # Default fallback for macOS 11.0.1
        if sys.platform == 'darwin':
            return os.path.expanduser('~')
        
        return None

    def open_website(self):
        """Open the website in the default browser"""
        webbrowser.open("https://turkokards.com")

    def show_bulk_rename_dialog(self):
        """Show bulk rename dialog for selected files or all files in current directory"""
        # Determine which files to rename
        if self.selected_items:
            files_to_rename = [path for path in self.selected_items if os.path.isfile(path)]
            dialog_title = "Bulk Rename {} Selected Files".format(len(files_to_rename))
        else:
            # Get all files in current directory (excluding folders)
            try:
                all_items = os.listdir(self.current_folder)
                files_to_rename = [os.path.join(self.current_folder, item) 
                                 for item in all_items 
                                 if os.path.isfile(os.path.join(self.current_folder, item)) 
                                 and not item.startswith('.')]
            except (OSError, PermissionError):
                QMessageBox.warning(self, "Error", "Cannot access files in current directory")
                return
            
            if not files_to_rename:
                QMessageBox.information(self, "No Files", "No files found to rename in current directory")
                return
            
            dialog_title = "Bulk Rename {} Files in Current Directory".format(len(files_to_rename))
        
        if not files_to_rename:
            QMessageBox.information(self, "No Files", "No files selected for renaming")
            return
        
        # Create the bulk rename dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(dialog_title)
        dialog.setModal(True)
        dialog.resize(700, 500)
        
        layout = QVBoxLayout()
        
        # Pattern input section
        pattern_group = QGroupBox("Rename Pattern")
        pattern_layout = QGridLayout()
        
        # Pattern type selection
        self.pattern_type = QComboBox()
        self.pattern_type.addItems([
            "Find and Replace",
            "Add Prefix", 
            "Add Suffix",
            "Number Files (1, 2, 3...)",
            "Custom Pattern"
        ])
        self.pattern_type.currentTextChanged.connect(lambda: self.toggle_replacement_controls())
        pattern_layout.addWidget(QLabel("Rename Type:"), 0, 0)
        pattern_layout.addWidget(self.pattern_type, 0, 1)
        
        # Find/Replace inputs (shown by default)
        pattern_layout.addWidget(QLabel("Find:"), 1, 0)
        self.find_text = QLineEdit()
        self.find_text.textChanged.connect(lambda: self.update_rename_preview(files_to_rename))
        pattern_layout.addWidget(self.find_text, 1, 1)
        
        pattern_layout.addWidget(QLabel("Replace with:"), 2, 0)
        self.replace_text = QLineEdit()
        self.replace_text.textChanged.connect(lambda: self.update_rename_preview(files_to_rename))
        pattern_layout.addWidget(self.replace_text, 2, 1)
        
        # Custom pattern input (hidden by default)
        pattern_layout.addWidget(QLabel("Pattern:"), 3, 0)
        self.pattern_text = QLineEdit()
        self.pattern_text.setPlaceholderText("Use {name} for filename, {ext} for extension, {n} for number")
        self.pattern_text.textChanged.connect(lambda: self.update_rename_preview(files_to_rename))
        pattern_layout.addWidget(self.pattern_text, 3, 1)
        
        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)
        
        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(["Original Name", "New Name"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.preview_table)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        button_layout.addStretch()
        
        # Rename button
        rename_button = QPushButton("Rename Files")
        rename_button.clicked.connect(lambda: self.execute_bulk_rename(files_to_rename, dialog))
        button_layout.addWidget(rename_button)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Store dialog reference for other methods
        self.bulk_rename_dialog = dialog
        
        # Initialize preview
        self.toggle_replacement_controls()
        self.update_rename_preview(files_to_rename)
        
        # Show dialog
        dialog.exec_()

    def toggle_replacement_controls(self):
        """Show/hide controls based on selected pattern type"""
        pattern_type = self.pattern_type.currentText()
        
        # Get all the input widgets from dialog layout
        dialog = self.bulk_rename_dialog
        
        # Hide/show find/replace controls
        if pattern_type == "Find and Replace":
            self.find_text.setVisible(True)
            self.replace_text.setVisible(True)
            self.pattern_text.setVisible(False)
        else:
            self.find_text.setVisible(False) 
            self.replace_text.setVisible(False)
            self.pattern_text.setVisible(pattern_type == "Custom Pattern")

    def update_rename_preview(self, files_to_rename):
        """Update the preview table with new file names"""
        pattern_type = self.pattern_type.currentText()
        
        self.preview_table.setRowCount(len(files_to_rename))
        
        for i, file_path in enumerate(files_to_rename):
            original_name = os.path.basename(file_path)
            
            # Generate new name based on pattern type
            try:
                if pattern_type == "Find and Replace":
                    new_name = self.generate_new_filename(original_name, self.find_text.text(), self.replace_text.text())
                elif pattern_type == "Add Prefix":
                    new_name = self.find_text.text() + original_name
                elif pattern_type == "Add Suffix":
                    name, ext = os.path.splitext(original_name)
                    new_name = name + self.find_text.text() + ext
                elif pattern_type == "Number Files (1, 2, 3...)":
                    name, ext = os.path.splitext(original_name)
                    new_name = f"{i+1:03d}{ext}"
                elif pattern_type == "Custom Pattern":
                    name, ext = os.path.splitext(original_name)
                    new_name = self.pattern_text.text().replace("{name}", name).replace("{ext}", ext).replace("{n}", str(i+1))
                else:
                    new_name = original_name
            except Exception:
                new_name = original_name
            
            # Set table items
            self.preview_table.setItem(i, 0, QTableWidgetItem(original_name))
            self.preview_table.setItem(i, 1, QTableWidgetItem(new_name))
            
            # Color invalid names red
            if not new_name or new_name == original_name:
                self.preview_table.item(i, 1).setBackground(QColor(255, 200, 200))

    def generate_new_filename(self, old_name, pattern, replacement=""):
        """Generate new filename based on pattern"""
        try:
            if not pattern:
                return old_name
            
            return old_name.replace(pattern, replacement)
        except Exception:
            return old_name

    def execute_bulk_rename(self, files_to_rename, dialog):
        """Execute the bulk rename operation"""
        pattern_type = self.pattern_type.currentText()
        
        if not files_to_rename:
            QMessageBox.warning(dialog, "Error", "No files to rename")
            return
        
        # Confirm operation
        reply = QMessageBox.question(dialog, "Confirm Bulk Rename",
                                   f"Are you sure you want to rename {len(files_to_rename)} files?",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        success_count = 0
        errors = []
        
        for i, file_path in enumerate(files_to_rename):
            try:
                old_name = os.path.basename(file_path)
                directory = os.path.dirname(file_path)
                
                # Generate new name
                if pattern_type == "Find and Replace":
                    new_name = self.generate_new_filename(old_name, self.find_text.text(), self.replace_text.text())
                elif pattern_type == "Add Prefix":
                    new_name = self.find_text.text() + old_name
                elif pattern_type == "Add Suffix":
                    name, ext = os.path.splitext(old_name)
                    new_name = name + self.find_text.text() + ext
                elif pattern_type == "Number Files (1, 2, 3...)":
                    name, ext = os.path.splitext(old_name)
                    new_name = f"{i+1:03d}{ext}"
                elif pattern_type == "Custom Pattern":
                    name, ext = os.path.splitext(old_name)
                    new_name = self.pattern_text.text().replace("{name}", name).replace("{ext}", ext).replace("{n}", str(i+1))
                else:
                    continue  # Skip if no valid pattern
                
                if new_name and new_name != old_name:
                    new_path = os.path.join(directory, new_name)
                    if not os.path.exists(new_path):
                        os.rename(file_path, new_path)
                        success_count += 1
                    else:
                        errors.append(f"File already exists: {new_name}")
                        
            except Exception as e:
                errors.append(f"Error renaming {old_name}: {str(e)}")
        
        # Show results
        if errors:
            error_msg = "Renamed {} files successfully.\n\nErrors encountered:\n".format(success_count) + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += "\n... and {} more errors".format(len(errors) - 10)
            QMessageBox.warning(dialog, "Bulk Rename Complete with Errors", error_msg)
        else:
            QMessageBox.information(dialog, "Bulk Rename Complete", "Successfully renamed {} files.".format(success_count))
        
        # Refresh the view and close dialog
        self.update_icon_view(self.current_folder)
        dialog.accept()

    def go_up(self):
        current_path = self.current_folder
        parent_path = os.path.dirname(current_path)
        if parent_path and os.path.exists(parent_path) and parent_path != current_path:
            parent_index = self.model.index(parent_path)
            self.tree_view.setCurrentIndex(parent_index)
            self.tree_view.expand(parent_index)
            self.update_icon_view(parent_path)

    def on_tree_item_clicked(self, index):
        try:
            file_path = self.model.filePath(index)
            
            # Additional validation for macOS 11.0.1
            if sys.platform == 'darwin':
                # Check if path exists and is accessible
                if not os.path.exists(file_path):
                    self.show_error_message("Path Error", f"Path no longer exists: {file_path}")
                    return
                
                # Check read permissions
                if not os.access(file_path, os.R_OK):
                    self.show_error_message("Permission Error", f"Cannot access: {file_path}")
                    return
            
            if QFileInfo(file_path).isDir():
                # Verify directory can be listed before updating view
                try:
                    os.listdir(file_path)
                    self.update_icon_view(file_path)
                except (OSError, PermissionError) as e:
                    self.show_error_message("Access Error", 
                        f"Cannot access directory: {file_path}", str(e))
                    return
            else:
                self.clear_icon_view()
        except Exception as e:
            self.show_error_message("Tree Navigation Error", 
                "Error accessing selected item", str(e))
            self.clear_icon_view()

    def update_icon_view(self, folder_path):
        self.current_folder = folder_path  # Update current folder
        self.save_last_dir(folder_path)  # Save the current folder to settings
        
        # Update breadcrumb navigation
        self.breadcrumb.set_path(folder_path)
        
        # Synchronize tree view with icon view
        self.sync_tree_view_selection(folder_path)
        
        # Clear the icon view first
        self.clear_icon_view()
        
        # Filter files/folders based on search criteria
        search_text = self.search_filter.search_input.text().lower()
        selected_filters = []
        filter_type = self.search_filter.type_combo.currentText()
        
        if filter_type == "Images":
            selected_filters.extend(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'])
        elif filter_type == "Documents":
            selected_filters.extend(['.txt', '.pdf', '.doc', '.docx', '.rtf', '.odt'])
        elif filter_type == "Videos":
            selected_filters.extend(['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'])
        elif filter_type == "Audio":
            selected_filters.extend(['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma'])
        
        try:
            items = os.listdir(folder_path)
        except (OSError, PermissionError) as e:
            self.show_error_message("Access Error", f"Cannot read directory: {folder_path}", str(e))
            return
        
        # Clear selection when changing folders
        self.selected_items = []
        self.on_selection_changed([])  # Notify of empty selection
        
        # Sort items: directories first, then files
        items = sorted(items, key=lambda x: (not os.path.isdir(os.path.join(folder_path, x)), x.lower()))
        
        # Create icon widgets for each item
        for item_name in items:
            full_path = os.path.join(folder_path, item_name)
            
            # Skip hidden files on macOS and Linux unless show hidden is enabled
            if item_name.startswith('.') and not getattr(self, 'show_hidden', False):
                continue
            
            # Apply search filter
            if search_text and search_text not in item_name.lower():
                continue
            
            # Apply type filters (only if at least one filter is selected)
            if selected_filters:
                is_file = os.path.isfile(full_path)
                if is_file:
                    file_ext = os.path.splitext(item_name)[1].lower()
                    if file_ext not in selected_filters:
                        continue
                else:
                    # For directories, show them if any filter is selected
                    # (user might want to navigate into directories)
                    pass
            
            try:
                is_dir = os.path.isdir(full_path)
                
                # Create icon widget
                icon_widget = IconWidget(item_name, full_path, is_dir, self.thumbnail_size)
                
                # Connect click signals
                icon_widget.clicked.connect(self.icon_clicked)
                icon_widget.doubleClicked.connect(self.icon_double_clicked)
                icon_widget.rightClicked.connect(self.icon_right_clicked)
                
                # Add to container based on current view mode
                if self.view_mode_manager.get_mode() == "icon":
                    # Icon view - use optimized grid layout
                    self.icon_container.add_widget_optimized(icon_widget, self.thumbnail_size, self.icons_wide)
                elif self.view_mode_manager.get_mode() == "list":
                    # List view - add to list view
                    item = QListWidgetItem(item_name)
                    item.setData(Qt.UserRole, full_path)  # Store full path
                    if is_dir:
                        item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                    else:
                        item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                    self.list_view.addItem(item)
                elif self.view_mode_manager.get_mode() == "detail":
                    # Detail view - add to table
                    row = self.detail_view.rowCount()
                    self.detail_view.insertRow(row)
                    
                    # Name column
                    name_item = QTableWidgetItem(item_name)
                    name_item.setData(Qt.UserRole, full_path)
                    if is_dir:
                        name_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                    else:
                        name_item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                    self.detail_view.setItem(row, 0, name_item)
                    
                    # Size column
                    if is_dir:
                        size_text = "Folder"
                    else:
                        try:
                            size = os.path.getsize(full_path)
                            size_text = self.format_file_size(size)
                        except:
                            size_text = "Unknown"
                    self.detail_view.setItem(row, 1, QTableWidgetItem(size_text))
                    
                    # Modified column
                    try:
                        mtime = os.path.getmtime(full_path)
                        modified_text = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                    except:
                        modified_text = "Unknown"
                    self.detail_view.setItem(row, 2, QTableWidgetItem(modified_text))
                
            except Exception as e:
                print(f"Error creating icon widget for {item_name}: {e}")
                continue

    def clear_icon_view(self):
        """Clear all items from the current view"""
        # Clear grid layout by removing all widgets
        layout = self.icon_container.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        
        # Clear detail view rows (QTableView)
        if hasattr(self, 'detail_view'):
            self.detail_view.setRowCount(0)

    def deselect_icons(self):
        """Deselect all icons in the current view"""
        self.selected_items = []
        self.icon_container.clear_selection()
        self.on_selection_changed([])

    def on_selection_changed(self, selected_paths):
        """Handle selection change in icon view"""
        self.selected_items = selected_paths
        
        # Update clipboard actions
        has_selection = len(selected_paths) > 0
        self.cut_action.setEnabled(has_selection)
        self.copy_action.setEnabled(has_selection) 
        self.delete_action.setEnabled(has_selection)
        
        # Update preview pane
        if len(selected_paths) == 1:
            self.preview_pane.preview_file(selected_paths[0])
        elif len(selected_paths) > 1:
            self.preview_pane.clear_preview()
            # Could show multi-selection info here
        else:
            self.preview_pane.clear_preview()

    def icon_clicked(self, full_path, modifiers):
        """Handle single click on an icon"""
        if modifiers & Qt.ControlModifier:
            # Ctrl+click: toggle selection
            if full_path in self.selected_items:
                self.selected_items.remove(full_path)
                self.icon_container.remove_from_selection_by_path(full_path)
            else:
                self.selected_items.append(full_path)
                self.icon_container.add_to_selection_by_path(full_path)
        elif modifiers & Qt.ShiftModifier:
            # Shift+click: range selection (simplified)
            if full_path not in self.selected_items:
                self.selected_items.append(full_path)
                self.icon_container.add_to_selection_by_path(full_path)
        else:
            # Regular click: select only this item
            self.selected_items = [full_path]
            self.icon_container.clear_selection()
            self.icon_container.add_to_selection_by_path(full_path)
        
        self.on_selection_changed(self.selected_items)

    def icon_double_clicked(self, full_path):
        """Handle double-click on an icon"""
        if os.path.isdir(full_path):
            self.update_icon_view(full_path)
        else:
            # Open file with default application using platform utilities
            try:
                if not PlatformUtils.open_file_with_default_app(full_path):
                    self.show_error_message("Open Error", f"Cannot open file: {full_path}", "No suitable application found")
            except Exception as e:
                self.show_error_message("Open Error", f"Cannot open file: {full_path}", str(e))

    def icon_right_clicked(self, full_path, global_pos):
        """Handle right-click on an icon"""
        # Ensure the clicked item is selected
        if full_path not in self.selected_items:
            self.selected_items = [full_path]
            self.icon_container.clear_selection()
            self.icon_container.add_to_selection_by_path(full_path)
            self.on_selection_changed(self.selected_items)
        
        context_menu = QMenu(self)
        
        # Single item actions
        if len(self.selected_items) == 1:
            item_path = self.selected_items[0]
            is_dir = os.path.isdir(item_path)
            
            if is_dir:
                open_action = context_menu.addAction("Open")
                open_action.triggered.connect(lambda: self.update_icon_view(item_path))
            else:
                open_action = context_menu.addAction("Open")
                open_action.triggered.connect(lambda: self.icon_double_clicked(item_path))
            
            context_menu.addSeparator()
        
        # Multi-selection or single item actions
        cut_action = context_menu.addAction("Cut")
        cut_action.triggered.connect(self.cut_action_triggered)
        cut_action.setEnabled(len(self.selected_items) > 0)
        
        copy_action = context_menu.addAction("Copy")
        copy_action.triggered.connect(self.copy_action_triggered)
        copy_action.setEnabled(len(self.selected_items) > 0)
        
        # Paste (always available in folder context)
        if self.clipboard_manager.get_current_operation()[0]:  # Has something to paste
            paste_action = context_menu.addAction("Paste")
            paste_action.triggered.connect(self.paste_action_triggered)
        
        context_menu.addSeparator()
        
        # Single item actions
        if len(self.selected_items) == 1:
            rename_action = context_menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self.rename_file(self.selected_items[0]))
            
            copy_path_action = context_menu.addAction("Copy Path")
            copy_path_action.triggered.connect(lambda: self.copy_path_to_clipboard(self.selected_items))
            
            # Add "Reveal in File Manager" option for single items
            reveal_action = context_menu.addAction("Reveal in File Manager")
            reveal_action.triggered.connect(lambda: self.show_reveal_in_file_manager_option(self.selected_items[0]))
        
        context_menu.addSeparator()
        
        delete_action = context_menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_multiple_files(self.selected_items))
        delete_action.setEnabled(len(self.selected_items) > 0)
        
        # Always add "Open Terminal Here" option
        context_menu.addSeparator()
        terminal_action = context_menu.addAction("Open Terminal Here")
        
        # Determine the path to open terminal in
        if len(self.selected_items) == 1:
            selected_path = self.selected_items[0]
            if os.path.isdir(selected_path):
                # If it's a directory, open terminal in that directory
                terminal_action.triggered.connect(lambda: self.open_terminal_here(selected_path))
            else:
                # If it's a file, open terminal in the parent directory
                terminal_action.triggered.connect(lambda: self.open_terminal_here(os.path.dirname(selected_path)))
        else:
            # Multiple items selected, open terminal in current folder
            terminal_action.triggered.connect(lambda: self.open_terminal_here(self.current_folder))
        
        context_menu.exec_(global_pos)

    def rename_file(self, path):
        """Rename a single file or folder"""
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        
        if ok and new_name and new_name != old_name:
            try:
                new_path = os.path.join(os.path.dirname(path), new_name)
                if os.path.exists(new_path):
                    QMessageBox.warning(self, "Error", "A file or folder with that name already exists.")
                    return
                    
                os.rename(path, new_path)
                self.update_icon_view(self.current_folder)
                
            except Exception as e:
                self.show_error_message("Rename Error", f"Could not rename: {old_name}", str(e))

    def copy_path_to_clipboard(self, paths):
        """Copy file/folder paths to clipboard"""
        if paths:
            clipboard = QApplication.clipboard()
            if len(paths) == 1:
                clipboard.setText(paths[0])
            else:
                clipboard.setText('\n'.join(paths))
            
            # Show temporary status message
            count = len(paths)
            item_word = "path" if count == 1 else "paths"
            self.statusBar().showMessage(f"Copied {count} {item_word} to clipboard", 2000)

    def empty_space_right_clicked(self, global_pos):
        """Handle right-click on empty space"""
        context_menu = QMenu(self)
        
        # Create new actions
        new_folder_action = context_menu.addAction("New Folder")
        new_folder_action.triggered.connect(self.create_new_folder)
        
        new_file_action = context_menu.addAction("New File")  
        new_file_action.triggered.connect(self.create_new_file)
        
        context_menu.addSeparator()
        
        # Paste action
        if self.clipboard_manager.get_current_operation()[0]:  # Has something to paste
            paste_action = context_menu.addAction("Paste")
            paste_action.triggered.connect(self.paste_action_triggered)
        
        context_menu.addSeparator()
        
        # Open Terminal Here action
        terminal_action = context_menu.addAction("Open Terminal Here")
        terminal_action.triggered.connect(lambda: self.open_terminal_here(self.current_folder))
        
        context_menu.exec_(global_pos)

    def create_new_file(self):
        """Create a new file in current directory"""
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            try:
                file_path = os.path.join(self.current_folder, name)
                if os.path.exists(file_path):
                    QMessageBox.warning(self, "Error", "A file with that name already exists.")
                    return
                    
                # Create empty file
                with open(file_path, 'w') as f:
                    pass
                    
                self.update_icon_view(self.current_folder)
            except Exception as e:
                self.show_error_message("Error", f"Could not create file: {str(e)}")

    def create_new_folder(self):
        """Create a new folder in current directory"""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                folder_path = os.path.join(self.current_folder, name)
                if os.path.exists(folder_path):
                    QMessageBox.warning(self, "Error", "A folder with that name already exists.")
                    return
                    
                os.makedirs(folder_path)
                self.update_icon_view(self.current_folder)
            except Exception as e:
                self.show_error_message("Error", f"Could not create folder: {str(e)}")

    def paste_to(self, dest_path):
        """Paste clipboard contents to destination"""
        operation, paths = self.clipboard_manager.get_current_operation()
        
        if not operation or not paths:
            return
        
        if len(paths) == 1:
            self.paste_single_item(paths[0], dest_path, operation)
        else:
            self.paste_multiple_items(paths, dest_path, operation)
        
        # Clear clipboard after move operation
        if operation == "cut":
            self.clipboard_manager.clear_current()
        
        # Refresh view
        self.update_icon_view(self.current_folder)

    def paste_single_item(self, src_path, dest_path, operation):
        """Paste a single item"""
        try:
            if not os.path.exists(src_path):
                QMessageBox.warning(self, "Error", f"Source file no longer exists: {os.path.basename(src_path)}")
                return
            
            src_name = os.path.basename(src_path)
            final_dest = os.path.join(dest_path, src_name)
            
            # Handle name conflicts
            counter = 1
            while os.path.exists(final_dest):
                name, ext = os.path.splitext(src_name)
                if operation == "copy":
                    final_dest = os.path.join(dest_path, f"{name} (copy {counter}){ext}")
                else:  # move
                    final_dest = os.path.join(dest_path, f"{name} ({counter}){ext}")
                counter += 1
            
            if operation == "copy":
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, final_dest)
                else:
                    shutil.copy2(src_path, final_dest)
                self.statusBar().showMessage(f"Copied: {src_name}", 3000)
            else:  # cut/move
                shutil.move(src_path, final_dest)
                self.statusBar().showMessage(f"Moved: {src_name}", 3000)
                
        except Exception as e:
            self.show_error_message("Paste Error", f"Could not paste: {src_name}", str(e))

    def paste_multiple_items(self, src_paths, dest_path, operation):
        """Paste multiple items with progress"""
        progress = QProgressDialog(f"{'Copying' if operation == 'copy' else 'Moving'} files...", "Cancel", 0, len(src_paths), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        success_count = 0
        errors = []
        
        for i, src_path in enumerate(src_paths):
            if progress.wasCanceled():
                break
                
            try:
                if not os.path.exists(src_path):
                    errors.append(f"Source no longer exists: {os.path.basename(src_path)}")
                    continue
                
                src_name = os.path.basename(src_path)
                progress.setLabelText(f"{'Copying' if operation == 'copy' else 'Moving'}: {src_name}")
                progress.setValue(i)
                
                final_dest = os.path.join(dest_path, src_name)
                
                # Handle name conflicts
                counter = 1
                while os.path.exists(final_dest):
                    name, ext = os.path.splitext(src_name)
                    if operation == "copy":
                        final_dest = os.path.join(dest_path, f"{name} (copy {counter}){ext}")
                    else:  # move
                        final_dest = os.path.join(dest_path, f"{name} ({counter}){ext}")
                    counter += 1
                
                if operation == "copy":
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, final_dest)
                    else:
                        shutil.copy2(src_path, final_dest)
                else:  # cut/move
                    shutil.move(src_path, final_dest)
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"Error with {os.path.basename(src_path)}: {str(e)}")
        
        progress.setValue(len(src_paths))
        progress.hide()
        
        # Show results
        if errors:
            error_msg = f"{'Copied' if operation == 'copy' else 'Moved'} {success_count} items successfully.\n\nErrors:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(self, "Operation Complete with Errors", error_msg)
        else:
            action_word = "Copied" if operation == "copy" else "Moved"
            self.statusBar().showMessage(f"{action_word} {success_count} items", 3000)

    def delete_file(self, path):
        """Delete a single file or folder"""
        try:
            name = os.path.basename(path)
            reply = QMessageBox.question(self, "Confirm Delete", 
                                       f"Are you sure you want to delete '{name}'?",
                                       QMessageBox.Yes | QMessageBox.No,
                                       QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                
                self.update_icon_view(self.current_folder)
                self.statusBar().showMessage(f"Deleted: {name}", 3000)
                
        except Exception as e:
            self.show_error_message("Delete Error", f"Could not delete: {os.path.basename(path)}", str(e))

    def delete_multiple_files(self, paths):
        """Delete multiple files/folders with confirmation"""
        if not paths:
            return
        
        count = len(paths)
        item_word = "item" if count == 1 else "items"
        
        reply = QMessageBox.question(self, "Confirm Delete",
                                   f"Are you sure you want to delete {count} {item_word}?",
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        success_count = 0
        errors = []
        
        for path in paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                success_count += 1
            except Exception as e:
                errors.append(f"Error deleting {os.path.basename(path)}: {str(e)}")
        
        # Refresh view
        self.update_icon_view(self.current_folder)
        
        # Show results
        if errors:
            error_msg = f"Deleted {success_count} items successfully.\n\nErrors:\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(self, "Delete Complete with Errors", error_msg)
        else:
            self.statusBar().showMessage(f"Deleted {success_count} items", 3000)

    def open_terminal_here(self, path):
        """Open terminal in the specified path"""
        try:
            if not PlatformUtils.open_terminal_at_path(path):
                QMessageBox.warning(self, "Error", "Could not open terminal at the specified location")
            else:
                self.statusBar().showMessage("Terminal opened", 2000)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open terminal: {str(e)}")

    def on_double_click(self, index):
        """Handle double-click events from tree or other views"""
        try:
            if hasattr(index, 'data'):
                file_path = index.data(Qt.UserRole)
                if file_path and os.path.isdir(file_path):
                    self.update_icon_view(file_path)
                elif file_path:
                    self.icon_double_clicked(file_path)
        except Exception as e:
            self.show_error_message("Navigation Error", "Could not navigate to selected item", str(e))

    def cut_action_triggered(self):
        """Handle cut action"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation("cut", self.selected_items.copy())
            self.clipboard_manager.add_to_history("cut", self.selected_items.copy())
            self.statusBar().showMessage(f"Cut {len(self.selected_items)} items", 2000)

    def copy_action_triggered(self):
        """Handle copy action"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation("copy", self.selected_items.copy())
            self.clipboard_manager.add_to_history("copy", self.selected_items.copy())
            self.statusBar().showMessage(f"Copied {len(self.selected_items)} items", 2000)

    def paste_action_triggered(self):
        """Handle paste action"""
        operation, paths = self.clipboard_manager.get_current_operation()
        
        if not operation or not paths:
            self.statusBar().showMessage("Nothing to paste", 2000)
            return
        
        # Paste to current folder
        self.paste_to(self.current_folder)

    # These are duplicate methods from earlier - removing since they're already defined above
    # def on_double_click(self, index):
    #     """Handle double-click events from tree or other views"""
    #     try:
    #         if hasattr(index, 'data'):
    #             file_path = index.data(Qt.UserRole)
    #             if file_path and os.path.isdir(file_path):
    #                 self.update_icon_view(file_path)
    #             elif file_path:
    #                 self.icon_double_clicked(file_path)
    #     except Exception as e:
    #         self.show_error_message("Navigation Error", "Could not navigate to selected item", str(e))

    def refresh_current_view(self):
        """Refresh the current view"""
        if hasattr(self, 'current_folder'):
            self.update_icon_view(self.current_folder)

    def deselect_icons(self):
        """Deselect all icons"""
        self.selected_items = []
        if hasattr(self, 'icon_container'):
            self.icon_container.clear_selection()
        self.on_selection_changed([])

    def select_all_items(self):
        """Select all items in current view"""
        try:
            all_items = []
            for item_name in os.listdir(self.current_folder):
                if not item_name.startswith('.') or getattr(self, 'show_hidden', False):
                    all_items.append(os.path.join(self.current_folder, item_name))
            
            self.selected_items = all_items
            # Update UI selection state
            if hasattr(self, 'icon_container'):
                self.icon_container.clear_selection()
                for path in all_items:
                    self.icon_container.add_to_selection_by_path(path)
            
            self.on_selection_changed(all_items)
            self.statusBar().showMessage(f"Selected {len(all_items)} items", 2000)
            
        except Exception as e:
            self.show_error_message("Selection Error", "Could not select all items", str(e))

    def delete_selected_items(self):
        """Delete currently selected items"""
        if self.selected_items:
            self.delete_multiple_files(self.selected_items)

    def rename_selected_item(self):
        """Rename the selected item (only works with single selection)"""
        if len(self.selected_items) == 1:
            self.rename_file(self.selected_items[0])
        elif len(self.selected_items) > 1:
            # For multiple selection, offer bulk rename
            reply = QMessageBox.question(self, "Bulk Rename", 
                                       f"You have {len(self.selected_items)} items selected. Would you like to bulk rename them?",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.show_bulk_rename_dialog()
        else:
            QMessageBox.information(self, "No Selection", "Please select an item to rename.")

    def set_thumbnail_size(self, size):
        """Set the thumbnail size and refresh the view"""
        self.thumbnail_size = size
        
        # Update checkmarks
        self.update_thumbnail_menu_checkmarks()
        
        # Save the setting
        self.save_last_dir(self.current_folder)
        
        # Refresh the current view with new thumbnail size
        self.update_icon_view(self.current_folder)

    def update_thumbnail_menu_checkmarks(self):
        """Update menu checkmarks based on current thumbnail size"""
        self.small_thumb_action.setChecked(self.thumbnail_size == 48)
        self.medium_thumb_action.setChecked(self.thumbnail_size == 64)
        self.large_thumb_action.setChecked(self.thumbnail_size == 96)
        self.xlarge_thumb_action.setChecked(self.thumbnail_size == 128)

    def set_icons_wide(self, width):
        """Set the number of icons wide and refresh the view"""
        self.icons_wide = width
        
        # Update checkmarks
        self.update_layout_menu_checkmarks()
        
        # Save the setting
        self.save_last_dir(self.current_folder)
        
        # Refresh the current view with new layout setting
        self.update_icon_view(self.current_folder)

    def update_layout_menu_checkmarks(self):
        """Update layout menu checkmarks based on current icons wide setting"""
        self.auto_width_action.setChecked(self.icons_wide == 0)
        self.fixed_4_wide_action.setChecked(self.icons_wide == 4)
        self.fixed_6_wide_action.setChecked(self.icons_wide == 6)
        self.fixed_8_wide_action.setChecked(self.icons_wide == 8)
        self.fixed_10_wide_action.setChecked(self.icons_wide == 10)
        self.fixed_12_wide_action.setChecked(self.icons_wide == 12)

    def update_dark_mode_checkmark(self):
        """Update dark mode menu checkmark"""
        self.dark_mode_action.setChecked(self.dark_mode)

    def toggle_dark_mode(self):
        """Toggle between dark and light mode"""
        self.dark_mode = not self.dark_mode
        self.apply_dark_mode()
        self.update_dark_mode_checkmark()
        
        # Save the setting immediately
        self.save_last_dir(self.current_folder)
        
        # Update all UI components instantly
        self.refresh_all_themes()

    def apply_dark_mode(self):
        """Apply dark mode styling"""
        if self.dark_mode:
            dark_style = """
                QMainWindow {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QWidget {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QTreeView {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    selection-background-color: #0078d4;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #2b2b2b;
                }
                QLabel {
                    color: #ffffff;
                    background-color: transparent;
                }
                QMenu {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555;
                }
                QMenu::item:selected {
                    background-color: #0078d4;
                }
                QToolBar {
                    background-color: #404040;
                    color: #ffffff;
                    border: none;
                }
                QTabWidget::pane {
                    background-color: #3c3c3c;
                    color: #ffffff;
                }
                QTabBar::tab {
                    background-color: #404040;
                    color: #ffffff;
                    padding: 8px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #0078d4;
                }
                QPlainTextEdit {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555;
                }
                QTextEdit {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555;
                }
            """
            self.setStyleSheet(dark_style)
        else:
            # Light mode - reset to default
            self.setStyleSheet("")
            
    def refresh_all_themes(self):
        """Update all UI components with current theme"""
        # Update preview pane background
        if hasattr(self, 'preview_pane') and self.preview_pane:
            self.update_preview_pane_theme()
            
        # Update icon container background
        if hasattr(self, 'icon_container') and self.icon_container:
            self.update_icon_container_theme()
            
        # Update tree view theme
        if hasattr(self, 'tree_view') and self.tree_view:
            self.update_tree_view_theme()
            
        # Update breadcrumb theme
        if hasattr(self, 'breadcrumb') and self.breadcrumb:
            self.update_breadcrumb_theme()
            
        # Update all existing icons
        if hasattr(self, 'icon_container') and self.icon_container:
            for i in range(self.icon_container.layout().count()):
                item = self.icon_container.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if hasattr(widget, 'update_style_for_theme'):
                        widget.update_style_for_theme(self.dark_mode)
                        
        # Force repaint
        self.repaint()
        
    def update_tree_view_theme(self):
        """Update tree view colors for current theme"""
        if self.dark_mode:
            style = """
                QTreeView {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    selection-background-color: #0078d4;
                    selection-color: #ffffff;
                    border: 1px solid #555;
                }
                QTreeView::item {
                    padding: 2px;
                }
                QTreeView::item:hover {
                    background-color: #4a4a4a;
                }
                QTreeView::item:selected {
                    background-color: #0078d4;
                }
                QHeaderView::section {
                    background-color: #404040;
                    color: #ffffff;
                    border: 1px solid #555;
                    padding: 4px;
                }
            """
        else:
            style = ""
        self.tree_view.setStyleSheet(style)
        
    def update_breadcrumb_theme(self):
        """Update breadcrumb colors for current theme"""
        if self.dark_mode:
            style = """
                QWidget {
                    background-color: #404040;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: transparent;
                    color: #ffffff;
                    border: none;
                    padding: 4px 8px;
                    text-decoration: underline;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QPushButton:pressed {
                    background-color: #0078d4;
                }
                QLabel {
                    color: #cccccc;
                }
            """
        else:
            style = ""
        self.breadcrumb.setStyleSheet(style)
        
    def update_preview_pane_theme(self):
        """Update preview pane colors for current theme"""
        if self.dark_mode:
            style = """
                QWidget {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                    border: 1px solid #555;
                }
                QLabel {
                    background-color: transparent;
                    color: #ffffff;
                }
                QPlainTextEdit {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555;
                }
            """
        else:
            style = ""
        self.preview_pane.setStyleSheet(style)
        
    def update_icon_container_theme(self):
        """Update icon container background for current theme"""
        if self.dark_mode:
            style = """
                QWidget {
                    background-color: #2b2b2b;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                }
            """
        else:
            style = ""
        self.icon_container.setStyleSheet(style)
        if hasattr(self, 'icon_scroll_area'):
            self.icon_scroll_area.setStyleSheet(style)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def apply_theme(self):
        """Apply the current theme (dark or light mode)"""
        if self.dark_mode:
            # Dark mode styling
            dark_style = """
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTreeView {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #555555;
                selection-background-color: #0078d7;
            }
            QScrollArea {
                background-color: #2b2b2b;
                border: none;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #0078d7;
            }
            QMenuBar {
                background-color: #363636;
                color: #ffffff;
                border-bottom: 1px solid #555555;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #0078d7;
            }
            QMenu {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: #0078d7;
            }
            QToolBar {
                background-color: #404040;
                color: #ffffff;
                border: none;
                spacing: 3px;
            }
            QToolBar QToolButton {
                background-color: #404040;
                color: #ffffff;
                border: none;
                padding: 5px;
                margin: 1px;
            }
            QToolBar QToolButton:hover {
                background-color: #505050;
            }
            QStatusBar {
                background-color: #363636;
                color: #ffffff;
                border-top: 1px solid #555555;
            }
            """
            self.setStyleSheet(dark_style)
            
            # Apply dark theme to custom widgets
            for widget in self.findChildren(IconWidget):
                widget.update_style_for_theme(True)
        else:
            # Light mode (default)
            self.setStyleSheet("")
            
            # Apply light theme to custom widgets
            for widget in self.findChildren(IconWidget):
                widget.update_style_for_theme(False)
        
        # Update breadcrumb styling
        breadcrumb_style = """
            QWidget {
                background-color: rgba(0, 120, 215, 0.1);
                border: 1px solid rgba(0, 120, 215, 0.3);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QWidget:hover {
                background-color: rgba(0, 120, 215, 0.2);
            }
            QLabel {
                background: transparent;
                border: none;
                padding: 2px;
            }
            QLabel:hover {
                color: #0078d7;
                text-decoration: underline;
            }
            """ if not self.dark_mode else """
            QWidget {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                color: #ffffff;
            }
            QWidget:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QLabel {
                background: transparent;
                border: none;
                padding: 2px;
                color: #ffffff;
            }
            QLabel:hover {
                color: #ffffff;
                text-decoration: underline;
            }
            """
        
        # Apply missing methods placeholder
        breadcrumb_style += """
            /* Additional breadcrumb styling */
            QLabel[class="breadcrumb-separator"] {
                color: gray;
            }
        """
        
        if hasattr(self, 'breadcrumb'):
            self.breadcrumb.setStyleSheet(breadcrumb_style)

    def show_about_dialog(self):
        """Show the about dialog"""
        about_text = "gary simple file manager\nversion 0.4.4\n2025\n\n"
        about_text += "Enhanced Features:\n"
        about_text += "- Multiple view modes (Icon, List, Detail)\n"
        about_text += "- Advanced file operations\n"
        about_text += "- Search and filter system\n"
        about_text += "- File preview pane\n"
        about_text += "- Advanced clipboard with history\n"
        about_text += "- Resizable panels and toolbars\n\n"
        about_text += "Cross-platform compatibility"
        QMessageBox.about(self, "About garysfm Enhanced", about_text)

    def show_contact_dialog(self):
        """Show the contact dialog with clickable email"""
        # Create a custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Contact Me")
        dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Contact message
        contact_label = QLabel("For questions or feedback, please contact:")
        contact_label.setWordWrap(True)
        layout.addWidget(contact_label)
        
        # Clickable email button
        email_button = QPushButton("gary@gmail.com")
        email_button.setStyleSheet("QPushButton { text-align: left; border: none; color: blue; }")
        email_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("mailto:gary@gmail.com")))
        layout.addWidget(email_button)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def show_preferences(self):
        """Show preferences dialog (placeholder for future implementation)"""
        # For now, show a simple message
        QMessageBox.information(self, "Preferences", "Preferences dialog coming soon!")
    
    def toggle_show_hidden_files(self):
        """Toggle showing hidden files (placeholder for future implementation)"""
        # For now, show a simple message
        QMessageBox.information(self, "Hidden Files", "Show/hide hidden files coming soon!")
    
    def open_new_tab(self):
        """Open new tab (placeholder for future implementation)"""
        # For now, show a simple message
        QMessageBox.information(self, "New Tab", "Tabbed interface coming soon!")
    
    def move_to_trash(self):
        """Move selected items to trash (cross-platform)"""
        selected_items = self.get_selected_items()
        if not selected_items:
            return
        
        # Try to use cross-platform trash functionality
        try:
            # First try send2trash if available
            try:
                import send2trash
                for item_path in selected_items:
                    send2trash.send2trash(item_path)
                self.refresh_current_view()
                QMessageBox.information(self, "Success", f"Moved {len(selected_items)} item(s) to trash.")
                return
            except ImportError:
                pass
            
            # Platform-specific trash implementations
            success_count = 0
            errors = []
            
            for item_path in selected_items:
                try:
                    if PlatformUtils.is_windows():
                        # Windows Recycle Bin using shell commands
                        try:
                            import winshell
                            winshell.delete_file(item_path)
                            success_count += 1
                        except ImportError:
                            # Fallback to PowerShell command
                            cmd = f'powershell.exe -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(\'{item_path}\', \'OnlyErrorDialogs\', \'SendToRecycleBin\')"'
                            subprocess.run(cmd, shell=True, check=True)
                            success_count += 1
                    elif PlatformUtils.is_macos():
                        # macOS Trash
                        subprocess.run(["osascript", "-e", f'tell app "Finder" to delete POSIX file "{item_path}"'], check=True)
                        success_count += 1
                    else:  # Linux
                        # Use gio trash if available
                        subprocess.run(["gio", "trash", item_path], check=True)
                        success_count += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(item_path)}: {str(e)}")
            
            if success_count > 0:
                self.refresh_current_view()
                if errors:
                    error_msg = f"Moved {success_count} item(s) to trash.\nErrors:\n" + "\n".join(errors[:5])
                    if len(errors) > 5:
                        error_msg += f"\n... and {len(errors) - 5} more errors"
                    QMessageBox.warning(self, "Partial Success", error_msg)
                else:
                    QMessageBox.information(self, "Success", f"Moved {success_count} item(s) to trash.")
            else:
                raise Exception("Could not move any items to trash")
                
        except Exception as e:
            # Final fallback to regular delete with confirmation
            reply = QMessageBox.question(
                self, 
                "Move to Trash", 
                f"Trash functionality not available. Permanently delete {len(selected_items)} item(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.delete_selected_items()

    def sync_tree_view_selection(self, folder_path):
        """Synchronize tree view selection with the given folder path"""
        try:
            index = self.model.index(folder_path)
            if index.isValid():
                self.tree_view.setCurrentIndex(index)
                self.tree_view.expand(index)
        except Exception as e:
            # If sync fails, just continue - it's not critical
            pass


class ClipboardHistoryDialog(QDialog):
    """Dialog for showing clipboard history"""
    def __init__(self, clipboard_manager, parent=None):
        super().__init__(parent)
        self.clipboard_manager = clipboard_manager
        self.selected_entry = None
        self.setup_ui()
        self.load_history()
    
    def setup_ui(self):
        self.setWindowTitle("Clipboard History")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QVBoxLayout()
        
        # History list
        self.history_list = QTableView()
        self.history_model = QStandardItemModel()
        self.history_model.setHorizontalHeaderLabels(['Operation', 'Files', 'Time'])
        self.history_list.setModel(self.history_model)
        self.history_list.setSelectionBehavior(QTableView.SelectRows)
        layout.addWidget(self.history_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.use_button = QPushButton("Use Selected")
        self.use_button.clicked.connect(self.use_selected)
        button_layout.addWidget(self.use_button)
        
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self.clear_history)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_history(self):
        """Load clipboard history into the table"""
        history = self.clipboard_manager.get_history()
        
        for entry in history:
            operation_item = QStandardItem(entry['operation'].capitalize())
            
            files_text = f"{len(entry['paths'])} files"
            if len(entry['paths']) == 1:
                files_text = os.path.basename(entry['paths'][0])
            files_item = QStandardItem(files_text)
            
            time_item = QStandardItem(entry['timestamp'].strftime('%Y-%m-%d %H:%M'))
            
            self.history_model.appendRow([operation_item, files_item, time_item])
        
        self.history_list.resizeColumnsToContents()
    
    def use_selected(self):
        """Use the selected history entry"""
        selection = self.history_list.selectionModel().selectedRows()
        if selection:
            row = selection[0].row()
            history = self.clipboard_manager.get_history()
            if row < len(history):
                self.selected_entry = history[row]
                self.accept()
    
    def clear_history(self):
        """Clear the clipboard history"""
        self.clipboard_manager.history.clear()
        self.history_model.clear()
        self.history_model.setHorizontalHeaderLabels(['Operation', 'Files', 'Time'])
    
    def get_selected_entry(self):
        """Get the selected history entry"""
        return self.selected_entry

class AdvancedOperationsDialog(QDialog):
    """Dialog for advanced file operations"""
    def __init__(self, selected_items, current_folder, parent=None):
        super().__init__(parent)
        self.selected_items = selected_items
        self.current_folder = current_folder
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Advanced Operations")
        self.setModal(True)
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(f"Selected {len(self.selected_items)} item(s):"))
        
        # List selected items
        items_list = QTextEdit()
        items_list.setMaximumHeight(100)
        items_list.setReadOnly(True)
        items_text = "\n".join([os.path.basename(item) for item in self.selected_items])
        items_list.setPlainText(items_text)
        layout.addWidget(items_list)
        
        # Operations
        layout.addWidget(QLabel("Operations:"))
        
        self.compress_btn = QPushButton("Create Archive (.zip)")
        self.compress_btn.clicked.connect(self.create_archive)
        layout.addWidget(self.compress_btn)
        
        self.calculate_size_btn = QPushButton("Calculate Total Size")
        self.calculate_size_btn.clicked.connect(self.calculate_size)
        layout.addWidget(self.calculate_size_btn)
        
        self.duplicate_btn = QPushButton("Duplicate Items")
        self.duplicate_btn.clicked.connect(self.duplicate_items)
        layout.addWidget(self.duplicate_btn)
        
        # Results area
        self.results_text = QTextEdit()
        self.results_text.setMaximumHeight(100)
        self.results_text.setReadOnly(True)
        layout.addWidget(self.results_text)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def create_archive(self):
        """Create a zip archive of selected items"""
        try:
            import zipfile
            archive_name = f"archive_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            archive_path = os.path.join(self.current_folder, archive_name)
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item_path in self.selected_items:
                    if os.path.isfile(item_path):
                        zipf.write(item_path, os.path.basename(item_path))
                    elif os.path.isdir(item_path):
                        for root, dirs, files in os.walk(item_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arc_path = os.path.relpath(file_path, os.path.dirname(item_path))
                                zipf.write(file_path, arc_path)
            
            self.results_text.append(f"Archive created: {archive_name}")
        except Exception as e:
            self.results_text.append(f"Archive creation failed: {str(e)}")
    
    def calculate_size(self):
        """Calculate total size of selected items"""
        total_size = 0
        file_count = 0
        folder_count = 0
        
        for item_path in self.selected_items:
            if os.path.isfile(item_path):
                total_size += os.path.getsize(item_path)
                file_count += 1
            elif os.path.isdir(item_path):
                folder_count += 1
                for root, dirs, files in os.walk(item_path):
                    for file in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, file))
                            file_count += 1
                        except:
                            continue
        
        # Format size
        def format_size(size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"
        
        result = f"Total size: {format_size(total_size)}\n"
        result += f"Files: {file_count}, Folders: {folder_count}"
        self.results_text.append(result)
    
    def duplicate_items(self):
        """Create duplicates of selected items"""
        success_count = 0
        for item_path in self.selected_items:
            try:
                base_name = os.path.basename(item_path)
                name, ext = os.path.splitext(base_name)
                duplicate_name = f"{name}_copy{ext}"
                duplicate_path = os.path.join(os.path.dirname(item_path), duplicate_name)
                
                # Find unique name if duplicate already exists
                counter = 1
                while os.path.exists(duplicate_path):
                    duplicate_name = f"{name}_copy_{counter}{ext}"
                    duplicate_path = os.path.join(os.path.dirname(item_path), duplicate_name)
                    counter += 1
                
                if os.path.isfile(item_path):
                    shutil.copy2(item_path, duplicate_path)
                elif os.path.isdir(item_path):
                    shutil.copytree(item_path, duplicate_path)
                
                success_count += 1
            except Exception as e:
                self.results_text.append(f"Failed to duplicate {base_name}: {str(e)}")
        
        self.results_text.append(f"Successfully duplicated {success_count} item(s)")

    def navigate_to_path(self, path):
        """Navigate to a specific path (called from breadcrumb)"""
        try:
            if os.path.exists(path) and os.path.isdir(path):
                index = self.model.index(path)
                self.tree_view.setCurrentIndex(index)
                self.tree_view.expand(index)
                self.update_icon_view(path)
            else:
                self.show_error_message("Navigation Error", f"Path no longer exists: {path}")
        except Exception as e:
            self.show_error_message("Navigation Error", f"Cannot navigate to {path}: {str(e)}")
            
    def safe_update_status_bar(self):
        """Safely update status bar with error protection"""
        try:
            if hasattr(self, 'status_bar') and self.status_bar is not None:
                self.update_status_bar()
        except Exception as e:
            print(f"Status bar update failed: {str(e)}")  # Debug output
            
    def update_status_bar(self):
        """Update status bar with current selection and folder info"""
        # Check if status bar exists
        if not hasattr(self, 'status_bar') or self.status_bar is None:
            return
            
        try:
            selected_count = len(self.selected_items)
            if selected_count == 0:
                # Show folder info
                if self.current_folder and os.path.exists(self.current_folder):
                    try:
                        items = os.listdir(self.current_folder)
                        folder_count = sum(1 for item in items if os.path.isdir(os.path.join(self.current_folder, item)))
                        file_count = len(items) - folder_count
                        self.status_bar.showMessage(f"{file_count} files, {folder_count} folders")
                    except (OSError, PermissionError):
                        self.status_bar.showMessage("Cannot read folder contents")
                else:
                    self.status_bar.showMessage("Ready")
            elif selected_count == 1:
                # Show single item info
                item_path = self.selected_items[0]
                if os.path.exists(item_path):
                    if os.path.isdir(item_path):
                        self.status_bar.showMessage(f"1 folder selected: {os.path.basename(item_path)}")
                    else:
                        try:
                            size = os.path.getsize(item_path)
                            size_str = self.format_file_size(size)
                            self.status_bar.showMessage(f"1 file selected: {os.path.basename(item_path)} ({size_str})")
                        except OSError:
                            self.status_bar.showMessage(f"1 file selected: {os.path.basename(item_path)}")
                else:
                    self.status_bar.showMessage("1 item selected (no longer exists)")
            else:
                # Show multiple items info
                self.status_bar.showMessage(f"{selected_count} items selected")
        except Exception as e:
            # Fallback to basic message if status update fails
            if hasattr(self, 'status_bar') and self.status_bar is not None:
                self.status_bar.showMessage(f"Status update error: {str(e)}")
            else:
                print(f"Status bar error: {str(e)}")  # Debug output
            
    def format_file_size(self, size):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
        
    def show_error_message(self, title, message, details=None):
        """Improved error handling with consistent error display"""
        self.error_count += 1
        
        # Log error (in a real app, this would go to a log file)
        print(f"Error #{self.error_count}: {title} - {message}")
        if details:
            print(f"Details: {details}")
            
        # Show error dialog
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle(title)
        error_box.setText(message)
        
        if details:
            error_box.setDetailedText(details)
            
        # Add helpful buttons
        error_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Help)
        error_box.setDefaultButton(QMessageBox.Ok)
        
        result = error_box.exec_()
        if result == QMessageBox.Help:
            # In a real app, this could open help documentation
            QMessageBox.information(self, "Help", 
                "Try refreshing the view (F5) or navigating to a different folder.\n"
                "If problems persist, restart the application.")
                
    def delete_selected_items(self):
        """Delete currently selected items (keyboard shortcut handler)"""
        if self.selected_items:
            if len(self.selected_items) == 1:
                self.delete_file(self.selected_items[0])
            else:
                self.delete_multiple_files(self.selected_items)
                
    def rename_selected_item(self):
        """Rename currently selected item (keyboard shortcut handler)"""
        if len(self.selected_items) == 1:
            self.rename_file(self.selected_items[0])
            
    def refresh_current_view(self):
        """Refresh the current folder view (F5)"""
        self.update_icon_view(self.current_folder)
        
    def select_all_items(self):
        """Select all items in current folder (Ctrl+A)"""
        if hasattr(self, 'icon_container'):
            layout = self.icon_container.layout()
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if hasattr(widget, 'full_path'):
                        self.icon_container.add_to_selection(widget)
                        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode (F11)"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def update_thumbnail_menu_checkmarks(self):
        """Update menu checkmarks based on current thumbnail size"""
        self.small_thumb_action.setChecked(self.thumbnail_size == 48)
        self.medium_thumb_action.setChecked(self.thumbnail_size == 64)
        self.large_thumb_action.setChecked(self.thumbnail_size == 96)
        self.xlarge_thumb_action.setChecked(self.thumbnail_size == 128)

    def update_dark_mode_checkmark(self):
        """Update dark mode menu checkmark"""
        self.dark_mode_action.setChecked(self.dark_mode)

    def toggle_dark_mode(self):
        """Toggle between dark and light mode"""
        self.dark_mode = not self.dark_mode
        self.update_dark_mode_checkmark()
        self.save_last_dir(self.current_folder)  # Save the setting
        self.apply_theme()

    def apply_theme(self):
        """Apply the current theme (dark or light mode)"""
        if self.dark_mode:
            # Dark mode styling
            dark_style = """
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTreeView {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #555555;
                selection-background-color: #0078d7;
            }
            QScrollArea {
                background-color: #2b2b2b;
                border: none;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #0078d7;
            }
            QMenuBar {
                background-color: #363636;
                color: #ffffff;
                border-bottom: 1px solid #555555;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #0078d7;
            }
            QMenu {
                background-color: #363636;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #0078d7;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 3px;
                border-radius: 3px;
            }
            QTextEdit {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #555555;
            }
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QRadioButton {
                color: #ffffff;
            }
            QCheckBox {
                color: #ffffff;
            }
            QStatusBar {
                background-color: #2b2b2b;
                color: #ffffff;
                border-top: 1px solid #555555;
            }
            """
            self.setStyleSheet(dark_style)
            
            # Update breadcrumb style for dark mode
            self.update_breadcrumb_style(True)
        else:
            # Light mode (default)
            self.setStyleSheet("")
            # Update breadcrumb style for light mode
            self.update_breadcrumb_style(False)
        
        # Refresh the icon view to update icon widget styles
        self.update_icon_view(self.current_folder)
        
    def update_breadcrumb_style(self, dark_mode):
        """Update breadcrumb button styles based on theme"""
        if dark_mode:
            breadcrumb_style = """
                QPushButton {
                    border: none;
                    padding: 2px 6px;
                    color: #66b3ff;
                    text-decoration: underline;
                    text-align: left;
                    background-color: transparent;
                }
                QPushButton:hover {
                    background-color: rgba(102, 179, 255, 0.2);
                }
                QPushButton:pressed {
                    background-color: rgba(102, 179, 255, 0.3);
                }
                QLabel {
                    color: #888888;
                }
            """
        else:
            breadcrumb_style = """
                QPushButton {
                    border: none;
                    padding: 2px 6px;
                    color: #0066cc;
                    text-decoration: underline;
                    text-align: left;
                    background-color: transparent;
                }
                QPushButton:hover {
                    background-color: rgba(0, 102, 204, 0.1);
                }
                QPushButton:pressed {
                    background-color: rgba(0, 102, 204, 0.2);
                }
                QLabel {
                    color: gray;
                }
            """
        
        if hasattr(self, 'breadcrumb'):
            self.breadcrumb.setStyleSheet(breadcrumb_style)

    def set_thumbnail_size(self, size):
        """Set the thumbnail size and refresh the view"""
        self.thumbnail_size = size
        
        # Update checkmarks
        self.update_thumbnail_menu_checkmarks()
        
        # Save the setting
        self.save_last_dir(self.current_folder)
        
        # Refresh the current view with new thumbnail size
        self.update_icon_view(self.current_folder)

    def show_about_dialog(self):
        """Show the about dialog"""
        about_text = "gary simple file manager\nversion 0.4.4\n2025\n\n"
        about_text += "Enhanced Features:\n"
        about_text += "- Multiple view modes (Icon, List, Detail)\n"
        about_text += "- Advanced file operations\n"
        about_text += "- Search and filter system\n"
        about_text += "- File preview pane\n"
        about_text += "- Advanced clipboard with history\n"
        about_text += "- Resizable panels and toolbars\n\n"
        about_text += "Cross-platform compatibility"
        QMessageBox.about(self, "About garysfm Enhanced", about_text)

    def show_contact_dialog(self):
        """Show the contact dialog with clickable email"""
        # Create a custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Contact Me")
        dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Contact message
        contact_label = QLabel("For questions or feedback, please contact:")
        contact_label.setWordWrap(True)
        layout.addWidget(contact_label)
        
        # Clickable email button
        email_button = QPushButton("gary@turkokards.com")
        email_button.clicked.connect(lambda: webbrowser.open("mailto:gary@turkokards.com"))
        email_button.setStyleSheet("QPushButton { text-decoration: underline; color: blue; }")
        layout.addWidget(email_button)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        dialog.setLayout(layout)
        dialog.exec_()

def main():
    """Main function to run the enhanced file manager"""
    # Enable high DPI scaling BEFORE creating QApplication
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Set application properties for better cross-platform integration
    app.setApplicationName("garysfm")
    app.setApplicationVersion("0.4.4")
    app.setApplicationDisplayName("Gary's Simple File Manager")
    app.setOrganizationName("turkokards")
    app.setOrganizationDomain("turkokards.com")
    
    # Platform-specific application properties
    if PlatformUtils.is_macos():
        app.setQuitOnLastWindowClosed(True)  # Standard macOS behavior
        # Set macOS application bundle properties if needed
    elif PlatformUtils.is_windows():
        # Windows-specific settings
        try:
            import ctypes
            # Set Windows taskbar icon
            myappid = 'turkokards.garysfm.filemanager.044'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except:
            pass
    # Linux doesn't need special setup
    
    # Create and show the main window
    window = SimpleFileManager()
    window.show()
    
    # Handle platform-specific window placement
    if PlatformUtils.is_windows():
        # Center window on Windows
        screen = app.desktop().screenGeometry()
        size = window.geometry()
        window.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

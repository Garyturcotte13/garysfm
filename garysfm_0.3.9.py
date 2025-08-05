import sys
import os
import shutil
import subprocess
import json
import webbrowser
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QFileSystemModel,
    QVBoxLayout, QWidget, QHBoxLayout, QMessageBox, QGridLayout,
    QSizePolicy, QLabel, QAction, QPushButton, QScrollArea, QMenu, QInputDialog, QFileIconProvider,
    QDialog, QLineEdit, QRadioButton, QButtonGroup, QTextEdit, QCheckBox
)
from PyQt5.QtCore import QDir, Qt, pyqtSignal, QFileInfo, QPoint, QRect
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen

class IconWidget(QWidget):
    clicked = pyqtSignal(str, object)  # Pass the event modifiers
    doubleClicked = pyqtSignal(str)
    rightClicked = pyqtSignal(str, QPoint)

    def __init__(self, file_name: str, full_path: str, is_dir: bool, thumbnail_size: int = 64, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.full_path = full_path
        self.is_dir = is_dir
        self.thumbnail_size = thumbnail_size
        
        layout = QVBoxLayout()
        
        # Create icon or thumbnail
        pixmap = self.create_icon_or_thumbnail(full_path, is_dir)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        
        # Create label with filename
        self.label = QLabel(file_name)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setToolTip(full_path)
        self.setStyleSheet("QWidget { border: 2px solid transparent; }")

    def update_style_for_theme(self, dark_mode):
        """Update the widget style based on the current theme"""
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
        
        if is_dir:
            # Create folder preview with thumbnails
            folder_preview = self.create_folder_preview(full_path, size)
            painter.drawPixmap(0, 0, folder_preview)
        else:
            # Check if it's an image file
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.svg'}
            file_ext = os.path.splitext(full_path)[1].lower()
            
            if file_ext in image_extensions:
                try:
                    # Try to create thumbnail from image
                    original_pixmap = QPixmap(full_path)
                    if not original_pixmap.isNull():
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
                        icon_provider = QFileIconProvider()
                        icon = icon_provider.icon(QFileInfo(full_path))
                        file_pixmap = icon.pixmap(size, size)
                        
                        # Center the file icon
                        x = (size - file_pixmap.width()) // 2
                        y = (size - file_pixmap.height()) // 2
                        painter.drawPixmap(x, y, file_pixmap)
                except Exception:
                    # Fall back to default file icon if thumbnail creation fails
                    icon_provider = QFileIconProvider()
                    icon = icon_provider.icon(QFileInfo(full_path))
                    file_pixmap = icon.pixmap(size, size)
                    
                    # Center the file icon
                    x = (size - file_pixmap.width()) // 2
                    y = (size - file_pixmap.height()) // 2
                    painter.drawPixmap(x, y, file_pixmap)
            else:
                # Use default file icon for non-images
                icon_provider = QFileIconProvider()
                icon = icon_provider.icon(QFileInfo(full_path))
                file_pixmap = icon.pixmap(size, size)
                
                # Center the file icon
                x = (size - file_pixmap.width()) // 2
                y = (size - file_pixmap.height()) // 2
                painter.drawPixmap(x, y, file_pixmap)
        
        painter.end()
        return framed_pixmap

    def create_folder_preview(self, folder_path, size):
        """Create a folder icon with preview thumbnails of images inside"""
        preview_pixmap = QPixmap(size, size)
        preview_pixmap.fill(Qt.transparent)
        
        painter = QPainter(preview_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Start with the default folder icon as background
        icon_provider = QFileIconProvider()
        folder_icon = icon_provider.icon(QFileIconProvider.Folder)
        folder_pixmap = folder_icon.pixmap(size, size)
        
        # Center and draw the folder icon
        x = (size - folder_pixmap.width()) // 2
        y = (size - folder_pixmap.height()) // 2
        painter.drawPixmap(x, y, folder_pixmap)
        
        # Try to find image files in the folder for preview
        try:
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'}
            image_files = []
            
            # Get first few image files from the folder
            files = os.listdir(folder_path)
            for file_name in files:
                if len(image_files) >= 4:  # Limit to 4 images max
                    break
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext in image_extensions:
                    file_path = os.path.join(folder_path, file_name)
                    if os.path.isfile(file_path):
                        image_files.append(file_path)
            
            # If we found images, create small previews
            if image_files:
                preview_size = size // 4  # Each preview is 1/4 the size
                positions = [
                    (size - preview_size - 2, 2),  # Top right
                    (size - preview_size - 2, preview_size + 4),  # Middle right
                    (size - preview_size * 2 - 4, 2),  # Top, second from right
                    (size - preview_size * 2 - 4, preview_size + 4)  # Middle, second from right
                ]
                
                for i, img_path in enumerate(image_files[:4]):
                    try:
                        img_pixmap = QPixmap(img_path)
                        if not img_pixmap.isNull():
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
        self.setLayout(QGridLayout())
        self.drag_start = None
        self.drag_end = None
        self.selection_rect = QRect()
        self.is_dragging = False
        self.selected_widgets = set()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.pos()
            self.is_dragging = True
            # If not holding Ctrl, clear previous selection
            if not (event.modifiers() & Qt.ControlModifier):
                self.clear_selection()
            self.emptySpaceClicked.emit()
        elif event.button() == Qt.RightButton:
            self.emptySpaceRightClicked.emit(event.globalPos())

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

class SimpleFileManager(QMainWindow):
    SETTINGS_FILE = "filemanager_settings.json"

    def __init__(self):
        super().__init__()
        self.clipboard_data = None
        self.thumbnail_size = 64  # Default thumbnail size
        self.dark_mode = False  # Default to light mode
        self.last_dir = self.load_last_dir() or QDir.rootPath()
        self.current_folder = self.last_dir  # Track current folder for right-click actions
        self.selected_icon = None  # Track selected icon
        self.selected_items = []  # Track multiple selected items
        self.main_widget = QWidget()
        self.main_layout = QHBoxLayout()
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)

        # Left pane: tree view and controls
        self.left_pane = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_pane.setLayout(self.left_layout)
        self.main_layout.addWidget(self.left_pane, 1)  # 1/5 width

        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.rootPath())
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(self.last_dir))
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_double_click)
        self.left_layout.addWidget(self.tree_view)

        # Right pane: icon view of selected folder contents
        self.right_pane = QWidget()
        self.right_layout = QVBoxLayout()
        self.right_pane.setLayout(self.right_layout)
        self.main_layout.addWidget(self.right_pane, 4)  # 4/5 width

        # Go Up button
        self.go_up_button = QPushButton("Go Up")
        self.go_up_button.clicked.connect(self.go_up)
        self.right_layout.addWidget(self.go_up_button)

        # Scroll area for icons
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.icon_container = IconContainer()
        self.icon_container.emptySpaceClicked.connect(self.deselect_icons)
        self.icon_container.emptySpaceRightClicked.connect(self.empty_space_right_clicked)
        self.icon_container.selectionChanged.connect(self.on_selection_changed)
        self.icon_grid = self.icon_container.layout()
        self.scroll_area.setWidget(self.icon_container)
        self.right_layout.addWidget(self.scroll_area)

        self.setWindowTitle('garysfm')
        self.resize(900, 600)
        self.update_icon_view(self.last_dir)

        # Menu bar for Cut, Copy, Paste actions
        menu_bar = self.menuBar()
        edit_menu = menu_bar.addMenu("Edit")
        self.cut_action = QAction("Cut", self)
        self.copy_action = QAction("Copy", self)
        self.paste_action = QAction("Paste", self)
        self.cut_action.triggered.connect(self.cut_action_triggered)
        self.copy_action.triggered.connect(self.copy_action_triggered)
        self.paste_action.triggered.connect(self.paste_action_triggered)
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        
        edit_menu.addSeparator()  # Add separator before bulk rename
        self.bulk_rename_action = QAction("Bulk Rename...", self)
        self.bulk_rename_action.triggered.connect(self.show_bulk_rename_dialog)
        edit_menu.addAction(self.bulk_rename_action)

        # View menu for thumbnail size options
        view_menu = menu_bar.addMenu("View")
        
        # Thumbnail size submenu
        thumbnail_menu = view_menu.addMenu("Thumbnail Size")
        self.small_thumb_action = QAction("Small (48px)", self, checkable=True)
        self.medium_thumb_action = QAction("Medium (64px)", self, checkable=True)
        self.large_thumb_action = QAction("Large (96px)", self, checkable=True)
        self.xlarge_thumb_action = QAction("Extra Large (128px)", self, checkable=True)
        
        # Set default selection
        self.medium_thumb_action.setChecked(True)
        
        # Connect actions
        self.small_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(48))
        self.medium_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(64))
        self.large_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(96))
        self.xlarge_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(128))
        
        thumbnail_menu.addAction(self.small_thumb_action)
        thumbnail_menu.addAction(self.medium_thumb_action)
        thumbnail_menu.addAction(self.large_thumb_action)
        thumbnail_menu.addAction(self.xlarge_thumb_action)

        # Dark mode toggle
        view_menu.addSeparator()
        self.dark_mode_action = QAction("Dark Mode", self, checkable=True)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        view_menu.addAction(self.dark_mode_action)

        # Update menu checkmarks based on loaded thumbnail size
        self.update_thumbnail_menu_checkmarks()
        
        # Apply saved dark mode setting
        self.update_dark_mode_checkmark()
        self.apply_theme()

        # Info menu for about dialog
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

        # For right-click context menu
        self.current_right_clicked_path = None

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
            """
            self.setStyleSheet(dark_style)
        else:
            # Light mode (default)
            self.setStyleSheet("")
        
        # Refresh the icon view to update icon widget styles
        self.update_icon_view(self.current_folder)

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
        QMessageBox.about(self, "About garysfm", 
                         "gary simple file manager\nversion 0.3.9\n2025")

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

    def open_website(self):
        """Open the website in the default browser"""
        webbrowser.open("https://turkokards.com")

    def show_bulk_rename_dialog(self):
        """Show bulk rename dialog for selected files or all files in current directory"""
        # Determine which files to rename
        if self.selected_items:
            files_to_rename = [path for path in self.selected_items if os.path.isfile(path)]
            dialog_title = f"Bulk Rename {len(files_to_rename)} Selected Files"
        else:
            # Get all files in current directory (excluding folders)
            try:
                all_items = os.listdir(self.current_folder)
                files_to_rename = [os.path.join(self.current_folder, item) 
                                 for item in all_items 
                                 if os.path.isfile(os.path.join(self.current_folder, item)) 
                                 and not item.startswith('.')]
                dialog_title = f"Bulk Rename All {len(files_to_rename)} Files in Directory"
            except Exception:
                QMessageBox.warning(self, "Error", "Cannot access current directory for bulk rename.")
                return
        
        if not files_to_rename:
            QMessageBox.information(self, "No Files", "No files available for bulk rename.")
            return
        
        # Create bulk rename dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(dialog_title)
        dialog.setFixedSize(500, 400)
        
        layout = QVBoxLayout()
        
        # Operation selection
        operation_label = QLabel("Select Operation:")
        layout.addWidget(operation_label)
        
        self.operation_group = QButtonGroup()
        self.add_prefix_radio = QRadioButton("Add prefix to filename")
        self.add_suffix_radio = QRadioButton("Add suffix to filename (before extension)")
        self.remove_pattern_radio = QRadioButton("Remove pattern from filename")
        self.replace_pattern_radio = QRadioButton("Replace pattern in filename")
        
        self.add_prefix_radio.setChecked(True)  # Default selection
        
        self.operation_group.addButton(self.add_prefix_radio)
        self.operation_group.addButton(self.add_suffix_radio)
        self.operation_group.addButton(self.remove_pattern_radio)
        self.operation_group.addButton(self.replace_pattern_radio)
        
        layout.addWidget(self.add_prefix_radio)
        layout.addWidget(self.add_suffix_radio)
        layout.addWidget(self.remove_pattern_radio)
        layout.addWidget(self.replace_pattern_radio)
        
        # Pattern input
        pattern_label = QLabel("Pattern/Text:")
        layout.addWidget(pattern_label)
        
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("Enter text to add/remove/replace")
        layout.addWidget(self.pattern_input)
        
        # Replacement text (only for replace operation)
        self.replacement_label = QLabel("Replace with:")
        layout.addWidget(self.replacement_label)
        
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Enter replacement text")
        layout.addWidget(self.replacement_input)
        
        # Initially hide replacement controls
        self.replacement_label.hide()
        self.replacement_input.hide()
        
        # Connect radio buttons to show/hide replacement controls
        self.replace_pattern_radio.toggled.connect(self.toggle_replacement_controls)
        
        # Preview area
        preview_label = QLabel("Preview (first 10 files):")
        layout.addWidget(preview_label)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(100)
        layout.addWidget(self.preview_text)
        
        # Update preview when inputs change
        self.pattern_input.textChanged.connect(lambda: self.update_rename_preview(files_to_rename))
        self.replacement_input.textChanged.connect(lambda: self.update_rename_preview(files_to_rename))
        self.operation_group.buttonClicked.connect(lambda: self.update_rename_preview(files_to_rename))
        
        # Buttons
        button_layout = QHBoxLayout()
        
        preview_button = QPushButton("Update Preview")
        preview_button.clicked.connect(lambda: self.update_rename_preview(files_to_rename))
        button_layout.addWidget(preview_button)
        
        rename_button = QPushButton("Rename Files")
        rename_button.clicked.connect(lambda: self.execute_bulk_rename(files_to_rename, dialog))
        button_layout.addWidget(rename_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Initial preview
        self.update_rename_preview(files_to_rename)
        
        dialog.exec_()

    def toggle_replacement_controls(self):
        """Show/hide replacement controls based on operation selection"""
        show_replacement = self.replace_pattern_radio.isChecked()
        self.replacement_label.setVisible(show_replacement)
        self.replacement_input.setVisible(show_replacement)

    def update_rename_preview(self, files_to_rename):
        """Update the preview of renamed files"""
        pattern = self.pattern_input.text()
        replacement = self.replacement_input.text()
        
        if not pattern and self.remove_pattern_radio.isChecked():
            self.preview_text.setText("Enter a pattern to remove...")
            return
        
        if not pattern and self.replace_pattern_radio.isChecked():
            self.preview_text.setText("Enter a pattern to replace...")
            return
        
        preview_lines = []
        preview_files = files_to_rename[:10]  # Show first 10 files
        
        for file_path in preview_files:
            old_name = os.path.basename(file_path)
            new_name = self.generate_new_filename(old_name, pattern, replacement)
            
            if new_name != old_name:
                preview_lines.append(f"{old_name} → {new_name}")
            else:
                preview_lines.append(f"{old_name} (no change)")
        
        if len(files_to_rename) > 10:
            preview_lines.append(f"... and {len(files_to_rename) - 10} more files")
        
        self.preview_text.setText("\n".join(preview_lines))

    def generate_new_filename(self, old_name, pattern, replacement=""):
        """Generate new filename based on selected operation"""
        name_without_ext, ext = os.path.splitext(old_name)
        
        if self.add_prefix_radio.isChecked():
            return pattern + old_name
        
        elif self.add_suffix_radio.isChecked():
            return name_without_ext + pattern + ext
        
        elif self.remove_pattern_radio.isChecked():
            new_name_without_ext = name_without_ext.replace(pattern, "")
            return new_name_without_ext + ext
        
        elif self.replace_pattern_radio.isChecked():
            new_name_without_ext = name_without_ext.replace(pattern, replacement)
            return new_name_without_ext + ext
        
        return old_name

    def execute_bulk_rename(self, files_to_rename, dialog):
        """Execute the bulk rename operation"""
        pattern = self.pattern_input.text().strip()
        replacement = self.replacement_input.text().strip()
        
        if not pattern:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter a pattern.")
            return
        
        # Count how many files will actually be renamed
        files_to_change = []
        for file_path in files_to_rename:
            old_name = os.path.basename(file_path)
            new_name = self.generate_new_filename(old_name, pattern, replacement)
            if new_name != old_name and new_name.strip():
                files_to_change.append((file_path, new_name))
        
        if not files_to_change:
            QMessageBox.information(dialog, "No Changes", "No files will be changed with the current pattern.")
            return
        
        # Confirm the operation
        operation_name = ""
        if self.add_prefix_radio.isChecked():
            operation_name = f"add prefix '{pattern}'"
        elif self.add_suffix_radio.isChecked():
            operation_name = f"add suffix '{pattern}'"
        elif self.remove_pattern_radio.isChecked():
            operation_name = f"remove pattern '{pattern}'"
        elif self.replace_pattern_radio.isChecked():
            operation_name = f"replace '{pattern}' with '{replacement}'"
        
        reply = QMessageBox.question(
            dialog, 
            "Confirm Bulk Rename", 
            f"Are you sure you want to {operation_name} for {len(files_to_change)} files?\n\nThis operation cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Perform the rename operation
        errors = []
        success_count = 0
        
        for file_path, new_name in files_to_change:
            try:
                directory = os.path.dirname(file_path)
                new_path = os.path.join(directory, new_name)
                
                # Check if target file already exists
                if os.path.exists(new_path):
                    errors.append(f"{os.path.basename(file_path)}: Target file already exists")
                    continue
                
                os.rename(file_path, new_path)
                success_count += 1
                
            except Exception as e:
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")
        
        # Show results
        if errors:
            error_msg = f"Renamed {success_count} files successfully.\n\nErrors encountered:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            QMessageBox.warning(dialog, "Bulk Rename Complete with Errors", error_msg)
        else:
            QMessageBox.information(dialog, "Bulk Rename Complete", f"Successfully renamed {success_count} files.")
        
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
        file_path = self.model.filePath(index)
        if QFileInfo(file_path).isDir():
            self.update_icon_view(file_path)
        else:
            self.clear_icon_view()

    def update_icon_view(self, folder_path):
        self.current_folder = folder_path  # Update current folder
        self.save_last_dir(folder_path)  # Save the current folder to settings
        
        # Synchronize tree view with icon view
        folder_index = self.model.index(folder_path)
        if folder_index.isValid():
            self.tree_view.setCurrentIndex(folder_index)
            self.tree_view.expand(folder_index)
            # Also expand parent directories to ensure visibility
            parent_index = folder_index.parent()
            while parent_index.isValid():
                self.tree_view.expand(parent_index)
                parent_index = parent_index.parent()
        
        for i in reversed(range(self.icon_grid.count())):
            widget = self.icon_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        try:
            files = os.listdir(folder_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot access folder:\n{e}")
            return
        files = [f for f in files if not f.startswith('.')]
        files.sort(key=lambda x: (not os.path.isdir(os.path.normpath(os.path.join(folder_path, x))), x.lower()))
        row, col = 0, 0
        for file_name in files:
            full_path = os.path.normpath(os.path.join(folder_path, file_name))
            is_dir = os.path.isdir(full_path)
            icon_widget = IconWidget(file_name, full_path, is_dir, self.thumbnail_size)
            icon_widget.update_style_for_theme(self.dark_mode)  # Apply theme
            icon_widget.clicked.connect(self.icon_clicked)
            icon_widget.doubleClicked.connect(self.icon_double_clicked)
            icon_widget.rightClicked.connect(self.icon_right_clicked)
            self.icon_grid.addWidget(icon_widget, row, col)
            col += 1
            if col >= 6:
                col = 0
                row += 1

    def clear_icon_view(self):
        for i in reversed(range(self.icon_grid.count())):
            widget = self.icon_grid.itemAt(i).widget()
            if widget:
                widget.setParent(None)

    def deselect_icons(self):
        self.icon_container.clear_selection()
        self.selected_icon = None
        self.selected_items = []

    def on_selection_changed(self, selected_paths):
        self.selected_items = selected_paths

    def icon_clicked(self, full_path, modifiers):
        # Find the widget that was clicked
        clicked_widget = None
        for i in range(self.icon_grid.count()):
            widget = self.icon_grid.itemAt(i).widget()
            if widget and widget.full_path == full_path:
                clicked_widget = widget
                break
        
        if not clicked_widget:
            return
            
        if modifiers & Qt.ControlModifier:
            # Ctrl+click: toggle selection
            if clicked_widget in self.icon_container.selected_widgets:
                self.icon_container.remove_from_selection(clicked_widget)
            else:
                self.icon_container.add_to_selection(clicked_widget)
        else:
            # Regular click: select only this item
            self.icon_container.clear_selection()
            self.icon_container.add_to_selection(clicked_widget)
            self.selected_icon = clicked_widget

    def icon_double_clicked(self, full_path):
        if QFileInfo(full_path).isDir():
            self.update_icon_view(full_path)
        else:
            try:
                if sys.platform.startswith('win'):
                    os.startfile(full_path)
                elif sys.platform == 'darwin':
                    subprocess.run(['open', full_path])
                else:
                    subprocess.run(['xdg-open', full_path])
            except Exception as e:
                QMessageBox.warning(self, "Error Opening File", str(e))

    def icon_right_clicked(self, full_path, global_pos):
        self.current_right_clicked_path = full_path
        
        # If the right-clicked item is not in current selection, select only it
        if full_path not in self.selected_items:
            clicked_widget = None
            for i in range(self.icon_grid.count()):
                widget = self.icon_grid.itemAt(i).widget()
                if widget and widget.full_path == full_path:
                    clicked_widget = widget
                    break
            if clicked_widget:
                self.icon_container.clear_selection()
                self.icon_container.add_to_selection(clicked_widget)

        menu = QMenu()
        
        # Update menu items based on selection count
        selected_count = len(self.selected_items)
        if selected_count > 1:
            cut_action = menu.addAction(f"Cut ({selected_count} items)")
            copy_action = menu.addAction(f"Copy ({selected_count} items)")
            copy_path_action = menu.addAction(f"Copy as Path ({selected_count} items)")
            delete_action = menu.addAction(f"Delete ({selected_count} items)")
            # Disable rename and terminal for multiple selections
            rename_action = None
            terminal_action = None
        else:
            cut_action = menu.addAction("Cut")
            copy_action = menu.addAction("Copy")
            copy_path_action = menu.addAction("Copy as Path")
            delete_action = menu.addAction("Delete")
            terminal_action = menu.addAction("Open Terminal Here")
            rename_action = menu.addAction("Rename")
            
        paste_action = menu.addAction("Paste")

        action = menu.exec_(global_pos)
        if action == cut_action:
            if selected_count > 1:
                self.clipboard_data = (self.selected_items, "cut")
            else:
                self.clipboard_data = (full_path, "cut")
        elif action == copy_action:
            if selected_count > 1:
                self.clipboard_data = (self.selected_items, "copy")
            else:
                self.clipboard_data = (full_path, "copy")
        elif action == copy_path_action:
            self.copy_path_to_clipboard(full_path if selected_count <= 1 else self.selected_items)
        elif action == paste_action:
            self.paste_to(full_path)
        elif action == delete_action:
            if selected_count > 1:
                self.delete_multiple_files(self.selected_items)
            else:
                self.delete_file(full_path)
        elif terminal_action and action == terminal_action:
            self.open_terminal_here(os.path.dirname(full_path))
        elif rename_action and action == rename_action:
            self.rename_file(full_path)
    def rename_file(self, path):
        base_dir = os.path.dirname(path)
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(self, "Rename", f"Enter new name for '{old_name}':", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        new_path = os.path.normpath(os.path.join(base_dir, new_name))
        if os.path.exists(new_path):
            QMessageBox.warning(self, "Error", "A file/folder with that name already exists.")
            return
        try:
            os.rename(path, new_path)
            self.update_icon_view(base_dir)
        except Exception as e:
            QMessageBox.warning(self, "Error Renaming File", str(e))

    def copy_path_to_clipboard(self, paths):
        """Copy file path(s) to clipboard"""
        try:
            clipboard = QApplication.clipboard()
            if isinstance(paths, list):
                # Multiple paths - join them with newlines
                path_text = '\n'.join(paths)
            else:
                # Single path
                path_text = paths
            
            clipboard.setText(path_text)
            
            # Show a brief confirmation message
            count = len(paths) if isinstance(paths, list) else 1
            if count == 1:
                QMessageBox.information(self, "Copied", f"Path copied to clipboard:\n{path_text}")
            else:
                QMessageBox.information(self, "Copied", f"{count} paths copied to clipboard.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not copy path to clipboard:\n{str(e)}")

    def empty_space_right_clicked(self, global_pos):
        menu = QMenu()
        new_file_action = menu.addAction("Create New File")
        new_folder_action = menu.addAction("Create New Folder")
        menu.addSeparator()  # Add a separator line
        terminal_action = menu.addAction("Open Terminal Here")

        action = menu.exec_(global_pos)
        if action == new_file_action:
            self.create_new_file()
        elif action == new_folder_action:
            self.create_new_folder()
        elif action == terminal_action:
            self.open_terminal_here(self.current_folder)

    def create_new_file(self):
        file_name, ok = QInputDialog.getText(self, "Create New File", "Enter file name:")
        if not ok or not file_name:
            return
        new_file_path = os.path.normpath(os.path.join(self.current_folder, file_name))
        if os.path.exists(new_file_path):
            QMessageBox.warning(self, "Error", "A file with that name already exists.")
            return
        try:
            with open(new_file_path, 'w') as f:
                f.write("")  # Create empty file
            self.update_icon_view(self.current_folder)
        except Exception as e:
            QMessageBox.warning(self, "Error Creating File", str(e))

    def create_new_folder(self):
        folder_name, ok = QInputDialog.getText(self, "Create New Folder", "Enter folder name:")
        if not ok or not folder_name:
            return
        new_folder_path = os.path.normpath(os.path.join(self.current_folder, folder_name))
        if os.path.exists(new_folder_path):
            QMessageBox.warning(self, "Error", "A folder with that name already exists.")
            return
        try:
            os.makedirs(new_folder_path)
            self.update_icon_view(self.current_folder)
        except Exception as e:
            QMessageBox.warning(self, "Error Creating Folder", str(e))

    def paste_to(self, dest_path):
        if not self.clipboard_data:
            QMessageBox.warning(self, "No Clipboard Data", "Nothing to paste.")
            return
        src_path, operation = self.clipboard_data

        if not os.path.isdir(dest_path):
            dest_path = os.path.dirname(dest_path)
        if not os.path.exists(dest_path):
            QMessageBox.warning(self, "Invalid Destination", "Destination path does not exist.")
            return

        # Handle multiple items
        if isinstance(src_path, list):
            self.paste_multiple_items(src_path, dest_path, operation)
        else:
            self.paste_single_item(src_path, dest_path, operation)
        
        self.clipboard_data = None

    def paste_single_item(self, src_path, dest_path, operation):
        new_file_path = os.path.normpath(os.path.join(dest_path, os.path.basename(src_path)))

        if os.path.exists(new_file_path):
            msg = f'"{os.path.basename(new_file_path)}" already exists in this location.\n\nChoose an action:'
            btns = QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            reply = QMessageBox.question(self, "File Exists", msg + "\nYes: Overwrite\nNo: Rename\nCancel: Abort", btns)
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.No:
                new_name, ok = QInputDialog.getText(self, "Rename", "Enter new name:", text=os.path.basename(new_file_path))
                if not ok or not new_name:
                    return
                new_file_path = os.path.normpath(os.path.join(dest_path, new_name))
                if os.path.exists(new_file_path):
                    QMessageBox.warning(self, "Error", "A file/folder with that name already exists.")
                    return

        try:
            if operation == "cut":
                if os.path.exists(new_file_path):
                    if os.path.isdir(new_file_path):
                        shutil.rmtree(new_file_path)
                    else:
                        os.remove(new_file_path)
                shutil.move(src_path, new_file_path)
            elif operation == "copy":
                if os.path.exists(new_file_path):
                    if os.path.isdir(new_file_path):
                        shutil.rmtree(new_file_path)
                    else:
                        os.remove(new_file_path)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, new_file_path)
                else:
                    shutil.copy2(src_path, new_file_path)
            self.update_icon_view(dest_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def paste_multiple_items(self, src_paths, dest_path, operation):
        errors = []
        conflicts = []
        
        # Check for conflicts first
        for src_path in src_paths:
            new_file_path = os.path.normpath(os.path.join(dest_path, os.path.basename(src_path)))
            if os.path.exists(new_file_path):
                conflicts.append(os.path.basename(src_path))
        
        if conflicts:
            msg = f"The following {len(conflicts)} items already exist:\n" + "\n".join(conflicts[:5])
            if len(conflicts) > 5:
                msg += f"\n... and {len(conflicts) - 5} more"
            msg += "\n\nChoose action for all conflicts:"
            btns = QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            reply = QMessageBox.question(self, "Multiple Conflicts", 
                                       msg + "\nYes: Overwrite All\nNo: Skip All\nCancel: Abort", btns)
            if reply == QMessageBox.Cancel:
                return
            overwrite_all = (reply == QMessageBox.Yes)
        else:
            overwrite_all = True
        
        # Process each item
        for src_path in src_paths:
            new_file_path = os.path.normpath(os.path.join(dest_path, os.path.basename(src_path)))
            
            if os.path.exists(new_file_path) and not overwrite_all:
                continue  # Skip this item
            
            try:
                if operation == "cut":
                    if os.path.exists(new_file_path):
                        if os.path.isdir(new_file_path):
                            shutil.rmtree(new_file_path)
                        else:
                            os.remove(new_file_path)
                    shutil.move(src_path, new_file_path)
                elif operation == "copy":
                    if os.path.exists(new_file_path):
                        if os.path.isdir(new_file_path):
                            shutil.rmtree(new_file_path)
                        else:
                            os.remove(new_file_path)
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, new_file_path)
                    else:
                        shutil.copy2(src_path, new_file_path)
            except Exception as e:
                errors.append(f"{os.path.basename(src_path)}: {str(e)}")
        
        if errors:
            QMessageBox.warning(self, "Paste Errors", 
                              f"Some items could not be pasted:\n" + "\n".join(errors))
        
        self.update_icon_view(dest_path)

    def delete_file(self, path):
        reply = QMessageBox.question(self, "Delete", f"Delete {os.path.basename(path)}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.update_icon_view(os.path.dirname(path))
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def delete_multiple_files(self, paths):
        reply = QMessageBox.question(self, "Delete Multiple Items", 
                                   f"Delete {len(paths)} selected items?", 
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            errors = []
            for path in paths:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception as e:
                    errors.append(f"{os.path.basename(path)}: {str(e)}")
            
            if errors:
                QMessageBox.warning(self, "Deletion Errors", 
                                  f"Some files could not be deleted:\n" + "\n".join(errors))
            
            self.update_icon_view(self.current_folder)

    def open_terminal_here(self, path):
        try:
            if sys.platform.startswith('win'):
                # Windows: Use cmd.exe with proper syntax
                subprocess.Popen(f'start cmd /K "cd /d "{path}""', shell=True)
            elif sys.platform == 'darwin':
                # macOS: Use Terminal.app
                subprocess.Popen(['open', '-a', 'Terminal', path])
            else:
                # Linux: Try different terminal emulators in order of preference
                terminals = [
                    ['x-terminal-emulator', '--working-directory', path],
                    ['gnome-terminal', '--working-directory', path],
                    ['konsole', '--workdir', path],
                    ['xfce4-terminal', '--working-directory', path],
                    ['mate-terminal', '--working-directory', path],
                    ['lxterminal', '--working-directory', path],
                    ['xterm', '-e', f'cd "{path}" && bash']
                ]
                
                terminal_opened = False
                for terminal_cmd in terminals:
                    try:
                        subprocess.Popen(terminal_cmd)
                        terminal_opened = True
                        break
                    except FileNotFoundError:
                        continue
                
                if not terminal_opened:
                    QMessageBox.warning(self, "Error", "No terminal emulator found. Please install a terminal emulator.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open terminal:\n{e}")

    def on_double_click(self, index):
        file_path = self.model.filePath(index)
        if not QFileInfo(file_path).isDir():
            try:
                if sys.platform.startswith('win'):
                    os.startfile(file_path)
                elif sys.platform == 'darwin':
                    subprocess.run(['open', file_path])
                else:
                    subprocess.run(['xdg-open', file_path])
            except Exception as e:
                QMessageBox.warning(self, "Error Opening File", str(e))

    def cut_action_triggered(self):
        index = self.tree_view.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "No Selection", "No file or folder selected.")
            return
        self.clipboard_data = (self.model.filePath(index), "cut")

    def copy_action_triggered(self):
        index = self.tree_view.selectionModel().currentIndex()
        if not index.isValid():
            QMessageBox.warning(self, "No Selection", "No file or folder selected.")
            return
        self.clipboard_data = (self.model.filePath(index), "copy")

    def paste_action_triggered(self):
        if not self.clipboard_data:
            QMessageBox.warning(self, "No Clipboard Data", "Nothing to paste.")
            return

        src_path, operation = self.clipboard_data
        dest_index = self.tree_view.selectionModel().currentIndex()
        dest_path = self.model.filePath(dest_index)

        if not QFileInfo(dest_path).isDir():
            dest_path = os.path.dirname(dest_path)
        if not os.path.exists(dest_path):
            QMessageBox.warning(self, "Invalid Destination", "Destination path does not exist.")
            return

        new_file_path = os.path.normpath(os.path.join(dest_path, os.path.basename(src_path)))

        if os.path.exists(new_file_path):
            msg = f'"{os.path.basename(new_file_path)}" already exists in this location.\n\nChoose an action:'
            btns = QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            reply = QMessageBox.question(self, "File Exists", msg + "\nYes: Overwrite\nNo: Rename\nCancel: Abort", btns)
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.No:
                new_name, ok = QInputDialog.getText(self, "Rename", "Enter new name:", text=os.path.basename(new_file_path))
                if not ok or not new_name:
                    return
                new_file_path = os.path.normpath(os.path.join(dest_path, new_name))
                if os.path.exists(new_file_path):
                    QMessageBox.warning(self, "Error", "A file/folder with that name already exists.")
                    return

        try:
            if operation == "cut":
                if os.path.exists(new_file_path):
                    if os.path.isdir(new_file_path):
                        shutil.rmtree(new_file_path)
                    else:
                        os.remove(new_file_path)
                shutil.move(src_path, new_file_path)
                self.update_icon_view(dest_path)
            elif operation == "copy":
                if os.path.exists(new_file_path):
                    if os.path.isdir(new_file_path):
                        shutil.rmtree(new_file_path)
                    else:
                        os.remove(new_file_path)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, new_file_path)
                else:
                    shutil.copy2(src_path, new_file_path)
                self.update_icon_view(dest_path)
            self.clipboard_data = None
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def save_last_dir(self, path):
        try:
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump({
                    "last_dir": path,
                    "thumbnail_size": self.thumbnail_size,
                    "dark_mode": self.dark_mode
                }, f)
        except Exception:
            pass

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
                    return data.get("last_dir", None)
        except Exception:
            pass
        return None

    def closeEvent(self, event):
        """Save the current folder location when the application is closed"""
        self.save_last_dir(self.current_folder)
        event.accept()

def main():
    app = QApplication(sys.argv)
    file_manager = SimpleFileManager()
    file_manager.showMaximized()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
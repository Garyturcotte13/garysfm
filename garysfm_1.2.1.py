import wave
import struct
import logging
import hashlib
import tempfile
from PyQt5.QtCore import QSettings
import builtins as _builtins
from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

# Configure basic logging: only show ERROR and above to quiet debug/info messages
logging.basicConfig(level=logging.ERROR)
# Global toggle and helpers for thumbnail debug/info/error messages.
# Put these at module scope so any function can use them.
THUMBNAIL_VERBOSE = False

# Toggle for noisy event-filter debug messages
EVENT_FILTER_VERBOSE = False

# Toggle for noisy icon-container debug messages (mouse/space clicks in the icon grid)
ICON_CONTAINER_VERBOSE = False

def icon_container_debug(msg, *args):
    try:
        if ICON_CONTAINER_VERBOSE:
            print(f"[ICON-CONTAINER] {msg.format(*args)}")
    except Exception:
        pass

def event_filter_debug(msg, *args):
    try:
        if EVENT_FILTER_VERBOSE:
            print(f"[EVENT-FILTER] {msg.format(*args)}")
    except Exception:
        pass

def thumbnail_debug(msg, *args):
    try:
        if THUMBNAIL_VERBOSE:
            print(f"[THUMBNAIL-DEBUG] {msg.format(*args)}")
    except Exception:
        pass

def thumbnail_info(msg, *args):
    try:
        if THUMBNAIL_VERBOSE:
            print(f"[THUMBNAIL-INFO] {msg.format(*args)}")
    except Exception:
        pass

def thumbnail_error(msg, *args):
    try:
        # Always show errors so failures are visible even when verbose is off
        print(f"[THUMBNAIL-ERROR] {msg.format(*args)}")
    except Exception:
        pass
def is_thumb_file(path):
    """Return True if the path represents a thumbnail cache file (ends with .thumb)."""
    try:
        return isinstance(path, str) and path.lower().endswith('.thumb')
    except Exception:
        return False
def get_waveform_thumbnail(wav_path, width=128, height=48, color=None, thumbnail_cache=None):
    """Generate a waveform QPixmap thumbnail for WAV/MP3 using soundfile, wave, or pydub fallbacks.
    Returns a QPixmap or None on failure. Uses a simple on-disk cache in TEMP.
    """
    logger = logging.getLogger('thumbnail')
    import os
    # Avoid evaluating QColor at import time (can be undefined in some import orders)
    if color is None:
        try:
            from PyQt5.QtGui import QColor
            color = QColor('deepskyblue')
        except Exception:
            color = None
    logger.debug('get_waveform_thumbnail called for: %s', wav_path)
    logger.debug('File exists: %s | Path: %s', os.path.exists(wav_path), wav_path)
    logger.debug('File extension: %s', os.path.splitext(wav_path)[1].lower())
    # Guard: don't attempt to generate thumbnails for files that are themselves thumbnail cache files
    if is_thumb_file(wav_path):
        logger.debug('Skipping waveform thumbnail generation for .thumb file: %s', wav_path)
        return None
    """
    Generate a waveform QPixmap thumbnail for a .wav file using only stdlib and PyQt5.
    Returns a QPixmap of the waveform.
    Uses the application's ThumbnailCache if provided.
    """
    try:
        import hashlib
        # Use temp directory for cache
        temp_dir = os.path.join(os.environ.get('TEMP', '/tmp'), 'garysfm_thumbnails')
        os.makedirs(temp_dir, exist_ok=True)
        file_hash = hashlib.md5(wav_path.encode('utf-8')).hexdigest()
        cache_key = f"{file_hash}_{width}"
        thumb_path = os.path.join(temp_dir, f"{cache_key}.thumb")

        # Return cached pixmap when available
        if os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                return pixmap

        data = None
        # Try soundfile first
        try:
            import soundfile as sf
            logger.debug('Using soundfile to read: %s', wav_path)
            data, samplerate = sf.read(wav_path)
            if hasattr(data, 'ndim') and data.ndim > 1:
                data = data[:, 0]
            data = data.tolist() if hasattr(data, 'tolist') else list(data)
            logger.debug('Finished soundfile block for: %s', wav_path)
        except Exception:
            # soundfile failed — try stdlib wave for WAV or pydub for MP3
            logger.debug('soundfile not available or failed for %s', wav_path)
            if wav_path.lower().endswith('.wav'):
                try:
                    with wave.open(wav_path, 'rb') as wf:
                        n_channels = wf.getnchannels()
                        sampwidth = wf.getsampwidth()
                        n_frames = wf.getnframes()
                        frames = wf.readframes(n_frames)
                        if sampwidth == 1:
                            fmt = f"{n_frames * n_channels}B"
                            data = struct.unpack(fmt, frames)
                            data = [x - 128 for x in data]
                        elif sampwidth == 2:
                            fmt = f"{n_frames * n_channels}h"
                            data = struct.unpack(fmt, frames)
                        else:
                            logger.error('Unsupported sample width: %s for %s', sampwidth, wav_path)
                            return None
                        if n_channels > 1:
                            data = data[::n_channels]
                    logger.debug('Finished WAV block for: %s', wav_path)
                except Exception as e_wave_backend:
                    logger.exception('wave backend failed for %s: %s', wav_path, e_wave_backend)
                    return None
            elif wav_path.lower().endswith('.mp3'):
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_mp3(wav_path)
                    samples = audio.get_array_of_samples()
                    data = samples[::audio.channels] if audio.channels > 1 else samples
                    data = list(data)
                    logger.debug('Finished pydub block for: %s', wav_path)
                except Exception as e_pydub:
                    logger.exception('pydub fallback failed for %s: %s', wav_path, e_pydub)
                    return None
            else:
                logger.error('No available backend succeeded for %s', wav_path)
                return None

        # Ensure we have numerical samples
        if not data:
            logger.debug('No waveform data for %s', wav_path)
            return None

        # Downsample to width
        step = max(1, len(data) // width)
        samples = [max(data[i:i+step], key=abs, default=0) for i in range(0, len(data), step)]
        # Normalize
        peak = max(abs(min(samples)), abs(max(samples)), 1)
        norm = [int((s / peak) * (height // 2 - 2)) for s in samples]
        # Draw waveform
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor('white'))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(color)
        mid = height // 2
        for x, y in enumerate(norm):
            painter.drawLine(x, mid - y, x, mid + y)
        painter.end()
        # Save thumbnail to disk for persistent cache (as PNG)
        try:
            saved = pixmap.save(thumb_path, 'PNG')
            if saved:
                logger.debug('Saved new thumbnail: %s', thumb_path)
            else:
                logger.warning('Failed to save thumbnail: %s', thumb_path)
        except Exception:
            logger.exception('Failed to save thumbnail for %s', thumb_path)
        return pixmap
    except Exception as e:
        logger.exception('Exception for %s: %s', wav_path, e)
        return None
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout
# --- SMB Browser Tab for Samba GUI Access ---
class SmbBrowserTab(QWidget):

    """A tab for browsing an SMB (Samba) network share."""
    def __init__(self, server, share, username, password, domain='', start_path='/', parent=None):
        super().__init__(parent)
        self.smb = SMBNetworkUtils(server, share, username, password, domain)
        self.current_path = start_path
        self.layout = QVBoxLayout(self)
        self.path_label = QLabel()
        self.layout.addWidget(self.path_label)
        # Add download/upload buttons
        btn_layout = QHBoxLayout()
        from PyQt5.QtGui import QIcon
        self.download_btn = QPushButton(QIcon.fromTheme('download'), "⬇ Download")
        self.download_btn.setToolTip("Download the selected file from the share")
        self.download_btn.clicked.connect(self.download_selected_file)
        btn_layout.addWidget(self.download_btn)
        self.upload_btn = QPushButton(QIcon.fromTheme('upload'), "⬆ Upload")
        self.upload_btn.setToolTip("Upload a file to the current directory on the share")
        self.upload_btn.clicked.connect(self.upload_file)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)
        self.list_widget = QListWidget()
        self.list_widget.setToolTip("Double-click a folder to enter it, or a file to select it.")
        self.layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.refresh()

    def refresh(self):
        from PyQt5.QtCore import QThread, pyqtSignal, QObject
        from PyQt5.QtWidgets import QProgressDialog
        self.download_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        progress = QProgressDialog("Loading directory...", None, 0, 0, self)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.show()
        class Worker(QObject):
            finished = pyqtSignal(list, str)
            def __init__(self, smb, path):
                super().__init__()
                self.smb = smb
                self.path = path
            def run(self):
                try:
                    entries = self.smb.listdir(self.path)
                    self.finished.emit(entries, None)
                except Exception as e:
                    self.finished.emit([], str(e))
        def on_finished(entries, error):
            from PyQt5.QtWidgets import QListWidgetItem
            from PyQt5.QtGui import QIcon
            import os
            progress.close()
            self.list_widget.clear()
            if error:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Directory Error", error)
                self.list_widget.addItem(f"[ERROR] {error}")
            else:
                # Supported audio extensions for waveform thumbnails
                audio_exts = ['.wav', '.flac', '.ogg', '.aiff', '.aif', '.aifc', '.au', '.snd', '.sf', '.caf', '.mp3', '.m4a']
                for entry in entries:
                    item = QListWidgetItem(entry)
                    # Set waveform icon for supported audio files and cache them
                    if any(entry.lower().endswith(ext) for ext in audio_exts):
                        try:
                            audio_path = os.path.join(self.current_path, entry)
                            if not hasattr(self, 'thumbnail_cache') or self.thumbnail_cache is None:
                                self.thumbnail_cache = dict()
                            def cache_get(key):
                                return self.thumbnail_cache.get(key)
                            def cache_put(key, value):
                                self.thumbnail_cache[key] = value
                            class SimpleCache:
                                def get(self, key):
                                    return cache_get(key)
                                def put(self, key, value):
                                    cache_put(key, value)
                            thumbnail_debug('Calling get_waveform_thumbnail for: {}', audio_path)
                            supported_audio_exts = ['.wav', '.flac', '.ogg', '.aiff', '.aif', '.aifc', '.au', '.snd', '.sf', '.caf', '.mp3', '.oga', '.aac', '.m4a', '.wma', '.opus', '.alac']
                            ext = os.path.splitext(audio_path)[1].lower()
                            if ext in supported_audio_exts:
                                pixmap = get_waveform_thumbnail(audio_path, width=48, height=48, thumbnail_cache=SimpleCache())
                            else:
                                thumbnail_debug('Skipping unsupported audio extension for thumbnail: {}', audio_path)
                            if pixmap is not None:
                                item.setIcon(QIcon(pixmap))
                            else:
                                # Show a warning icon or text if thumbnail failed
                                item.setToolTip("Could not generate waveform thumbnail. See log for details.")
                        except Exception as e:
                            item.setToolTip(f"Thumbnail error: {e}")
                    self.list_widget.addItem(item)
            self.path_label.setText(f"smb://{self.smb.server}/{self.smb.share}{self.current_path}")
            self.download_btn.setEnabled(True)
            self.upload_btn.setEnabled(True)
            thread.quit()
            thread.wait()
        thread = QThread()
        worker = Worker(self.smb, self.current_path)
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)
        thread.start()

    def on_item_double_clicked(self, item):
        name = item.text()
        if name.startswith("[ERROR]"):
            return
        # Try to enter directory
        new_path = self.current_path.rstrip("/") + "/" + name
        try:
            entries = self.smb.listdir(new_path)
            self.current_path = new_path
            self.refresh()
        except Exception:
            pass  # Not a directory or error

    def download_selected_file(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal, QObject
        items = self.list_widget.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Select a file to download.")
            return
        name = items[0].text()
        remote_path = self.current_path.rstrip("/") + "/" + name
        save_path, _ = QFileDialog.getSaveFileName(self, "Save File As", name)
        if not save_path:
            return
        import os
        if os.path.exists(save_path):
            reply = QMessageBox.question(self, "Overwrite File?", f"{save_path} exists. Overwrite?", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.download_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        progress = QProgressDialog("Downloading file...", None, 0, 0, self)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.show()
        class Worker(QObject):
            finished = pyqtSignal(bytes, str)
            def __init__(self, smb, remote_path):
                super().__init__()
                self.smb = smb
                self.remote_path = remote_path
            def run(self):
                try:
                    data = self.smb.read_file(self.remote_path)
                    self.finished.emit(data, None)
                except Exception as e:
                    self.finished.emit(None, str(e))
        def on_finished(data, error):
            progress.close()
            self.download_btn.setEnabled(True)
            self.upload_btn.setEnabled(True)
            if error:
                QMessageBox.critical(self, "Download Failed", str(error))
            else:
                try:
                    with open(save_path, "wb") as f:
                        f.write(data)
                    QMessageBox.information(self, "Download Complete", f"Downloaded to {save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "Download Failed", str(e))
            thread.quit()
            thread.wait()
        thread = QThread()
        worker = Worker(self.smb, remote_path)
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)
        thread.start()

    def upload_file(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal, QObject
        import os
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload")
        if not file_path:
            return
        name = os.path.basename(file_path)
        remote_path = self.current_path.rstrip("/") + "/" + name
        # Confirm overwrite if file exists on SMB share (best effort: check listdir)
        try:
            existing = self.smb.listdir(self.current_path)
            if name in existing:
                reply = QMessageBox.question(self, "Overwrite File?", f"{name} exists on the share. Overwrite?", QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
        except Exception:
            pass
        self.download_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        progress = QProgressDialog("Uploading file...", None, 0, 0, self)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.show()
        class Worker(QObject):
            finished = pyqtSignal(str)
            def __init__(self, smb, remote_path, file_path):
                super().__init__()
                self.smb = smb
                self.remote_path = remote_path
                self.file_path = file_path
            def run(self):
                try:
                    with open(self.file_path, "rb") as f:
                        data = f.read()
                    self.smb.write_file(self.remote_path, data)
                    self.finished.emit(None)
                except Exception as e:
                    self.finished.emit(str(e))
        def on_finished(error):
            progress.close()
            self.download_btn.setEnabled(True)
            self.upload_btn.setEnabled(True)
            if error:
                QMessageBox.critical(self, "Upload Failed", str(error))
            else:
                QMessageBox.information(self, "Upload Complete", f"Uploaded {name}")
                self.refresh()
            thread.quit()
            thread.wait()
        thread = QThread()
        worker = Worker(self.smb, remote_path, file_path)
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)
        thread.start()

import os
import uuid
import sys
if sys.platform.startswith('linux'):
    try:
        from smb.SMBConnection import SMBConnection
        HAVE_PYSMB = True
    except ImportError:
        HAVE_PYSMB = False
        import subprocess
else:
    import smbprotocol
    from smbprotocol.connection import Connection
    from smbprotocol.session import Session
    from smbprotocol.tree import TreeConnect
    from smbprotocol.open import Open, CreateDisposition, FileAttributes, CreateOptions, FilePipePrinterAccessMask
    from smbprotocol.file_info import FileAttributes as SMBFileAttributes

class SMBNetworkUtils:
    """
    Utility class for SMB (Samba) network folder operations using smbprotocol.
    Supports listing, reading, writing, and copying files/folders on SMB shares.
    """
    def __init__(self, server, share, username, password, domain='', port=445):
        self.server = server
        self.share = share
        self.username = username
        self.password = password
        self.domain = domain
        self.port = port
        self.conn = None
        self.session = None
        self.tree = None
        self.smbc = None
        if sys.platform.startswith('linux'):
            if HAVE_PYSMB:
                self._connect_linux_pysmb()
            else:
                self._connect_linux_smbclient()
        else:
            self._connect_win()

    def _connect_linux_pysmb(self):
        # Use pysmb's SMBConnection
        self.smbc = SMBConnection(self.username, self.password, 'garysfm', self.server, domain=self.domain, use_ntlm_v2=True)
        assert self.smbc.connect(self.server, self.port), "Failed to connect to SMB server via pysmb"

    def _connect_linux_smbclient(self):
        # No persistent connection needed for smbclient subprocess
        self.smbc = None

    def _connect_win(self):
        smbprotocol.ClientConfig(username=self.username, password=self.password, domain=self.domain)
        self.conn = Connection(uuid.uuid4(), self.server, port=self.port)
        self.conn.connect()
        self.session = Session(self.conn, self.username, self.password, self.domain)
        self.session.connect()
        self.tree = TreeConnect(self.session, f"//{self.server}/{self.share}")
        self.tree.connect()

    def listdir(self, path):
        """List files and folders in a directory on the SMB share."""
        if sys.platform.startswith('linux'):
            path = path.lstrip('/')
            if HAVE_PYSMB:
                files = self.smbc.listPath(self.share, path)
                return [f.filename for f in files if f.filename not in ('.', '..')]
            else:
                # Use smbclient subprocess
                # Use a temporary credentials file to avoid exposing the password
                # on the process command line. smbclient supports -A <credsfile>.
                import tempfile, stat
                creds_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as cf:
                        creds_path = cf.name
                        cf.write(f"username = {self.username}\npassword = {self.password}\n")
                    # Restrict permissions to owner only where possible
                    try:
                        os.chmod(creds_path, stat.S_IRUSR | stat.S_IWUSR)
                    except Exception:
                        pass
                    cmd = [
                        'smbclient',
                        f'//{self.server}/{self.share}',
                        '-A', creds_path,
                        '-c', f'ls {path or "."}'
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise RuntimeError(f'smbclient failed: {result.stderr}')
                    lines = result.stdout.splitlines()
                    # Parse output: skip lines that are not file/dir entries
                    entries = []
                    for line in lines:
                        parts = line.split()
                        if parts and not line.startswith('Domain=') and not line.startswith('smb:'):
                            entries.append(parts[0])
                    return [e for e in entries if e not in ('.', '..')]
                finally:
                    try:
                        if creds_path and os.path.exists(creds_path):
                            os.remove(creds_path)
                    except Exception:
                        pass
        else:
            dir_handle = Open(tree=self.tree, file_name=path, desired_access=FilePipePrinterAccessMask.FILE_LIST_DIRECTORY,
                             share_access=1, create_disposition=CreateDisposition.FILE_OPEN, create_options=CreateOptions.FILE_DIRECTORY_FILE)
            dir_handle.create()
            entries = dir_handle.query_directory()
            dir_handle.close()
            return [entry['file_name'] for entry in entries if entry['file_name'] not in ('.', '..')]

    def read_file(self, path):
        """Read the contents of a file from the SMB share."""
        if sys.platform.startswith('linux'):
            path = path.lstrip('/')
            if HAVE_PYSMB:
                from io import BytesIO
                file_obj = BytesIO()
                self.smbc.retrieveFile(self.share, path, file_obj)
                return file_obj.getvalue()
            else:
                # Use smbclient subprocess to get file
                import tempfile
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp_path = tmp.name
                    # Use temporary creds file to avoid showing password in process list
                    import tempfile, stat
                    creds_path = None
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as cf:
                            creds_path = cf.name
                            cf.write(f"username = {self.username}\npassword = {self.password}\n")
                        try:
                            os.chmod(creds_path, stat.S_IRUSR | stat.S_IWUSR)
                        except Exception:
                            pass
                        cmd = [
                            'smbclient',
                            f'//{self.server}/{self.share}',
                            '-A', creds_path,
                            '-c', f'get {path} {tmp_path}'
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                    finally:
                        try:
                            if 'creds_path' in locals() and creds_path and os.path.exists(creds_path):
                                os.remove(creds_path)
                        except Exception:
                            pass
                    if result.returncode != 0:
                        raise RuntimeError(f'smbclient get failed: {result.stderr}')
                    with open(tmp_path, 'rb') as f:
                        data = f.read()
                    return data
                finally:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            file_handle = Open(tree=self.tree, file_name=path, desired_access=FilePipePrinterAccessMask.FILE_READ_DATA,
                              share_access=1, create_disposition=CreateDisposition.FILE_OPEN)
            file_handle.create()
            data = file_handle.read(0, file_handle.query_info()['end_of_file'])
            file_handle.close()
            return data

    def write_file(self, path, data):
        """Write data to a file on the SMB share (overwrites if exists)."""
        if sys.platform.startswith('linux'):
            path = path.lstrip('/')
            if HAVE_PYSMB:
                from io import BytesIO
                file_obj = BytesIO(data)
                self.smbc.storeFile(self.share, path, file_obj)
            else:
                # Use smbclient subprocess to put file
                import tempfile
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp:
                        tmp.write(data)
                        tmp_path = tmp.name
                    # Use temporary creds file to avoid exposing password
                    import tempfile, stat
                    creds_path = None
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as cf:
                            creds_path = cf.name
                            cf.write(f"username = {self.username}\npassword = {self.password}\n")
                        try:
                            os.chmod(creds_path, stat.S_IRUSR | stat.S_IWUSR)
                        except Exception:
                            pass
                        cmd = [
                            'smbclient',
                            f'//{self.server}/{self.share}',
                            '-A', creds_path,
                            '-c', f'put {tmp_path} {path}'
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                    finally:
                        try:
                            if 'creds_path' in locals() and creds_path and os.path.exists(creds_path):
                                os.remove(creds_path)
                        except Exception:
                            pass
                    if result.returncode != 0:
                        raise RuntimeError(f'smbclient put failed: {result.stderr}')
                finally:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            file_handle = Open(tree=self.tree, file_name=path, desired_access=FilePipePrinterAccessMask.FILE_WRITE_DATA,
                              share_access=1, create_disposition=CreateDisposition.FILE_OVERWRITE_IF)
            file_handle.create()
            file_handle.write(0, data)
            file_handle.close()

    def copy_file_to_share(self, local_path, remote_path):
        """Copy a local file to the SMB share."""
        with open(local_path, 'rb') as f:
            data = f.read()
        self.write_file(remote_path, data)

    def copy_file_from_share(self, remote_path, local_path):
        """Copy a file from the SMB share to local disk."""
        data = self.read_file(remote_path)
        with open(local_path, 'wb') as f:
            f.write(data)

    def close(self):
        if sys.platform.startswith('linux'):
            if HAVE_PYSMB and self.smbc:
                self.smbc.close()
        else:
            if self.tree:
                self.tree.disconnect()
            if self.session:
                self.session.disconnect()
            if self.conn:
                self.conn.disconnect()

# Example usage (replace with your actual credentials and share):
# smb = SMBNetworkUtils(server='192.168.1.100', share='shared', username='user', password='pass')
# print(smb.listdir("/"))
# smb.copy_file_to_share('local.txt', '/remote.txt')
# smb.copy_file_from_share('/remote.txt', 'downloaded.txt')
# smb.close()
from PyQt5.QtWidgets import QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QFileDialog, QMessageBox, QPushButton
import re
import ftplib
import paramiko
import shutil
import sys

# --- Robust FFmpeg presence check for macOS ---
def find_ffmpeg():
    """
    Try to find ffmpeg in PATH, common Homebrew locations, or via FFMPEG_PATH env var.
    Returns the path to ffmpeg or None if not found.
    """
    ffmpeg_env = os.environ.get('FFMPEG_PATH')
    if ffmpeg_env and os.path.isfile(ffmpeg_env) and os.access(ffmpeg_env, os.X_OK):
        return ffmpeg_env
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path
    # Check common Homebrew locations
    brew_paths = [
        '/opt/homebrew/bin/ffmpeg',        # Apple Silicon
        '/usr/local/bin/ffmpeg',           # Intel
        '/Applications/ffmpeg/ffmpeg',     # gary's
    ]
    for path in brew_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None

# Global lazy thumbnail cache accessor
_GLOBAL_THUMBNAIL_CACHE = None
def get_global_thumbnail_cache():
    global _GLOBAL_THUMBNAIL_CACHE
    if _GLOBAL_THUMBNAIL_CACHE is None:
        try:
            _GLOBAL_THUMBNAIL_CACHE = ThumbnailCache()
        except Exception:
            _GLOBAL_THUMBNAIL_CACHE = None
    return _GLOBAL_THUMBNAIL_CACHE

if sys.platform == 'darwin':
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        print("[ERROR] FFmpeg not found in PATH or common locations. Please install FFmpeg (e.g., via Homebrew: 'brew install ffmpeg') and try again.")
        print("[ERROR] You can also set the FFMPEG_PATH environment variable to the full path of ffmpeg.")
        sys.exit(1)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QKeySequence, QFont, QTextDocument, QSyntaxHighlighter, QTextCharFormat, QStandardItemModel, QStandardItem, QColor, QDesktopServices, QMovie, QTextOption, QBrush, QTextCursor

# --- EXE Icon Extraction for PyQt ---
def get_exe_icon_qicon(exe_path, size=32):
    """
    Extracts the icon from an EXE file and returns a QIcon.
    Requires pywin32 and PyQt5.
    """
    import sys
    from PyQt5.QtGui import QPixmap, QIcon
    if sys.platform.startswith('win'):
        try:
            import win32api
            import win32con
            import win32ui
            import win32gui
            from PyQt5.QtGui import QImage
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if not large and not small:
                return QIcon()
            hicon = large[0] if large else small[0]
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, size, size)
            hdc_mem = hdc.CreateCompatibleDC()
            hdc_mem.SelectObject(hbmp)
            win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            image = QImage(bmpstr, bmpinfo['bmWidth'], bmpinfo['bmHeight'], QImage.Format_ARGB32)
            pixmap = QPixmap.fromImage(image)
            win32gui.DestroyIcon(hicon)
            return QIcon(pixmap)
        except Exception as e:
            print(f"[EXE-ICON] Failed to extract icon from {exe_path}: {e}")
            return QIcon()
    else:
        # On macOS/Linux, show a generic EXE icon or fallback to a PNG if available
        import os
        fallback_icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        if os.path.isfile(fallback_icon_path):
            return QIcon(QPixmap(fallback_icon_path).scaled(size, size))
    # Draw a simple generic icon (no blue squares/rect for drives)
    pixmap = QPixmap(size, size)
    pixmap.fill()
    from PyQt5.QtGui import QPainter, QColor
    painter = QPainter(pixmap)
    painter.setPen(QColor('black'))
    # Only draw the rectangle and text for non-drive files
    # (Drives should not show the blue squares/rect)
    # Optionally, you can check for 'exe_path' being a drive letter here and skip drawing
    painter.drawText(8, size//2, 'EXE')
    painter.end()
    return QIcon(pixmap)
def precache_text_pdf_thumbnails_in_directory(directory, thumbnail_cache, size=128, max_workers=4, on_complete=None, parent=None, show_progress=False):
    """
    Pre-cache thumbnails for text and PDF files in a directory in the background.
    Args:
        directory (str): Path to the directory to scan for files.
        thumbnail_cache (ThumbnailCache): The thumbnail cache instance to use.
        size (int): Thumbnail size in pixels (default 128).
        max_workers (int): Number of threads for parallel extraction.
    """
    import glob
    import concurrent.futures
    text_exts = ('.txt', '.md', '.log', '.ini', '.csv', '.json', '.xml', '.py', '.c', '.cpp', '.h', '.java', '.js', '.html', '.css')
    pdf_exts = ('.pdf',)
    docx_exts = ('.docx', '.doc')
    audio_exts = ('.wav', '.mp3', '.flac', '.ogg', '.oga', '.aac', '.m4a', '.wma', '.opus', '.aiff', '.alac')
    image_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp', '.ico')
    thumbnail_info("Called for directory={} size={}", directory, size)
    files = [f for f in glob.glob(os.path.join(directory, '*')) if os.path.splitext(f)[1].lower() in text_exts + pdf_exts + docx_exts + audio_exts + image_exts]
    thumbnail_info("Found {} files to process", len(files))
    # Optional progress dialog and cooperative cancellation
    stop_event = None
    progress_dialog = None
    # Precompute which files actually need caching so we only show the dialog when there's work to do
    files_to_cache = []
    try:
        for f in files:
            try:
                if not thumbnail_cache.is_cached(f, size):
                    files_to_cache.append(f)
            except Exception:
                files_to_cache.append(f)
    except Exception:
        # Fallback: assume all files may need caching
        files_to_cache = list(files)
    thumbnail_info("Files needing caching: {}", len(files_to_cache))
    # Consult user preference for caching dialog: 'always_show', 'ask', 'always_hide'
    try:
        settings = QSettings("garysfm", "garysfm")
        cache_dialog_pref = settings.value('cache_dialog_pref', 'ask')
    except Exception:
        cache_dialog_pref = 'ask'

    should_show_dialog = False
    if cache_dialog_pref == 'always_show':
        should_show_dialog = True
    elif cache_dialog_pref == 'ask':
        should_show_dialog = bool(show_progress) and bool(files_to_cache)
    elif cache_dialog_pref == 'always_hide':
        should_show_dialog = False
    else:
        should_show_dialog = bool(show_progress) and bool(files_to_cache)

    if should_show_dialog and files_to_cache:
        try:
            from PyQt5.QtWidgets import QProgressDialog, QApplication
            import threading
            stop_event = threading.Event()
            parent_win = parent
            if parent_win is None:
                parent_win = QApplication.instance().activeWindow() if QApplication.instance() else None
            progress_dialog = QProgressDialog('Caching thumbnails...', 'Cancel', 0, len(files_to_cache), parent_win)
            progress_dialog.setWindowTitle('Thumbnail caching')
            progress_dialog.setWindowModality(0)  # Non-modal by default; parent controls modality
            progress_dialog.setMinimumDuration(200)
            # When cancelled, set the stop event
            try:
                progress_dialog.canceled.connect(lambda: stop_event.set())
            except Exception:
                pass
            progress_dialog.show()
        except Exception:
            progress_dialog = None
            stop_event = None
    def cache_one_file(file_path):
        ext = os.path.splitext(file_path)[1].lower()
        # Skip thumbnail cache files themselves
        try:
            if is_thumb_file(file_path):
                thumbnail_debug("Skipping .thumb cache file: {}", file_path)
                return
        except Exception:
            pass
        # Check cooperative cancellation
        try:
            if stop_event is not None and stop_event.is_set():
                return
        except Exception:
            pass
        thumbnail_debug("Processing {} (ext={})", file_path, ext)
        if thumbnail_cache.get(file_path, size) is not None:
            thumbnail_debug("Already cached: {}", file_path)
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            if ext in text_exts:
                thumbnail_debug("Generating text thumbnail for {}", file_path)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = []
                    for _ in range(8):
                        try:
                            lines.append(next(f).rstrip())
                        except StopIteration:
                            break
                text = '\n'.join(lines)
                img = Image.new('RGBA', (size, size), (255, 255, 255, 255))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype('arial.ttf', 12)
                except Exception:
                    font = ImageFont.load_default()
                try:
                    text_bbox = draw.multiline_textbbox((0, 0), text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                except AttributeError:
                    text_width, text_height = draw.textsize(text, font=font)
                x = (size - text_width) // 2 if text_width < size else 4
                y = (size - text_height) // 2 if text_height < size else 4
                draw.multiline_text((x, y), text, fill=(0, 0, 0), font=font)
                img = img.resize((size, size), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                png_bytes = buf.getvalue()
                thumbnail_debug("About to cache text thumbnail for {}, {} bytes", file_path, len(png_bytes))
                thumbnail_cache.put(file_path, size, png_bytes)
                thumbnail_debug("Cached text thumbnail for {}", file_path)
            elif ext in pdf_exts:
                thumbnail_debug("Generating PDF thumbnail for {}", file_path)
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                if doc.page_count > 0:
                    page = doc.load_page(0)
                    zoom = max(size / 72, 2)
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                    img = img.resize((size, size), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    png_bytes = buf.getvalue()
                    thumbnail_debug("About to cache PDF thumbnail for {}, {} bytes", file_path, len(png_bytes))
                    thumbnail_cache.put(file_path, size, png_bytes)
                    thumbnail_debug("Cached PDF thumbnail for {}", file_path)
            elif ext in ['.wav', '.flac', '.ogg', '.aiff', '.aif', '.aifc', '.au', '.snd', '.sf', '.caf', '.mp3', '.oga', '.aac', '.m4a', '.wma', '.opus', '.alac']:
                thumbnail_debug("Generating waveform thumbnail for {}", file_path)
                try:
                    thumbnail_debug("Calling get_waveform_thumbnail for: {}", file_path)
                    # Use the thumbnail_cache passed into this function (module-level), not a `self` reference
                    pixmap = get_waveform_thumbnail(file_path, width=size, height=size, thumbnail_cache=thumbnail_cache)
                    # Save QPixmap to PNG bytes
                    from PyQt5.QtCore import QBuffer, QByteArray
                    buffer = QBuffer()
                    buffer.open(QBuffer.ReadWrite)
                    pixmap.save(buffer, 'PNG')
                    png_bytes = buffer.data().data()
                    thumbnail_debug("About to cache waveform thumbnail for {}, {} bytes", file_path, len(png_bytes))
                    thumbnail_cache.put(file_path, size, png_bytes)
                    thumbnail_debug("Cached waveform thumbnail for {}", file_path)
                except Exception as e:
                    thumbnail_error("Failed to generate waveform for {}: {}", file_path, e)
            elif ext in image_exts:
                thumbnail_debug("Generating image thumbnail for {}", file_path)
                img = Image.open(file_path)
                img = img.convert('RGBA')
                img = img.resize((size, size), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                png_bytes = buf.getvalue()
                thumbnail_debug("About to cache image thumbnail for {}, {} bytes", file_path, len(png_bytes))
                thumbnail_cache.put(file_path, size, png_bytes)
                thumbnail_debug("Cached image thumbnail for {}", file_path)
        except Exception as e:
            thumbnail_error("Failed for {}: {}", file_path, e)
    thumbnail_info("Starting cache thread pool for {} files (will process {})", len(files), len(files_to_cache))
    import concurrent.futures
    from concurrent.futures import as_completed
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    futures = [executor.submit(cache_one_file, file_path) for file_path in files_to_cache]
    completed = 0
    try:
        for future in as_completed(futures):
            # If user requested cancellation, break early
            try:
                if stop_event is not None and stop_event.is_set():
                    break
            except Exception:
                pass
            try:
                future.result()
            except Exception:
                # ignore per-file exceptions; they are logged inside cache_one_file
                pass
            completed += 1
            if progress_dialog is not None:
                try:
                    progress_dialog.setValue(completed)
                    # process UI events so dialog updates promptly
                    from PyQt5.QtWidgets import QApplication
                    QApplication.processEvents()
                except Exception:
                    pass
    finally:
        try:
            executor.shutdown(wait=False)
        except Exception:
            pass
        if progress_dialog is not None:
            try:
                progress_dialog.close()
            except Exception:
                pass
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass
def clear_text_pdf_docx_thumbnails(directory, thumbnail_cache, size=128):
    """Delete cached thumbnails for text/pdf/docx files at the given size in the directory."""
    import glob
    text_exts = ('.txt', '.md', '.log', '.ini', '.csv', '.json', '.xml', '.py', '.c', '.cpp', '.h', '.java', '.js', '.html', '.css')
    pdf_exts = ('.pdf',)
    docx_exts = ('.docx', '.doc')
    image_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp', '.ico')
    files = [f for f in glob.glob(os.path.join(directory, '*')) if os.path.splitext(f)[1].lower() in text_exts + pdf_exts + docx_exts + image_exts]
    for file_path in files:
        cache_key = thumbnail_cache.get_cache_key(file_path, size)
        cache_file = os.path.join(thumbnail_cache.cache_dir, f"{cache_key}.thumb")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                thumbnail_info("Removed {}", cache_file)
            except Exception as e:
                thumbnail_error("Failed to remove {}: {}", cache_file, e)
        if thumbnail_cache.get(file_path, size) is not None:
            return  # Already cached
        ext = os.path.splitext(file_path)[1].lower()
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io
            if ext in text_exts:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = []
                        for _ in range(8):
                            try:
                                lines.append(next(f).rstrip())
                            except StopIteration:
                                break
                    text = '\n'.join(lines)
                    img = Image.new('RGBA', (size, size), (255, 255, 255, 255))
                    draw = ImageDraw.Draw(img)
                    try:
                        font = ImageFont.truetype('arial.ttf', 12)
                    except Exception:
                        font = ImageFont.load_default()
                    try:
                        text_bbox = draw.multiline_textbbox((0, 0), text, font=font)
                        text_width = text_bbox[2] - text_bbox[0]
                        text_height = text_bbox[3] - text_bbox[1]
                    except AttributeError:
                        text_width, text_height = draw.textsize(text, font=font)
                    x = (size - text_width) // 2 if text_width < size else 4
                    y = (size - text_height) // 2 if text_height < size else 4
                    draw.multiline_text((x, y), text, fill=(0, 0, 0), font=font)
                    img = img.resize((size, size), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    png_bytes = buf.getvalue()
                    thumbnail_cache.put(file_path, size, png_bytes)
                except Exception as e:
                    thumbnail_error("Text thumbnail failed for {}: {}", file_path, e)
            elif ext in pdf_exts:
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(file_path)
                    if doc.page_count > 0:
                        page = doc.load_page(0)
                        zoom = max(size / 72, 2)
                        mat = fitz.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=mat)
                        img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                        img = img.resize((size, size), Image.LANCZOS)
                        buf = io.BytesIO()
                        img.save(buf, format='PNG')
                        png_bytes = buf.getvalue()
                        thumbnail_cache.put(file_path, size, png_bytes)
                except Exception as e:
                    thumbnail_error("PDF thumbnail failed for {}: {}", file_path, e)
            elif ext in docx_exts:
                try:
                    from PIL import ImageFont
                    img = Image.new('RGBA', (size, size), (255, 255, 255, 255))
                    draw = ImageDraw.Draw(img)
                    # Draw a simple DOCX icon: blue rectangle + file extension
                    rect_color = (40, 100, 200)
                    draw.rectangle([8, 8, size-8, size-8], fill=rect_color, outline=(0,0,0))
                    try:
                        font = ImageFont.truetype('arial.ttf', 28)
                    except Exception:
                        font = ImageFont.load_default()
                    text = 'DOCX' if ext == '.docx' else 'DOC'
                    try:
                        bbox = draw.textbbox((0, 0), text, font=font)
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]
                    except AttributeError:
                        w, h = draw.textsize(text, font=font)
                    draw.text(((size-w)//2, (size-h)//2), text, fill=(255,255,255), font=font)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    png_bytes = buf.getvalue()
                    thumbnail_cache.put(file_path, size, png_bytes)
                except Exception as e:
                    thumbnail_error("DOCX thumbnail failed for {}: {}", file_path, e)
            elif ext in audio_exts:
                # Use a generic audio icon (no waveform, no matplotlib)
                try:
                    from PIL import Image, ImageDraw, ImageFont
                    img = Image.new('RGB', (size, size), color='white')
                    draw = ImageDraw.Draw(img)
                    font = ImageFont.load_default()
                    draw.rectangle([16, 16, size-16, size-16], outline='green', width=4)
                    draw.text((size//4, size//2-10), "AUDIO", fill='green', font=font)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    png_bytes = buf.getvalue()
                    thumbnail_cache.put(file_path, size, png_bytes)
                except Exception as e:
                    thumbnail_error("Audio thumbnail failed for {}: {}", file_path, e)
        except Exception:
            pass  # Ignore errors for individual files
    # Shutdown helper runs in background to wait briefly and then shutdown the executor created above.

import os
import shutil
import errno
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel

# Utility: Generate a unique name with (copy) if file/folder exists
def get_nonconflicting_name(path):
    """
    If path exists, insert ' (copy)' before the extension (for files) or at the end (for folders).
    Returns a new path that does not exist.
    """
    if not os.path.exists(path):
        return path
    dir_name, base = os.path.split(path)
    # Check if path is a file or folder by checking if it has an extension and if it's a file on disk
    is_file = os.path.splitext(base)[1] != '' and (os.path.isfile(path) or not os.path.exists(path))
    if is_file:
        name, ext = os.path.splitext(base)
        new_base = f"{name} (copy){ext}"
        new_path = os.path.join(dir_name, new_base)
        count = 2
        while os.path.exists(new_path):
            new_base = f"{name} (copy {count}){ext}"
            new_path = os.path.join(dir_name, new_base)
            count += 1
    else:
        # Always append ' (copy)' to the very end of the folder name, regardless of dots
        new_base = f"{base} (copy)"
        new_path = os.path.join(dir_name, new_base)
        count = 2
        while os.path.exists(new_path):
            new_base = f"{base} (copy {count})"
            new_path = os.path.join(dir_name, new_base)
            count += 1
    return new_path


# Utility: fast move that prefers os.replace (atomic rename) and falls back to shutil.move
def fast_move(src, dest):
    """Move src to dest. Try os.replace first for same-filesystem atomic move.
    Returns the final destination path used.
    """
    import shutil, os, errno
    # Ensure destination directory exists
    dest_dir = os.path.dirname(dest)
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    # Resolve name conflicts before attempting move
    final_dest = get_nonconflicting_name(dest)

    try:
        # If src is a directory, use shutil.move (os.replace does not support directories)
        if os.path.isdir(src):
            shutil.move(src, final_dest)
            print(f"[MOVE-DEBUG] shutil.move (dir): {src} -> {final_dest}")
            return final_dest
        else:
            os.replace(src, final_dest)
            print(f"[MOVE-DEBUG] fast os.replace: {src} -> {final_dest}")
            return final_dest
    except OSError as e:
        # EXDEV: can't move across filesystems; fall back to shutil.move which will copy+remove
        if getattr(e, 'errno', None) == errno.EXDEV:
            try:
                shutil.move(src, final_dest)
                print(f"[MOVE-DEBUG] fallback shutil.move (EXDEV): {src} -> {final_dest}")
                return final_dest
            except Exception as e2:
                print(f"[MOVE-ERROR] move failed: {e} / fallback failed: {e2}")
                raise
        else:
            print(f"[MOVE-ERROR] move failed: {e}")
            raise

# Top-level OpenWithDialog class
class OpenWithDialog(QDialog):
    def __init__(self, parent=None):
        import sys
        super().__init__(parent)
        self.setWindowTitle("Open with...")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        self.label = QLabel("Select an application to open the file with:")
        layout.addWidget(self.label)
        self.app_list = QListWidget()
        # Platform-specific common apps
        if sys.platform.startswith('win'):
            self.common_apps = [
                ("Notepad", r"C:\\Windows\\System32\\notepad.exe"),
                ("WordPad", r"C:\\Program Files\\Windows NT\\Accessories\\wordpad.exe"),
                ("Paint", r"C:\\Windows\\System32\\mspaint.exe"),
                ("Photos", r"C:\\Program Files\\Windows Photo Viewer\\PhotoViewer.dll"),
                ("Choose another application...", None)
            ]
        elif sys.platform == 'darwin':
            self.common_apps = [
                ("TextEdit", "/Applications/TextEdit.app"),
                ("Preview", "/Applications/Preview.app"),
                ("Safari", "/Applications/Safari.app"),
                ("Choose another application...", None)
            ]
        else:
            self.common_apps = [
                ("gedit", "/usr/bin/gedit"),
                ("kate", "/usr/bin/kate"),
                ("xdg-open", "/usr/bin/xdg-open"),
                ("Choose another application...", None)
            ]
        for name, path in self.common_apps:
            if path and path.lower().endswith('.exe'):
                icon = get_exe_icon_qicon(path, size=24)
                from PyQt5.QtWidgets import QListWidgetItem
                item = QListWidgetItem(QIcon(icon), name)
                self.app_list.addItem(item)
            else:
                self.app_list.addItem(name)
        layout.addWidget(self.app_list)
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.selected_app = None
        self.app_list.itemDoubleClicked.connect(lambda _: self.accept())
    def get_app_path(self):
        import sys
        idx = self.app_list.currentRow()
        if idx < 0:
            return None
        name, path = self.common_apps[idx]
        if path is not None:
            return path
        # If 'Choose another application...' is selected, show a non-native PyQt file dialog
        try:
            from PyQt5.QtWidgets import QFileDialog
            file_dialog = QFileDialog(self, "Select Application")
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            # Platform-specific filter
            if sys.platform.startswith('win'):
                file_dialog.setNameFilter("Applications (*.exe);;All Files (*)")
            elif sys.platform == 'darwin':
                file_dialog.setNameFilter("Applications (*.app);;All Files (*)")
            else:
                file_dialog.setNameFilter("All Files (*)")
            file_dialog.setOption(QFileDialog.DontUseNativeDialog, True)
            if file_dialog.exec_() == QFileDialog.Accepted:
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    return selected_files[0]
        except Exception as e:
            import traceback
            print(f"[OPENWITH-DIALOG-ERROR] {e}\n{traceback.format_exc()}")
        return None
def precache_video_thumbnails_in_directory(directory, thumbnail_cache, size=128, max_workers=4, parent=None, show_progress=False):
    import sys
    import platform
    import shutil
    # Use robust ffmpeg finder for macOS
    if sys.platform == 'darwin':
        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            print('[ERROR] ffmpeg not found in PATH or common locations. Please install ffmpeg and ensure it is available in your PATH.')
            print('[ERROR] On macOS, you may need to launch your app from a terminal to inherit PATH, or set PATH in your environment.')
            print('[ERROR] You can also set the FFMPEG_PATH environment variable to the full path of ffmpeg.')
            return
    else:
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            print('[ERROR] ffmpeg not found in PATH. Please install ffmpeg and ensure it is available in your PATH.')
            return
    """
    Pre-cache video thumbnails for all video files in a directory in the background.
    Args:
        directory (str): Path to the directory to scan for videos.
        thumbnail_cache (ThumbnailCache): The thumbnail cache instance to use.
        size (int): Thumbnail size in pixels (default 128).
        max_workers (int): Number of threads for parallel extraction.
    """
    import glob
    import concurrent.futures
    video_exts = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v')
    video_files = [f for f in glob.glob(os.path.join(directory, '*')) if os.path.splitext(f)[1].lower() in video_exts]
    # Optional progress dialog and cooperative cancellation
    stop_event = None
    progress_dialog = None
    # Precompute which video files actually need caching so we only show the dialog when work is required
    files_to_cache = []
    try:
        for vf in video_files:
            try:
                if not thumbnail_cache.is_cached(vf, size):
                    files_to_cache.append(vf)
            except Exception:
                files_to_cache.append(vf)
    except Exception:
        files_to_cache = list(video_files)
    thumbnail_info("Found {} video files, to cache: {}", len(video_files), len(files_to_cache))
    # Consult user preference for caching dialog: 'always_show', 'ask', 'always_hide'
    try:
        settings = QSettings("garysfm", "garysfm")
        cache_dialog_pref = settings.value('cache_dialog_pref', 'ask')
    except Exception:
        cache_dialog_pref = 'ask'

    should_show_dialog = False
    if cache_dialog_pref == 'always_show':
        should_show_dialog = True
    elif cache_dialog_pref == 'ask':
        should_show_dialog = bool(show_progress) and bool(files_to_cache)
    elif cache_dialog_pref == 'always_hide':
        should_show_dialog = False
    else:
        should_show_dialog = bool(show_progress) and bool(files_to_cache)

    if should_show_dialog and files_to_cache:
        try:
            from PyQt5.QtWidgets import QProgressDialog, QApplication
            import threading
            stop_event = threading.Event()
            parent_win = parent
            if parent_win is None:
                parent_win = QApplication.instance().activeWindow() if QApplication.instance() else None
            progress_dialog = QProgressDialog('Caching video thumbnails...', 'Cancel', 0, len(files_to_cache), parent_win)
            progress_dialog.setWindowTitle('Video thumbnail caching')
            progress_dialog.setWindowModality(0)
            progress_dialog.setMinimumDuration(200)
            try:
                progress_dialog.canceled.connect(lambda: stop_event.set())
            except Exception:
                pass
            progress_dialog.show()
        except Exception:
            progress_dialog = None
            stop_event = None
    # shutil already imported above; ensure ffmpeg is available
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        print('[ERROR] ffmpeg not found in PATH. Please install ffmpeg and ensure it is available in your PATH.')
        if platform.system() == 'Darwin':
            print('[ERROR] On macOS, you may need to launch your app from a terminal to inherit PATH, or set PATH in your environment.')
        return
    def cache_one_video(video_path):
        # Skip thumbnail cache files themselves
        try:
            if is_thumb_file(video_path):
                logging.getLogger('thumbnail').debug('Skipping video thumbnail for .thumb file: %s', video_path)
                return
        except Exception:
            pass
        if thumbnail_cache.get(video_path, size) is not None:
            logging.getLogger('thumbnail').debug('Already cached: %s', video_path)
            return
        try:
            import ffmpeg
            from PIL import Image
            import tempfile
            logging.getLogger('thumbnail').debug('Probing video: %s', video_path)
            # Use ffmpeg-python with custom ffmpeg path if needed
            probe = ffmpeg.probe(video_path, cmd=ffmpeg_path)
            duration = float(probe['format'].get('duration', 0))
            if duration == 0:
                logging.getLogger('thumbnail').error('Could not determine duration for %s', video_path)
                return
            seek_time = max(duration * 0.1, 1.0)
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp_path = tmp.name
                logging.getLogger('thumbnail').debug('Extracting frame at %.2fs to %s', seek_time, tmp_path)
                (
                    ffmpeg
                    .input(video_path, ss=seek_time)
                    .output(tmp_path, vframes=1, format='image2', vcodec='mjpeg')
                    .overwrite_output()
                    .run(cmd=ffmpeg_path, quiet=False, capture_stdout=True, capture_stderr=True)
                )
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    logging.getLogger('thumbnail').error('ffmpeg did not produce a valid thumbnail for %s', video_path)
                    return
                try:
                    img = Image.open(tmp_path)
                    img = img.convert('RGBA').resize((size, size), Image.LANCZOS)
                    img.save(tmp_path)
                except Exception as e:
                    logging.getLogger('thumbnail').exception('PIL failed to process thumbnail for %s: %s', video_path, e)
                    return
                qimg = QPixmap(tmp_path)
                if qimg.isNull():
                    logging.getLogger('thumbnail').error('QPixmap failed to load thumbnail for %s (trying QImage fallback)', video_path)
                    from PyQt5.QtGui import QImage
                    try:
                        img_fallback = QImage(tmp_path)
                        if not img_fallback.isNull():
                            qimg = QPixmap.fromImage(img_fallback)
                            logging.getLogger('thumbnail').debug('QImage fallback succeeded for %s', video_path)
                        else:
                            logging.getLogger('thumbnail').error('QImage fallback also failed for %s', video_path)
                            return
                    except Exception as e:
                        logging.getLogger('thumbnail').exception('Exception in QImage fallback for %s: %s', video_path, e)
                        return
                thumbnail_cache.put(video_path, size, qimg)
                logging.getLogger('thumbnail').info('Cached video thumbnail for %s', video_path)
            finally:
                try:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            import traceback
            logging.getLogger('thumbnail').exception('Exception for %s: %s', video_path, e)
            traceback.print_exc()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    from concurrent.futures import as_completed
    futures = [executor.submit(cache_one_video, video_path) for video_path in files_to_cache]
    completed = 0
    try:
        for future in as_completed(futures):
            try:
                if stop_event is not None and stop_event.is_set():
                    break
            except Exception:
                pass
            try:
                future.result()
            except Exception:
                pass
            completed += 1
            if progress_dialog is not None:
                try:
                    progress_dialog.setValue(completed)
                    from PyQt5.QtWidgets import QApplication
                    QApplication.processEvents()
                except Exception:
                    pass
    finally:
        try:
            executor.shutdown(wait=False)
        except Exception:
            pass
        if progress_dialog is not None:
            try:
                progress_dialog.close()
            except Exception:
                pass

#!/usr/bin/env python3
"""

Gary's File Manager (garysfm) - Cross-platform Edition



Version: 1.2.1 - Theme enhancements, yellow themes, and visual improvements

A cross-platform file manager built with PyQt5, supporting Windows, macOS, and Linux.



WHAT'S NEW IN 1.1.5 (August 2025):
- New: APK thumbnail extraction and adaptive icon composition (extracts launcher icons from .apk and .xapk)
- New: .xapk support (detect and use embedded APK for thumbnails)
- New: Cache generated APK thumbnails to the thumbnail cache for faster reloads
- New: Improved ISO thumbnails — extract EXE icons and composite them over disc artwork; prefer usable icons and avoid blank/transparent results
- Improved: Multiple thumbnail heuristics and robust fallbacks for varied APK/ISO layouts

FEATURES (including previous versions):
- Drag-and-drop files directly from Gary's File Manager into web browser upload boxes (e.g., GitHub, Google Drive, etc.)
- Now supports native file drag-out for browser-based uploads
- When dragging to a directory within the app, you can choose Move or Copy
- Video thumbnailing for major formats (mp4, mkv, avi, mov, etc.)
- ffmpeg-based thumbnail extraction (cross-platform)
- Persistent thumbnail cache for images and videos
- Improved error handling and stability (no more hangs)
- "Open with..." option in right-click menu for files
- Custom PyQt dialog for choosing applications (cross-platform, non-native)
- Platform-specific handling for launching files with chosen apps
- Improved cross-platform experience for "Open with..."

Performance & Memory Optimizations:
- Virtual file loading with lazy loading for large directories
- Persistent thumbnail cache to disk for faster loading
- Background file system monitoring and updates
- Memory usage optimization with automatic garbage collection
- Advanced caching system for file metadata and icons

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
- Terminal support: Terminal.app and iTerm2 via enhanced AppleScript
- File operations: Improved Finder integration with better error handling
- Trash support: Multiple fallback methods (AppleScript, trash command, ~/.Trash)
- System requirements: macOS 10.12+ (Sierra or later)
- Native UI: Automatic dark mode detection, native menu bar, proper window behavior
- File filtering: Comprehensive .DS_Store and system file filtering
- Localization: Support for localized folder names (Documents, Downloads, etc.)
- Drag & Drop: Enhanced file dropping with proper path normalization

Linux:
- Terminal support: Auto-detection of gnome-terminal, konsole, xfce4-terminal, etc.
- File operations: XDG-compliant file managers (nautilus, dolphin, thunar, etc.)
- Trash support: gio trash command (usually pre-installed)
- Desktop environment integration via XDG utilities


Usage:
python garysfm_1.1.2.py

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
import time
import threading
import gc
import hashlib
import pickle
import tempfile
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, OrderedDict
from pathlib import Path
import platform
import re
import fnmatch
import zipfile
import tarfile
import gzip
import tempfile
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QFileSystemModel, QListView, QTableView,
    QVBoxLayout, QWidget, QHBoxLayout, QMessageBox, QGridLayout, QSplitter,
    QSizePolicy, QLabel, QAction, QPushButton, QScrollArea, QMenu, QInputDialog, QFileIconProvider,
    QDialog, QLineEdit, QRadioButton, QButtonGroup, QTextEdit, QCheckBox, QStatusBar, QShortcut,
    QComboBox, QToolBar, QFrame, QSlider, QSpinBox, QTabWidget, QPlainTextEdit, QHeaderView, QProgressBar,
    QGroupBox, QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem, QProgressDialog, QStyle,
    QTabBar, QStackedWidget, QMdiArea, QMdiSubWindow, QFileDialog, QLayout, QDateEdit, QSpacerItem,
    QStyledItemDelegate, QFormLayout
)
from PyQt5.QtCore import QDir, Qt, pyqtSignal, QFileInfo, QPoint, QRect, QTimer, QThread, QStringListModel, QSortFilterProxyModel, QModelIndex, QSize, QMimeData, QUrl, QEvent, QObject, QMutex, QWaitCondition, QDate
from PyQt5.QtCore import pyqtSlot


class GuiInvoker(QObject):
    """Singleton QObject used to invoke callables on the GUI thread via signal."""
    invoke = pyqtSignal(object)

    _instance = None

    def __init__(self):
        super().__init__()
        self.invoke.connect(self._on_invoke)

    @pyqtSlot(object)
    def _on_invoke(self, fn):
        try:
            if callable(fn):
                fn()
        except Exception:
            pass

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = GuiInvoker()
        return cls._instance

# Ensure GuiInvoker is created on the main thread during module import so
# background threads can safely emit to it without creating QObjects in other threads.
try:
    _ = GuiInvoker.instance()
except Exception:
    pass


def format_filename_with_underscore_wrap(filename, max_length_before_wrap=20):
    """
    Format filename to enable word wrapping at underscores for long names.
    Replaces underscores with a zero-width space followed by underscore
    to allow natural line breaks at underscore positions.
    
    Args:
        filename (str): The original filename
        max_length_before_wrap (int): Minimum length before considering wrapping
        
    Returns:
        str: Formatted filename with wrap-friendly underscores
    """
    # Only apply wrapping for longer filenames to avoid unnecessary breaks
    if len(filename) > max_length_before_wrap and '_' in filename:
        # Replace underscores with zero-width space + underscore
        # This allows Qt's word wrap to break at these positions
        return filename.replace('_', '\u200B_')
    return filename

def truncate_filename_for_display(filename, max_chars=13, selected=False):
    """
    Truncate filename for display, keeping only the beginning.
    Shows full name when selected, truncated otherwise.
    
    Args:
        filename (str): The original filename
        max_chars (int): Maximum characters to show when not selected
        selected (bool): Whether the item is currently selected
        
    Returns:
        str: Truncated or full filename based on selection state
    """
    if selected or len(filename) <= max_chars:
        return filename
    
    # Truncate to max_chars, no ellipsis - just cut off at character limit
    return filename[:max_chars]

class ArchiveManager:
    """
    Archive management class for handling ZIP, TAR, and other archive formats.
    Provides functionality to create, extract, and browse archive contents.
    """
    
    # Supported archive extensions
    ARCHIVE_EXTENSIONS = {
        '.zip': 'ZIP Archive',
        '.tar': 'TAR Archive', 
        '.tar.gz': 'Gzipped TAR Archive',
        '.tgz': 'Gzipped TAR Archive',
        '.tar.bz2': 'Bzipped TAR Archive',
        '.tbz2': 'Bzipped TAR Archive',
        '.gz': 'Gzipped File',
        '.rar': 'RAR Archive (read-only)'
    , '.iso': 'ISO Image'
    }
    
    @staticmethod
    def is_archive(file_path):
        """Check if a file is a supported archive format"""
        file_path_lower = str(file_path).lower()
        for ext in ArchiveManager.ARCHIVE_EXTENSIONS.keys():
            if file_path_lower.endswith(ext):
                return True
        return False
    
    @staticmethod
    def get_archive_type(file_path):
        """Get the archive type from file extension"""
        file_path_lower = str(file_path).lower()
        for ext in ArchiveManager.ARCHIVE_EXTENSIONS.keys():
            if file_path_lower.endswith(ext):
                return ext
        return None
    @staticmethod
    def extract_exe_icon_from_iso(iso_path, size=128):
        """
        Extract the icon from the first .exe found in the ISO (prefer setup.exe), return as QPixmap.
        Returns None if not possible.
        """
        try:
            import pycdlib
            import tempfile
            import os
            from PyQt5.QtGui import QPixmap

            # Use the global thumbnail cache if available to avoid repeated extraction
            cache = get_global_thumbnail_cache()
            if cache and cache.is_cached(iso_path, size):
                try:
                    pix = cache.get(iso_path, size)
                    if pix and not pix.isNull():
                        return pix
                except Exception:
                    pass

            # First, get a list of file entries from the ISO using the existing listing helper.
            success, entries_or_err = ArchiveManager.list_archive_contents(iso_path)
            if not success:
                # Fall back to simple root scan if listing helper failed for some reason
                try:
                    iso = pycdlib.PyCdlib()
                    iso.open(iso_path)
                    children = iso.list_children(iso_path='/')
                    entries = []
                    for c in children:
                        try:
                            name = c.file_identifier().decode(errors='ignore').rstrip(';1')
                        except Exception:
                            name = ''
                        if not name:
                            continue
                        full = '/' + name
                        if c.is_dir() and not full.endswith('/'):
                            full = full + '/'
                        entries.append({'name': full, 'is_dir': c.is_dir()})
                    try:
                        iso.close()
                    except Exception:
                        pass
                except Exception:
                    return None
            else:
                entries = entries_or_err

            # Find EXE candidates (prefer setup.exe)
            exe_candidates = [e['name'] for e in entries if (not e.get('is_dir')) and e['name'].lower().endswith('.exe')]
            if not exe_candidates:
                # Also try case-insensitive search for filenames that include '.exe' somewhere
                exe_candidates = [e['name'] for e in entries if (not e.get('is_dir')) and '.exe' in e['name'].lower()]
            if not exe_candidates:
                return None

            preferred = None
            for n in exe_candidates:
                if 'setup.exe' in n.lower():
                    preferred = n
                    break
            if not preferred:
                preferred = exe_candidates[0]

            # Try extracting the preferred EXE using pycdlib with multiple path strategies
            iso = pycdlib.PyCdlib()
            iso.open(iso_path)
            tmp_path = None
            tried = []
            for variant in (preferred, preferred + ';1', os.path.basename(preferred), os.path.basename(preferred) + ';1'):
                if not variant:
                    continue
                # normalize leading slash for variants passed to pycdlib
                if not variant.startswith('/'):
                    variant_path = '/' + variant
                else:
                    variant_path = variant
                # attempt iso_path, joliet_path, and rr_path options
                for kw in ('iso_path', 'joliet_path', 'rr_path'):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.exe') as tmp:
                            # Use keyword arg by building kwargs dict to pass to get_file_from_iso_fp
                            kwargs = {kw: variant_path}
                            try:
                                iso.get_file_from_iso_fp(tmp, **kwargs)
                            except Exception as ex_get:
                                msg = str(ex_get)
                                if 'unopack_from requires a buffer' in msg or 'unpack_from requires a buffer' in msg:
                                    # Specific pycdlib parsing error - log and try next variant
                                    tried.append((variant_path, kw, f"pycdlib buffer error: {msg}"))
                                    try:
                                        tmp.close()
                                    except Exception:
                                        pass
                                    # ensure any partial temp file is removed
                                    try:
                                        if os.path.exists(tmp.name):
                                            os.remove(tmp.name)
                                    except Exception:
                                        pass
                                    continue
                                else:
                                    raise
                            tmp_path = tmp.name

                        if tmp_path and os.path.exists(tmp_path):
                            # success
                            break
                    except Exception as e:
                        tried.append((variant_path, kw, str(e)))
                        # try next variant/kw
                        try:
                            # ensure temp file cleaned up if partially written
                            if 'tmp' in locals() and not tmp.closed:
                                tmp.close()
                        except Exception:
                            pass
                if tmp_path:
                    break

            try:
                iso.close()
            except Exception:
                pass

            if not tmp_path:
                # If pycdlib variants failed, try a 7-Zip (7z) fallback to extract the single
                # candidate file, and if that fails, fall back to extracting the full ISO to
                # a temp directory and searching for EXE files there.
                try:
                    import shutil, subprocess
                    seven = None
                    for cmd in ('7z', '7z.exe', '7zz', '7za', '7zr'):
                        seven_path = shutil.which(cmd)
                        if seven_path:
                            seven = seven_path
                            break
                    if seven:
                        for exe_entry in exe_candidates:
                            try:
                                tmpfh = tempfile.NamedTemporaryFile(delete=False, suffix='.exe')
                                tmpfh.close()
                                candidate_name = exe_entry.lstrip('/')
                                # Use 7z to extract the single file to stdout and write to the temp file
                                with open(tmpfh.name, 'wb') as outp:
                                    subprocess.run([seven, 'e', '-so', iso_path, candidate_name], stdout=outp, stderr=subprocess.DEVNULL, check=True)
                                if os.path.exists(tmpfh.name) and os.path.getsize(tmpfh.name) > 0:
                                    tmp_path = tmpfh.name
                                    break
                                else:
                                    try:
                                        os.remove(tmpfh.name)
                                    except Exception:
                                        pass
                            except Exception:
                                try:
                                    if 'tmpfh' in locals() and os.path.exists(tmpfh.name):
                                        os.remove(tmpfh.name)
                                except Exception:
                                    pass
                                continue

                    # If still not found, attempt full extraction to a temp dir and look for EXEs
                    if not tmp_path:
                        tmpdir = None
                        try:
                            tmpdir = tempfile.mkdtemp(prefix='garysfm_iso_')
                            extracted_any = False
                            # Try using pycdlib to extract all files if available
                            try:
                                import pycdlib
                                iso2 = pycdlib.PyCdlib()
                                iso2.open(iso_path)
                                # Use the previously built entries list if present; otherwise list
                                success_list, entries_list = ArchiveManager.list_archive_contents(iso_path)
                                if success_list and entries_list:
                                    for ent in entries_list:
                                        if ent.get('is_dir'):
                                            continue
                                        rel = ent['name'].lstrip('/')
                                        outpath = os.path.join(tmpdir, *rel.split('/'))
                                        outdir = os.path.dirname(outpath)
                                        os.makedirs(outdir, exist_ok=True)
                                        extracted = False
                                        for kw in ('iso_path', 'joliet_path', 'rr_path'):
                                            try:
                                                with open(outpath, 'wb') as out_f:
                                                    iso2.get_file_from_iso_fp(out_f, **{kw: '/' + rel})
                                                extracted = True
                                                break
                                            except Exception:
                                                try:
                                                    if os.path.exists(outpath):
                                                        os.remove(outpath)
                                                except Exception:
                                                    pass
                                                continue
                                        if extracted:
                                            extracted_any = True
                                try:
                                    iso2.close()
                                except Exception:
                                    pass
                            except Exception:
                                # pycdlib full-extract failed or not present; try 7z full extract
                                try:
                                    if seven:
                                        # x = extract with full paths; -o sets output dir
                                        subprocess.run([seven, 'x', f'-o{tmpdir}', iso_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                                        extracted_any = True
                                except Exception:
                                    extracted_any = False

                            # If extraction produced files, scan for EXE candidates
                            if extracted_any:
                                found = []
                                for root, dirs, files in os.walk(tmpdir):
                                    for fn in files:
                                        if fn.lower().endswith('.exe'):
                                            found.append(os.path.join(root, fn))
                                # Prefer setup.exe and nearest-to-root matches
                                preferred_exe = None
                                for path in found:
                                    if os.path.basename(path).lower() == 'setup.exe':
                                        preferred_exe = path
                                        break
                                if not preferred_exe and found:
                                    # pick the shortest relative path (closest to root)
                                    preferred_exe = min(found, key=lambda p: p.count(os.sep))
                                if preferred_exe:
                                    tmp_path = preferred_exe
                        except Exception:
                            pass
                        finally:
                            # if we didn't assign tmp_path from tmpdir extraction, we still want to
                            # keep tmpdir around until after icon extraction uses tmp_path; cleanup
                            # will be attempted later in finally blocks below. Store tmpdir in locals
                            if 'tmpdir' in locals():
                                # we will attempt to remove it after icon extraction
                                pass
                except Exception:
                    # Don't escalate failures from the fallback; we'll log below and return None
                    pass

            if not tmp_path:
                # log attempted variants for debugging (use print to avoid depending on logging setup)
                print(f"[ISO-THUMBNAIL] Could not extract EXE from {iso_path}; tried: {tried}")
                # If we created a tmpdir but couldn't find an EXE, remove it to avoid leaks
                try:
                    if 'tmpdir' in locals() and tmpdir and os.path.exists(tmpdir):
                        import shutil as _sh
                        _sh.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                return None

            # Use existing icon extraction
            try:
                icon = get_exe_icon_qicon(tmp_path, size=size)
            except Exception as e:
                print(f"[ISO-THUMBNAIL] get_exe_icon_qicon failed for {tmp_path}: {e}")
                icon = None
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            if icon and (not icon.isNull()):
                try:
                    pix = icon.pixmap(size, size)
                    # Store in cache for future use
                    if cache:
                        try:
                            cache.put(iso_path, size, pix)
                        except Exception:
                            pass
                    return pix
                except Exception:
                    return None
            return None
        except Exception as e:
            print(f"[ISO-THUMBNAIL] Failed to extract EXE icon from {iso_path}: {e}")
            return None
    
    @staticmethod
    def create_zip_archive(source_paths, output_path, progress_callback=None):
        """
        Create a ZIP archive from multiple source paths
        
        Args:
            source_paths (list): List of file/folder paths to archive
            output_path (str): Output ZIP file path
            progress_callback (callable): Optional callback for progress updates
        """
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                total_files = 0
                processed_files = 0
                # Count total files for progress tracking
                for source_path in source_paths:
                    if os.path.isfile(source_path):
                        total_files += 1
                    elif os.path.isdir(source_path):
                        pass
                # Add files to archive
                for source_path in source_paths:
                    if os.path.isfile(source_path):
                        arcname = os.path.basename(source_path)
                        zipf.write(source_path, arcname)
                        processed_files += 1
                        if progress_callback:
                            progress_callback(processed_files, total_files)
                    elif os.path.isdir(source_path):
                        base_dir = os.path.basename(source_path)
                        for root, dirs, files in os.walk(source_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(base_dir, os.path.relpath(file_path, source_path))
                                zipf.write(file_path, arcname)
                                processed_files += 1
                                if progress_callback:
                                    progress_callback(processed_files, total_files)
            
            return True, f"Archive created successfully: {output_path}"
            
        except Exception as e:
            return False, f"Failed to create archive: {str(e)}"
    
    @staticmethod
    def extract_archive(archive_path, extract_to, progress_callback=None):
        """
        Extract an archive to the specified directory
        
        Args:
            archive_path (str): Path to the archive file
            extract_to (str): Directory to extract files to
            progress_callback (callable): Optional callback for progress updates
        """
        try:
            import os
            archive_type = ArchiveManager.get_archive_type(archive_path)
            # Derive a readable extension if detection failed
            try:
                from os.path import splitext
                readable_ext = archive_type if archive_type else splitext(str(archive_path))[1].lower()
            except Exception:
                readable_ext = archive_type

            if archive_type == '.zip':
                return ArchiveManager._extract_zip(archive_path, extract_to, progress_callback)
            elif archive_type in ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2']:
                return ArchiveManager._extract_tar(archive_path, extract_to, progress_callback)
            elif archive_type == '.gz':
                return ArchiveManager._extract_gzip(archive_path, extract_to, progress_callback)
            elif archive_type == '.iso':
                # Implement ISO extraction using pycdlib
                try:
                    import pycdlib
                    import os
                    from datetime import datetime

                    if not os.path.exists(archive_path) or not os.path.isfile(archive_path):
                        return False, f"ISO file not found or not a file: {archive_path}"

                    success, entries_or_err = ArchiveManager.list_archive_contents(archive_path)
                    if not success:
                        return False, f"Failed to list ISO contents before extraction: {entries_or_err}"

                    entries = entries_or_err
                    # Filter to files only
                    files = [e for e in entries if not e.get('is_dir')]
                    total = len(files)
                    processed = 0

                    iso = pycdlib.PyCdlib()
                    iso.open(archive_path)

                    errors = []
                    for e in files:
                        try:
                            # e['name'] is like '/DIR/FILE.EXE' or '/FILE.TXT'
                            rel_path = e['name'].lstrip('/')
                            # Normalize separators
                            rel_path = rel_path.replace('\\', '/').lstrip('/')
                            out_path = os.path.join(extract_to, *rel_path.split('/'))
                            out_dir = os.path.dirname(out_path)
                            if out_dir and not os.path.exists(out_dir):
                                os.makedirs(out_dir, exist_ok=True)

                            # Try multiple pycdlib extraction kwargs for robustness
                            extracted = False
                            for kw in ('iso_path', 'joliet_path', 'rr_path'):
                                try:
                                    with open(out_path, 'wb') as out_f:
                                        kwargs = {kw: '/' + rel_path}
                                        try:
                                            iso.get_file_from_iso_fp(out_f, **kwargs)
                                        except Exception as ex_get:
                                            msg = str(ex_get)
                                            if 'unopack_from requires a buffer' in msg or 'unpack_from requires a buffer' in msg:
                                                # Skip this file on buffer unpack error
                                                raise Exception(f"pycdlib buffer unpack error for {e['name']}: {msg}")
                                            else:
                                                raise
                                    extracted = True
                                    break
                                except Exception:
                                    # Try next kw
                                    try:
                                        if os.path.exists(out_path):
                                            os.remove(out_path)
                                    except Exception:
                                        pass

                            if not extracted:
                                errors.append(f"Could not extract {e['name']}")

                        except Exception as ee:
                            errors.append(f"Error extracting {e.get('name')}: {ee}")

                        processed += 1
                        if progress_callback:
                            try:
                                if not progress_callback(processed, total):
                                    # Caller requested cancellation
                                    break
                            except Exception:
                                pass

                    try:
                        iso.close()
                    except Exception:
                        pass

                    if errors:
                        return False, f"Extraction completed with errors: {errors[:5]}"
                    return True, f"ISO extracted to: {extract_to}"

                except Exception as ex:
                    return False, f"ISO extraction failed: {ex}"
            else:
                return False, f"Unsupported archive format: {readable_ext} for file {archive_path}"
        except Exception as e:
            return False, f"Failed to extract archive: {str(e)}"
    
    @staticmethod
    def _extract_zip(archive_path, extract_to, progress_callback=None):
        """Extract ZIP archive"""
        with zipfile.ZipFile(archive_path, 'r') as zipf:
            members = zipf.infolist()
            total_files = len(members)
            
            for i, member in enumerate(members):
                zipf.extract(member, extract_to)
                if progress_callback:
                    progress_callback(i + 1, total_files)
        
        return True, f"ZIP archive extracted to: {extract_to}"
    
    @staticmethod
    def _extract_tar(archive_path, extract_to, progress_callback=None):
        """Extract TAR archive (including compressed variants)"""
        mode = 'r'
        if archive_path.endswith('.gz') or archive_path.endswith('.tgz'):
            mode = 'r:gz'
        elif archive_path.endswith('.bz2') or archive_path.endswith('.tbz2'):
            mode = 'r:bz2'
        
        with tarfile.open(archive_path, mode) as tarf:
            members = tarf.getmembers()
            total_files = len(members)
            
            for i, member in enumerate(members):
                tarf.extract(member, extract_to)
                if progress_callback:
                    progress_callback(i + 1, total_files)
        
        return True, f"TAR archive extracted to: {extract_to}"
    
    @staticmethod
    def _extract_gzip(archive_path, extract_to, progress_callback=None):
        """Extract GZIP file"""
        output_name = os.path.splitext(os.path.basename(archive_path))[0]
        output_path = os.path.join(extract_to, output_name)
        
        with gzip.open(archive_path, 'rb') as gz_file:
            with open(output_path, 'wb') as out_file:
                out_file.write(gz_file.read())
        
        if progress_callback:
            progress_callback(1, 1)
        
        return True, f"GZIP file extracted to: {output_path}"
    
    @staticmethod
    def list_archive_contents(archive_path):
        """
        List the contents of an archive without extracting
        Args:
            archive_path (str): Path to the archive file
        Returns:
            tuple: (success, contents_list or error_message)
        """
        try:
            archive_type = ArchiveManager.get_archive_type(archive_path)
            if archive_type == '.zip':
                return ArchiveManager._list_zip_contents(archive_path)
            elif archive_type in ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2']:
                return ArchiveManager._list_tar_contents(archive_path)
            elif archive_type == '.iso':
                # Use pycdlib to list ISO contents with iterative traversal to avoid recursion issues
                try:
                    import pycdlib
                    from datetime import datetime
                    import os
                    from collections import deque
                    iso = pycdlib.PyCdlib()
                    iso.open(archive_path)
                    contents = []
                    q = deque(['/'])
                    visited = set()
                    while q:
                        cur = q.popleft()
                        if cur in visited:
                            continue
                        visited.add(cur)
                        # Attempt listing using multiple pycdlib namespace variants to
                        # handle inconsistent Rock Ridge / Joliet / ISO9660 images.
                        children = None
                        for list_kw in ('iso_path', 'joliet_path', 'rr_path'):
                            try:
                                kwargs = {list_kw: cur}
                                tmp_children = iso.list_children(**kwargs)
                                # If this yields results, use them
                                if tmp_children:
                                    children = tmp_children
                                    break
                                # If empty but no exception, keep trying other namespaces
                            except Exception:
                                # Try next namespace
                                continue
                        # Final fallback: try the generic call if available
                        if children is None:
                            try:
                                children = iso.list_children(iso_path=cur)
                            except Exception:
                                # Could not list this directory in any namespace
                                continue
                        if not children:
                            # Nothing to iterate (empty dir)
                            continue
                        for child in children:
                            try:
                                # Some ISO images or pycdlib records can be malformed or incomplete
                                # (which may raise struct/pack/unpack errors). Protect each
                                # child record parse and skip entries that raise unexpected
                                # exceptions rather than aborting the whole listing.
                                try:
                                    raw_name = child.file_identifier().decode(errors='ignore')
                                except Exception:
                                    # If we cannot obtain a name, skip this record
                                    continue
                                # Skip special entries
                                name = raw_name.rstrip(';1')
                                if not name or name in ('.', '..'):
                                    continue
                                try:
                                    is_dir = child.is_dir()
                                except Exception:
                                    # Skip entries we cannot classify
                                    continue
                                try:
                                    size = child.data_length() if not is_dir else 0
                                except Exception:
                                    # If size cannot be read, set to 0 and continue
                                    size = 0
                                dt = None
                                try:
                                    dt = child.datetime()
                                    if isinstance(dt, tuple):
                                        dt = datetime(*dt[:6])
                                except Exception:
                                    dt = datetime.now()

                                # Build a normalized full path (leading slash)
                                if cur == '/':
                                    full = '/' + name
                                else:
                                    full = os.path.join(cur, name).replace('\\', '/')
                                if is_dir and not full.endswith('/'):
                                    full = full + '/'
                                contents.append({
                                    'name': full,
                                    'size': size,
                                    'compressed_size': size,
                                    'is_dir': is_dir,
                                    'date_time': dt,
                                    'type': 'folder' if is_dir else 'file'
                                })
                                if is_dir:
                                    # Enqueue directory for traversal
                                    if full not in visited:
                                        q.append(full)
                            except Exception as child_err:
                                # Defensive: skip problematic records but log for debugging
                                print(f"[ISO-LIST] Skipping malformed ISO directory record in {archive_path} at {cur}: {child_err}")
                                continue
                    try:
                        iso.close()
                    except Exception:
                        pass
                    return True, contents
                except Exception as e:
                    # Write a detailed traceback to a log file to aid debugging of
                    # inconsistent Rock Ridge / Joliet issues. Place log in thumbnail cache dir.
                    try:
                        import traceback
                        cache = get_global_thumbnail_cache()
                        cache_dir = cache.cache_dir if cache else os.path.join(tempfile.gettempdir(), 'garysfm_thumbnails')
                        os.makedirs(cache_dir, exist_ok=True)
                        safe_name = os.path.basename(archive_path).replace(os.path.sep, '_')
                        log_path = os.path.join(cache_dir, f"iso_list_error_{safe_name}.log")
                        with open(log_path, 'w', encoding='utf-8') as lf:
                            lf.write(f"Failed to list ISO contents for: {archive_path}\n\n")
                            lf.write(traceback.format_exc())
                    except Exception:
                        log_path = None
                    msg = str(e)
                    if log_path:
                        return False, f"Failed to list ISO contents: {msg} (details logged to: {log_path})"
                    else:
                        return False, f"Failed to list ISO contents: {msg}"
            else:
                return False, f"Cannot browse contents of {archive_type} files"
        except Exception as e:
            return False, f"Failed to list archive contents: {str(e)}"
    
    @staticmethod
    def _list_zip_contents(archive_path):
        """List ZIP archive contents"""
        contents = []
        with zipfile.ZipFile(archive_path, 'r') as zipf:
            for info in zipf.infolist():
                contents.append({
                    'name': info.filename,
                    'size': info.file_size,
                    'compressed_size': info.compress_size,
                    'is_dir': info.is_dir(),
                    'date_time': datetime(*info.date_time),
                    'type': 'folder' if info.is_dir() else 'file'
                })
        return True, contents
    
    @staticmethod
    def _list_tar_contents(archive_path):
        """List TAR archive contents"""
        mode = 'r'
        if archive_path.endswith('.gz') or archive_path.endswith('.tgz'):
            mode = 'r:gz'
        elif archive_path.endswith('.bz2') or archive_path.endswith('.tbz2'):
            mode = 'r:bz2'
        
        contents = []
        with tarfile.open(archive_path, mode) as tarf:
            for member in tarf.getmembers():
                contents.append({
                    'name': member.name,
                    'size': member.size,
                    'compressed_size': member.size,  # TAR doesn't compress per-file
                    'is_dir': member.isdir(),
                    'date_time': datetime.fromtimestamp(member.mtime),
                    'type': 'folder' if member.isdir() else 'file'
                })
        return True, contents

class ArchiveBrowserDialog(QDialog):
    """
    Dialog for browsing archive contents before extraction
    """
    
    def __init__(self, archive_path, parent=None):
        super().__init__(parent)
        self.archive_path = archive_path
        self.selected_items = []
        self.parent = parent
        self.init_ui()
        self.apply_theme()  # Apply theme after UI is initialized
        self.load_archive_contents()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle(f"Archive Browser - {os.path.basename(self.archive_path)}")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout()
        
        # Archive info label
        info_label = QLabel(f"Archive: {self.archive_path}")
        info_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(info_label)
        
        # Contents table
        self.contents_table = QTableWidget()
        self.contents_table.setColumnCount(4)
        self.contents_table.setHorizontalHeaderLabels(['Name', 'Type', 'Size', 'Modified'])
        self.contents_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.contents_table.setAlternatingRowColors(False)  # Don't use alternating colors - respect theme
        self.contents_table.setSortingEnabled(True)
        
        # Make table columns resizable
        header = self.contents_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.contents_table)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_items)
        button_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self.select_no_items)
        button_layout.addWidget(self.select_none_btn)
        
        button_layout.addStretch()
        
        self.extract_btn = QPushButton("Extract Selected")
        self.extract_btn.clicked.connect(self.accept)
        self.extract_btn.setDefault(True)
        button_layout.addWidget(self.extract_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_archive_contents(self):
        """Load and display archive contents"""
        try:
            success, contents = ArchiveManager.list_archive_contents(self.archive_path)
            
            if not success:
                QMessageBox.warning(self, "Error", contents)
                return
            
            self.contents_table.setRowCount(len(contents))
            
            for i, item in enumerate(contents):
                # Name column
                name_item = QTableWidgetItem(item['name'])
                if item['is_dir']:
                    name_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                else:
                    name_item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                self.contents_table.setItem(i, 0, name_item)
                
                # Type column
                type_item = QTableWidgetItem(item['type'].title())
                self.contents_table.setItem(i, 1, type_item)
                
                # Size column
                if item['is_dir']:
                    size_text = "-"
                else:
                    size_text = self.format_file_size(item['size'])
                size_item = QTableWidgetItem(size_text)
                size_item.setData(Qt.UserRole, item['size'])  # Store actual size for sorting
                self.contents_table.setItem(i, 2, size_item)
                
                # Modified column
                date_text = item['date_time'].strftime('%Y-%m-%d %H:%M:%S')
                date_item = QTableWidgetItem(date_text)
                date_item.setData(Qt.UserRole, item['date_time'])  # Store actual date for sorting
                self.contents_table.setItem(i, 3, date_item)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load archive contents: {str(e)}")
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def select_all_items(self):
        """Select all items in the table"""
        self.contents_table.selectAll()
    
    def select_no_items(self):
        """Deselect all items in the table"""
        self.contents_table.clearSelection()
    
    def get_selected_items(self):
        """Get list of selected item names"""
        selected_items = []
        for row in range(self.contents_table.rowCount()):
            if self.contents_table.item(row, 0).isSelected():
                selected_items.append(self.contents_table.item(row, 0).text())
        return selected_items
    
    def apply_theme(self):
        """Apply dark or light theme based on current setting (uses named light color themes)."""
        # Determine effective dark mode from self or parent
        dark_mode = False
        try:
            if getattr(self, 'dark_mode', False):
                dark_mode = True
            elif hasattr(self, 'parent') and getattr(self.parent, 'dark_mode', False):
                dark_mode = True
        except Exception:
            dark_mode = getattr(self, 'dark_mode', False)

        try:
            if dark_mode:
                # Dark mode styling (kept concise)
                dark_style = (
                    "QWidget { background-color: #2b2b2b; color: #ffffff; }"
                    "QMenu { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; }"
                    "QToolBar { background-color: #404040; color: #ffffff; border: none; }"
                    "QTabWidget::pane { background-color: #3c3c3c; color: #ffffff; }"
                    "QTabBar::tab { background-color: #404040; color: #ffffff; padding: 8px 16px; }"
                )
                self.setStyleSheet(dark_style)
            else:
                # Light mode: apply named theme if available
                theme_name = getattr(self, 'color_theme', 'Default Light')
                theme = getattr(self, 'COLOR_THEMES', {}).get(theme_name)
                if theme:
                    win = theme.get('window_bg', '#ffffff')
                    panel = theme.get('panel_bg', '#f5f5f5')
                    text = theme.get('text', '#000000')
                    accent = theme.get('accent', '#0078d7')

                    light_style = f"""
QWidget, QDialog {{
    background-color: {win};
    color: {text};
}}
QFrame, QGroupBox {{
    background-color: {panel};
    color: {text};
}}
QLabel {{ color: {text}; background-color: transparent; }}
QPushButton {{
    background-color: {panel};
    color: {text};
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 3px;
    padding: 5px 12px;
}}
QPushButton:hover {{ background-color: {win}; }}
QTableWidget {{
    background-color: {panel};
    color: {text};
    gridline-color: rgba(0,0,0,0.06);
}}
QHeaderView::section {{ background-color: {panel}; color: {text}; padding: 4px; }}
QMenuBar {{ background-color: {win}; color: {text}; }}
QMenu {{ background-color: {panel}; color: {text}; }}
QToolBar {{ background-color: {win}; border: none; }}
QLineEdit, QTextEdit, QPlainTextEdit {{ background-color: #ffffff; color: {text}; border: 1px solid rgba(0,0,0,0.08); }}
QProgressBar {{ background-color: {panel}; color: {text}; }}
QScrollBar:vertical {{ background: {panel}; }}
/* Accent color for selections */
QWidget:selected, QTableWidget::item:selected {{ background-color: {accent}; color: #ffffff; }}
"""
                    self.setStyleSheet(light_style)
                else:
                    self.setStyleSheet("")
        except Exception:
            # On error, reset to no stylesheet
            self.setStyleSheet("")

class FormattedFileSystemModel(QFileSystemModel):
    """
    Custom QFileSystemModel that applies underscore word wrapping to display names.
    This ensures folder and file names can wrap at underscores in list and detail views.
    """
    
    def data(self, index, role):
        """Override data method to apply formatting to display names and provide icons for list/detail views"""
        if role == Qt.DisplayRole:
            # Get the original filename from the base model
            original_name = super().data(index, role)
            if original_name:
                # Apply underscore wrapping formatting
                return format_filename_with_underscore_wrap(str(original_name))
        elif role == Qt.DecorationRole and index.column() == 0:
            # Provide the icon for the first column (left end)
            return super().data(index, Qt.DecorationRole)
        # For all other roles, use the original data
        return super().data(index, role)

class WordWrapDelegate(QStyledItemDelegate):
    """
    Custom delegate that handles word wrapping and name truncation.
    Shows truncated names (13 chars) normally, full names when selected.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
    
    def paint(self, painter, option, index):
        """Custom paint method that handles truncation, word wrapping, icon drawing, and drive usage bar"""
        import os
        import shutil
        # Draw background and selection
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        # Draw icon if present
        icon = index.data(Qt.DecorationRole)
        rect = option.rect
        icon_size = option.decorationSize if hasattr(option, 'decorationSize') else QSize(20, 20)
        if isinstance(icon, QIcon):
            icon_rect = QRect(rect.left() + 3, rect.top() + (rect.height() - icon_size.height()) // 2, icon_size.width(), icon_size.height())
            icon.paint(painter, icon_rect, Qt.AlignVCenter | Qt.AlignLeft)
            text_offset = icon_size.width() + 8
        else:
            text_offset = 3

        # Get the original text
        original_text = index.data(Qt.DisplayRole)
        if not original_text:
            return

        # Check if item is selected
        is_selected = option.state & QStyle.State_Selected

        # Apply truncation based on selection state
        display_text = truncate_filename_for_display(str(original_text), max_chars=13, selected=is_selected)

        # Apply underscore wrapping if not truncated
        if is_selected or len(original_text) <= 13:
            display_text = format_filename_with_underscore_wrap(display_text)

        # Set up the text document for rendering
        doc = QTextDocument()
        doc.setPlainText(display_text)
        doc.setDefaultFont(option.font)
        doc.setTextWidth(rect.width() - text_offset - 6)

        # Set word wrap mode to wrap at word boundaries (including zero-width spaces)
        doc.setDefaultTextOption(QTextOption(Qt.AlignLeft | Qt.AlignVCenter))
        text_option = doc.defaultTextOption()
        text_option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)

        # Set text color
        if is_selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            bg_color = option.palette.base().color()
            is_dark_mode = bg_color.lightness() < 128
            if is_dark_mode:
                font = option.font
                font.setBold(True)
                doc.setDefaultFont(font)
                text_format = QTextCharFormat()
                text_format.setForeground(QBrush(QColor(255, 255, 255)))
                text_format.setFont(font)
                cursor = QTextCursor(doc)
                cursor.select(QTextCursor.Document)
                cursor.setCharFormat(text_format)
                painter.setPen(QColor(255, 255, 255))
            else:
                painter.setPen(option.palette.text().color())

        # Draw the text with proper margins to prevent cutoff, shifted right for icon
        painter.save()
        text_rect = QRect(rect.left() + text_offset, rect.top() + 2, rect.width() - text_offset - 3, rect.height() - 24)
        painter.translate(text_rect.topLeft())
        doc.setTextWidth(text_rect.width())
        doc.drawContents(painter)
        painter.restore()

        # --- Custom: Draw drive usage bar if in drive-list mode and this is a drive root ---
        # Heuristic: If the item is a drive root (like 'C:/'), show the bar
        drive_path = None
        try:
            # Only show for top-level items (parent is invalid)
            if not index.parent().isValid():
                # Try to get the absolute path from the model
                file_info = index.model().fileInfo(index)
                if file_info.isRoot() or file_info.isDir():
                    drive_path = file_info.absoluteFilePath()
                    # On Windows, ensure it ends with a slash (C:/)
                    if os.name == 'nt' and len(drive_path) == 2 and drive_path[1] == ':':
                        drive_path += '/'
        except Exception:
            pass
        if drive_path and os.path.ismount(drive_path):
            try:
                usage = shutil.disk_usage(drive_path)
                percent = int(usage.used / usage.total * 100) if usage.total > 0 else 0
                bar_rect = QRect(rect.left() + text_offset, rect.bottom() - 18, rect.width() - text_offset - 10, 12)
                # Draw background bar
                painter.save()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(220, 220, 220) if not is_selected else QColor(80, 80, 80))
                painter.drawRect(bar_rect)
                # Draw usage bar
                bar_width = int(bar_rect.width() * percent / 100)
                painter.setBrush(QColor(0, 120, 215) if not is_selected else QColor(0, 180, 255))
                painter.drawRect(QRect(bar_rect.left(), bar_rect.top(), bar_width, bar_rect.height()))
                painter.restore()
                # Draw text: 'xx% used, 10.2 GB free of 100 GB'
                used_gb = usage.used / (1024 ** 3)
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                usage_text = f"{percent}% used, {free_gb:.1f} GB free of {total_gb:.1f} GB"
                painter.save()
                painter.setPen(QColor(40, 40, 40) if not is_selected else QColor(255, 255, 255))
                font = option.font
                font.setPointSizeF(font.pointSizeF() * 0.9)
                painter.setFont(font)
                painter.drawText(bar_rect, Qt.AlignCenter, usage_text)
                painter.restore()
            except Exception:
                pass
    
    def sizeHint(self, option, index):
        """Calculate the size hint for the text"""
        original_text = index.data(Qt.DisplayRole)
        if not original_text:
            return super().sizeHint(option, index)
        
        # Check if item is selected
        is_selected = option.state & QStyle.State_Selected
        
        # Use truncated text for size calculation when not selected
        display_text = truncate_filename_for_display(str(original_text), max_chars=13, selected=is_selected)
        
        # Create a text document to calculate the required size with margins
        doc = QTextDocument()
        doc.setPlainText(display_text)
        doc.setDefaultFont(option.font)
        # Account for margins when calculating width
        available_width = option.rect.width() - 6 if option.rect.width() > 6 else 200  # Subtract margin space
        doc.setTextWidth(available_width)
        
        text_option = QTextOption(Qt.AlignLeft | Qt.AlignVCenter)
        text_option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(text_option)
        
        # Return the calculated size plus margin space
        size = doc.size().toSize()
        size.setWidth(size.width() + 6)  # Add back margin space
        size.setHeight(size.height() + 4)  # Add vertical margin space
        return QSize(size.width(), max(size.height(), option.fontMetrics.height()))

# Cross-platform utility functions
class PlatformUtils:
    @staticmethod
    def get_music_directory():
        """Get user's music directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Music")
        elif PlatformUtils.is_macos():
            music_path = os.path.join(home, "Music")
            if not os.path.exists(music_path):
                alt_paths = [
                    os.path.join(home, "Musique"),  # French
                    os.path.join(home, "Música"),   # Spanish
                    os.path.join(home, "Music")     # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return music_path
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "MUSIC"], capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Music")

    @staticmethod
    def get_pictures_directory():
        """Get user's pictures directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Pictures")
        elif PlatformUtils.is_macos():
            pictures_path = os.path.join(home, "Pictures")
            if not os.path.exists(pictures_path):
                alt_paths = [
                    os.path.join(home, "Fotos"),    # Spanish
                    os.path.join(home, "Images"),   # French
                    os.path.join(home, "Pictures")  # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return pictures_path
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Pictures")

    @staticmethod
    def get_videos_directory():
        """Get user's videos directory"""
        home = PlatformUtils.get_home_directory()
        if PlatformUtils.is_windows():
            return os.path.join(home, "Videos")
        elif PlatformUtils.is_macos():
            videos_path = os.path.join(home, "Movies")
            if not os.path.exists(videos_path):
                alt_paths = [
                    os.path.join(home, "Videos"),   # English fallback
                    os.path.join(home, "Películas"), # Spanish
                    os.path.join(home, "Films"),    # French
                    os.path.join(home, "Movies")     # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return videos_path
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "VIDEOS"], capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Videos")
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
    def detect_system_dark_mode():
        """Detect if the system is using dark mode (macOS specific)"""
        if not PlatformUtils.is_macos():
            return False
        
        try:
            # Check macOS system appearance
            result = subprocess.run([
                'defaults', 'read', '-g', 'AppleInterfaceStyle'
            ], capture_output=True, text=True, timeout=5)
            
            # If the command succeeds and returns "Dark", system is in dark mode
            return result.returncode == 0 and 'Dark' in result.stdout.strip()
        except Exception:
            # If any error occurs, assume light mode
            return False
    
    @staticmethod
    def get_macos_accent_color():
        """Get macOS system accent color"""
        if not PlatformUtils.is_macos():
            return None
        
        try:
            result = subprocess.run([
                'defaults', 'read', '-g', 'AppleAccentColor'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                color_code = result.stdout.strip()
                # Convert macOS color codes to CSS colors
                accent_colors = {
                    '-1': '#007AFF',  # Blue (default)
                    '0': '#FF3B30',   # Red
                    '1': '#FF9500',   # Orange  
                    '2': '#FFCC00',   # Yellow
                    '3': '#34C759',   # Green
                    '4': '#007AFF',   # Blue
                    '5': '#5856D6',   # Purple
                    '6': '#FF2D92',   # Pink
                }
                return accent_colors.get(color_code, '#007AFF')
        except Exception:
            pass
        
        return '#007AFF'  # Default blue
    
    @staticmethod
    def get_navigation_modifier():
        """Get the navigation modifier key (for back/forward)"""
        return "Cmd" if PlatformUtils.is_macos() else "Alt"
    
    @staticmethod
    def setup_macos_window_behavior(window):
        """Setup macOS-specific window behavior"""
        if not PlatformUtils.is_macos():
            return
        
        try:
            # Enable window restoration
            window.setProperty("NSWindowRestorationFrameAutosaveName", "MainWindow")
            
            # Set proper window flags for macOS
            window.setWindowFlags(window.windowFlags() | Qt.WindowFullscreenButtonHint)
            
            # Enable native macOS title bar behavior if possible
            try:
                from PyQt5.QtMacExtras import QMacToolBar
                # This would require QtMacExtras, which might not be available
                # So we'll just continue without it
            except ImportError:
                pass
                
        except Exception as e:
            pass
    
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
                # Use AppleScript to open Terminal with better error handling and options
                try:
                    # Try modern Terminal.app AppleScript first
                    script = f'''
                    tell application "Terminal"
                        activate
                        do script "cd {shlex.quote(path)}"
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], check=True)
                except Exception as terminal_error:
                    try:
                        # Fallback to iTerm2 if available
                        iterm_script = f'''
                        tell application "iTerm"
                            create window with default profile
                            tell current session of current window
                                write text "cd {shlex.quote(path)}"
                            end tell
                        end tell
                        '''
                        subprocess.run(["osascript", "-e", iterm_script], check=True)
                    except Exception:
                        # Final fallback to simple open command
                        subprocess.run(["open", "-a", "Terminal", path], check=True)
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
            # Try multiple macOS trash methods
            return ["osascript", "-e", "tell app \"Finder\" to delete POSIX file"]  # Built-in AppleScript method
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
            # Use macOS standard Documents folder
            docs_path = os.path.join(home, "Documents")
            # Also check for localized versions
            if not os.path.exists(docs_path):
                # Try alternative paths on macOS
                alt_paths = [
                    os.path.join(home, "Documents"),
                    os.path.join(home, "Documentos"),  # Spanish
                    os.path.join(home, "Documents")    # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return docs_path
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
            # Use macOS standard Downloads folder
            downloads_path = os.path.join(home, "Downloads")
            # Also check for localized versions
            if not os.path.exists(downloads_path):
                # Try alternative paths on macOS
                alt_paths = [
                    os.path.join(home, "Downloads"),
                    os.path.join(home, "Descargas"),   # Spanish
                    os.path.join(home, "Téléchargements"),  # French
                    os.path.join(home, "Downloads")    # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return downloads_path
        else:  # Linux
            # Try XDG user dirs first
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
            # Use macOS standard Desktop folder with localization support
            desktop_path = os.path.join(home, "Desktop")
            if not os.path.exists(desktop_path):
                # Try alternative paths on macOS for different languages
                alt_paths = [
                    os.path.join(home, "Desktop"),
                    os.path.join(home, "Escritorio"),  # Spanish
                    os.path.join(home, "Bureau"),      # French
                    os.path.join(home, "Schreibtisch"), # German
                    os.path.join(home, "Desktop")      # Fallback
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
            return desktop_path
        else:  # Linux
            try:
                result = subprocess.run(["xdg-user-dir", "DESKTOP"], 
                                      capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Desktop")
                result = subprocess.run(["xdg-user-dir", "DESKTOP"], 
                                      capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                return os.path.join(home, "Desktop")

# Performance & Memory Optimization Classes
class ThumbnailCache:
    """Persistent disk-based thumbnail cache for performance optimization with thread safety"""
    
    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), 'garysfm_thumbnails')
        self.memory_cache = OrderedDict()  # LRU cache in memory
        self.max_memory_cache = 200  # Reduced from 500 to 200 for better memory usage
        self.cleanup_started = False  # Flag to track cleanup thread
        
        # Add thread safety with lock
        import threading
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Cache metadata file
        self.metadata_file = os.path.join(self.cache_dir, 'cache_metadata.json')
        self.metadata = self._load_metadata()
        
        # Don't start cleanup thread automatically to avoid exit hanging
        # self._start_cleanup_thread()
    
    def _load_metadata(self):
        """Load cache metadata from disk"""
        try:
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_metadata(self):
        """Save cache metadata to disk"""
        try:
            # Write atomically to avoid partial writes from concurrent processes
            import tempfile
            dirp = os.path.dirname(self.metadata_file)
            fd, tmp_path = tempfile.mkstemp(dir=dirp)
            try:
                # Sanitize metadata into JSON-serializable structures (string keys, simple values)
                def _sanitize(obj):
                    # Primitive types allowed as-is
                    if obj is None or isinstance(obj, (str, int, float, bool)):
                        return obj
                    if isinstance(obj, dict):
                        out = {}
                        # Iterate over a snapshot of items to avoid runtime errors if dict is mutated concurrently
                        for k, v in list(obj.items()):
                            try:
                                ks = str(k)
                            except Exception:
                                ks = repr(k)
                            out[ks] = _sanitize(v)
                        return out
                    if isinstance(obj, (list, tuple, set)):
                        return [_sanitize(i) for i in obj]
                    # Fallback: try to JSON-encode, otherwise use repr()
                    try:
                        json.dumps(obj)
                        return obj
                    except Exception:
                        return repr(obj)

                # Copy metadata under lock to get a stable snapshot for serialization
                try:
                    with getattr(self, '_lock'):
                        meta_snapshot = dict(self.metadata)
                except Exception:
                    # Fallback if lock not present or copying fails
                    try:
                        meta_snapshot = dict(self.metadata)
                    except Exception:
                        meta_snapshot = {}

                safe_meta = _sanitize(meta_snapshot)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(safe_meta, f, ensure_ascii=False, indent=2)
                # Atomic replace - try os.replace, but fall back to shutil.move or copy on failure
                try:
                    os.replace(tmp_path, self.metadata_file)
                except Exception:
                    logging.getLogger(__name__).warning('atomic replace failed for %s -> %s, attempting fallback', tmp_path, self.metadata_file)
                    try:
                        import shutil
                        shutil.move(tmp_path, self.metadata_file)
                    except Exception:
                        logging.getLogger(__name__).warning('shutil.move fallback failed, attempting file copy', exc_info=True)
                        try:
                            # Last-resort: copy file contents into target path
                            with open(tmp_path, 'rb') as src, open(self.metadata_file, 'wb') as dst:
                                data = src.read()
                                dst.write(data)
                                try:
                                    dst.flush()
                                    os.fsync(dst.fileno())
                                except Exception:
                                    pass
                        except Exception:
                            logging.getLogger(__name__).exception('Failed to persist metadata via any fallback')
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
        except Exception:
            logging.getLogger(__name__).exception('Failed to save thumbnail cache metadata')
    
    def _start_cleanup_thread(self):
        """Start background thread to clean old cache files"""
        def cleanup_old_files():
            try:
                cutoff_time = time.time() - (7 * 24 * 3600)  # 7 days ago
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.thumb'):
                        filepath = os.path.join(self.cache_dir, filename)
                        if os.path.getmtime(filepath) < cutoff_time:
                            os.remove(filepath)
                            # Remove from metadata
                            key = filename[:-6]  # Remove .thumb extension
                            if key in self.metadata:
                                del self.metadata[key]
                self._save_metadata()
            except Exception:
                pass  # Fail silently for cleanup
        
        cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
        cleanup_thread.start()
    
    def get_cache_key(self, file_path, size):
        """Generate cache key for file path and size"""
        path_hash = hashlib.md5(file_path.encode('utf-8')).hexdigest()
        return f"{path_hash}_{size}"
    
    def get(self, file_path, size):
        logging.getLogger('thumbnail').debug("get: %s size=%s", file_path, size)
        """Get cached thumbnail as PNG bytes and reconstruct QPixmap"""
        cache_key = self.get_cache_key(file_path, size)
        logging.getLogger('thumbnail').debug("get_cache_key: %s", cache_key)
        with self._lock:
            if cache_key in self.memory_cache:
                logging.getLogger('thumbnail').debug('Memory cache hit for %s', cache_key)
                self.memory_cache.move_to_end(cache_key)
                png_bytes = self.memory_cache[cache_key]
                return self._pixmap_from_png_bytes(png_bytes)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.thumb")
        logging.getLogger('thumbnail').debug('cache_file: %s', cache_file)
        if os.path.exists(cache_file):
            logging.getLogger('thumbnail').debug('Disk cache hit for %s', cache_file)
            try:
                # Guard file_mtime lookup: file_path may not exist locally (remote/iso)
                file_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
                with self._lock:
                    cache_meta = self.metadata.get(cache_key, {})
                cache_mtime = cache_meta.get('mtime', 0)
                logging.getLogger('thumbnail').debug('file_mtime=%s, cache_mtime=%s for %s', file_mtime, cache_mtime, file_path)
                if not cache_meta:
                    logging.getLogger('thumbnail').debug('No metadata for %s (file: %s)', cache_key, file_path)
                if file_mtime <= cache_mtime:
                    logging.getLogger('thumbnail').debug('Cache is valid for %s', file_path)
                    try:
                        with open(cache_file, 'rb') as f:
                            png_bytes = f.read()
                        logging.getLogger('thumbnail').debug('Read %d bytes from cache file for %s', len(png_bytes), file_path)
                        self._add_to_memory_cache(cache_key, png_bytes)
                        return self._pixmap_from_png_bytes(png_bytes)
                    except Exception as e:
                        logging.getLogger('thumbnail').exception('Exception reading cache file for %s: %s', file_path, e)
                else:
                    logging.getLogger('thumbnail').debug('Cache is stale for %s', file_path)
            except Exception as e:
                logging.getLogger('thumbnail').exception('Exception in get() for %s: %s', file_path, e)
        else:
            logging.getLogger('thumbnail').debug('No cache file found for %s', file_path)
        return None

    def is_cached(self, file_path, size):
        """Quick check whether a thumbnail exists and is up-to-date for file_path at size.
        This is a fast, read-only check that avoids loading the thumbnail bytes.
        Returns True if cached and fresh, False otherwise.
        """
        try:
            cache_key = self.get_cache_key(file_path, size)
            with self._lock:
                if cache_key in self.memory_cache:
                    return True
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.thumb")
            if not os.path.exists(cache_file):
                return False
            try:
                file_mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
                with self._lock:
                    cache_meta = self.metadata.get(cache_key, {})
                cache_mtime = cache_meta.get('mtime', 0)
                return file_mtime <= cache_mtime
            except Exception:
                return False
        except Exception:
            return False

    def _pixmap_from_png_bytes(self, png_bytes):
        from PyQt5.QtCore import QByteArray
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(png_bytes), 'PNG')
        return pixmap
    
    def put(self, file_path, size, thumbnail_data):
        logging.getLogger('thumbnail').debug('put: %s size=%s', file_path, size)
        """Store thumbnail as PNG bytes in cache with thread safety"""
        from PyQt5.QtCore import QBuffer, QByteArray
        cache_key = self.get_cache_key(file_path, size)
        logging.getLogger('thumbnail').debug('put_cache_key: %s', cache_key)
        # Accept either QPixmap or PNG bytes
        if isinstance(thumbnail_data, QPixmap):
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            thumbnail_data.save(buffer, 'PNG')
            png_bytes = buffer.data().data()
            buffer.close()
        elif isinstance(thumbnail_data, (bytes, bytearray)):
            png_bytes = bytes(thumbnail_data)
        else:
            logging.getLogger('thumbnail').warning('Unsupported thumbnail_data type: %s', type(thumbnail_data))
            return
        logging.getLogger('thumbnail').debug('Writing %d bytes to cache for %s size=%s', len(png_bytes), file_path, size)
        self._add_to_memory_cache(cache_key, png_bytes)
        try:
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.thumb")
            with open(cache_file, 'wb') as f:
                f.write(png_bytes)
            with self._lock:
                self.metadata[cache_key] = {
                    'mtime': os.path.getmtime(file_path),
                    'created': time.time()
                }
            self._save_metadata()
        except Exception:
            pass
    
    def _add_to_memory_cache(self, key, value):
        """Add item to memory cache with LRU eviction and thread safety"""
        with self._lock:  # Thread-safe access to cache
            if key in self.memory_cache:
                self.memory_cache.move_to_end(key)
            else:
                self.memory_cache[key] = value
                # Remove oldest items if cache is full
                while len(self.memory_cache) > self.max_memory_cache:
                    self.memory_cache.popitem(last=False)
    
    def clear_memory_cache(self):
        """Clear the in-memory cache with thread safety"""
        with self._lock:
            self.memory_cache.clear()
    
    def cleanup(self):
        """Clean up cache resources and memory"""
        try:
            self.memory_cache.clear()
            import gc
            gc.collect()
        except Exception:
            pass

class VirtualFileLoader:
    """Virtual file loader for large directories with lazy loading"""
    
    def __init__(self, chunk_size=100):
        self.chunk_size = chunk_size
        self.loaded_chunks = {}
        self.total_items = 0
        self.directory_cache = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="FileLoader")
    
    def load_directory_async(self, directory_path, callback, sort_func=None):
        """Load directory contents asynchronously in chunks"""
        def load_worker():
            try:
                if not os.path.exists(directory_path):
                    callback([], True)  # Empty list, done
                    return

                # Get all items
                try:
                    # Clear caches first
                    if hasattr(self, 'loaded_chunks'):
                        self.loaded_chunks.clear()
                    if hasattr(self, 'directory_cache'):
                        self.directory_cache.clear()
                    # Shutdown executor with timeout
                    if hasattr(self, 'executor') and self.executor:
                        try:
                            # Cancel all pending futures
                            self.executor.shutdown(wait=False)
                            import time
                            time.sleep(0.1)
                        except Exception as e:
                            print(f"Error shutting down executor: {e}")
                            try:
                                self.executor.shutdown(wait=False)
                            except:
                                pass
                except Exception as e:
                    print(f"Error during VirtualFileLoader cleanup: {e}")

                # Build the items list (was missing, causing 'items' undefined errors)
                try:
                    import time
                    # Include full paths for items for consistency with other loaders
                    items = [os.path.join(directory_path, name) for name in os.listdir(directory_path)]
                    if sort_func:
                        try:
                            items = sorted(items, key=sort_func)
                        except Exception:
                            items = sorted(items)
                    else:
                        items = sorted(items)
                except Exception as e:
                    print(f"[VirtualFileLoader] Failed to list directory {directory_path}: {e}")
                    callback([], True)
                    return

                # Send items in chunks
                for i in range(0, len(items), self.chunk_size):
                    chunk = items[i:i + self.chunk_size]
                    chunk_index = i // self.chunk_size
                    self.loaded_chunks[chunk_index] = chunk

                    # Call callback with chunk and completion status
                    is_complete = (i + self.chunk_size) >= len(items)
                    callback(chunk, is_complete)

                    # Small delay to prevent UI blocking
                    time.sleep(0.001)

            except Exception as e:
                callback([], True)  # Error occurred, return empty
        
        future = self.executor.submit(load_worker)
        return future
    
    def get_chunk(self, chunk_index):
        """Get a specific chunk by index"""
        return self.loaded_chunks.get(chunk_index, [])
    
    def cleanup(self):
        """Clean up resources with improved shutdown handling"""
        try:
            # ...removed debug print...
            
            # Clear caches first
            if hasattr(self, 'loaded_chunks'):
                self.loaded_chunks.clear()
            if hasattr(self, 'directory_cache'):
                self.directory_cache.clear()
            
            # Shutdown executor with timeout
            if hasattr(self, 'executor') and self.executor:
                try:
                    # ...removed debug print...
                    # Cancel all pending futures
                    self.executor.shutdown(wait=False)
                    
                    # Give it a moment to shut down gracefully
                    import time
                    time.sleep(0.1)
                    
                    # ...removed debug print...
                except Exception as e:
                    print(f"Error shutting down executor: {e}")
                    # Force shutdown if graceful fails
                    try:
                        self.executor.shutdown(wait=False)
                    except:
                        pass
                        
            # ...removed debug print...
            
        except Exception as e:
            print(f"Error during VirtualFileLoader cleanup: {e}")

class MemoryManager:
    """Memory usage optimization and automatic garbage collection"""
    def add_cleanup_callback(self, callback):
        """Register a callback to be called during memory cleanup."""
        self.cleanup_callbacks.append(callback)
    
    def __init__(self, check_interval=30):
        self.check_interval = check_interval
        self.last_cleanup = time.time()
        self.memory_threshold = 150 * 1024 * 1024  # Reduced from 200MB to 150MB for more aggressive cleanup
        self.cleanup_callbacks = []
        self.running = True  # Add running flag for clean shutdown
        self.monitor_thread = None  # Keep reference to thread
        
        # Start memory monitoring thread
        self._start_monitoring_thread()
    
    def _start_monitoring_thread(self):
        """Start background memory monitoring with leak detection"""
        def monitor_memory():
            while self.running:  # Check running flag instead of infinite loop
                try:
                    import psutil
                    process = psutil.Process()
                    memory_usage = process.memory_info().rss
                    memory_mb = memory_usage / 1024 / 1024
                    
                    # Check for memory threshold breach
                    if memory_usage > self.memory_threshold:
                        # ...removed debug print...
                        self.force_cleanup()
                    
                    # Regular cleanup every interval
                    if time.time() - self.last_cleanup > self.check_interval:
                        # ...removed debug print...
                        self.routine_cleanup()
                    
                    # Check for memory leaks (increasing memory without cleanup)
                    if not hasattr(self, '_last_memory_check'):
                        self._last_memory_check = memory_usage
                        self._memory_growth_counter = 0
                    else:
                        memory_growth = memory_usage - self._last_memory_check
                        if memory_growth > 50 * 1024 * 1024:  # 50MB growth
                            self._memory_growth_counter += 1
                            # ...removed debug print...
                            if self._memory_growth_counter >= 3:  # 3 consecutive growths
                                # ...removed debug print...
                                self.force_cleanup()
                                self._memory_growth_counter = 0
                        else:
                            self._memory_growth_counter = 0
                        
                        self._last_memory_check = memory_usage
                        
                    time.sleep(min(self.check_interval, 5))  # Check at least every 5 seconds
                    
                except ImportError:
                    # psutil not available, do basic cleanup periodically
                    if self.running:  # Check running flag
                        time.sleep(min(self.check_interval, 5))
                        if time.time() - self.last_cleanup > self.check_interval:
                            self.routine_cleanup()
                except Exception as e:
                    print(f"Error in memory monitoring: {e}")
                    if self.running:  # Check running flag
                        time.sleep(min(self.check_interval, 5))
        
        self.monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        def monitor_memory():
            while self.running:  # Check running flag instead of infinite loop
                try:
                    import psutil
                    process = psutil.Process()
                    memory_usage = process.memory_info().rss
                    # Check for memory threshold breach
                    if memory_usage > self.memory_threshold:
                        self.force_cleanup()
                    # Regular cleanup every interval
                    if time.time() - self.last_cleanup > self.check_interval:
                        self.routine_cleanup()
                    # Check for memory leaks (increasing memory without cleanup)
                    if not hasattr(self, '_last_memory_check'):
                        self._last_memory_check = memory_usage
                        self._memory_growth_counter = 0
                    else:
                        memory_growth = memory_usage - self._last_memory_check
                        if memory_growth > 50 * 1024 * 1024:  # 50MB growth
                            self._memory_growth_counter += 1
                            if self._memory_growth_counter >= 3:  # 3 consecutive growths
                                self.force_cleanup()
                                self._memory_growth_counter = 0
                        else:
                            self._memory_growth_counter = 0
                        self._last_memory_check = memory_usage
                    time.sleep(min(self.check_interval, 5))  # Check at least every 5 seconds
                except ImportError:
                    # psutil not available, do basic cleanup periodically
                    if self.running:  # Check running flag
                        time.sleep(min(self.check_interval, 5))
                        if time.time() - self.last_cleanup > self.check_interval:
                            self.routine_cleanup()
                except Exception as e:
                    print(f"Error in memory monitoring: {e}")
                    if self.running:  # Check running flag
                        time.sleep(min(self.check_interval, 5))
            self.last_cleanup = time.time()
    
    def force_cleanup(self):
        """Force aggressive memory cleanup with detailed reporting"""
        try:
            # ...removed debug print...
            
            # Memory usage before cleanup
            try:
                import psutil
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024  # MB
                # ...removed debug print...
            except ImportError:
                memory_before = 0
            
            # More aggressive cleanup
            for callback in self.cleanup_callbacks:
                try:
                    callback(aggressive=True)
                except Exception as e:
                    print(f"Aggressive cleanup callback error: {e}")
            
            # Multiple garbage collection passes with detailed reporting
            import gc
            total_collected = 0
            for i in range(3):
                collected = gc.collect()
                total_collected += collected
                print(f"GC pass {i+1}: collected {collected} objects")
                
                # Check for remaining garbage
                if gc.garbage:
                    print(f"Warning: {len(gc.garbage)} objects still in gc.garbage after pass {i+1}")
            
            # Final memory report
            try:
                if memory_before > 0:
                    memory_after = process.memory_info().rss / 1024 / 1024  # MB
                    memory_freed = memory_before - memory_after
                    print(f"Memory after aggressive cleanup: {memory_after:.1f} MB")
                    print(f"Total memory freed: {memory_freed:.1f} MB")
                    print(f"Total objects collected: {total_collected}")
            except:
                pass
            
            self.last_cleanup = time.time()
        except Exception as e:
            print(f"Error in aggressive cleanup: {e}")
    
    def cleanup(self):
        """Clean up memory manager and stop background thread - PLATFORM AWARE"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            # Platform-specific timeout handling
            import platform
            platform_name = platform.system().lower()
            
            if platform_name == 'darwin':  # macOS
                # macOS handles threads more gracefully, allow slightly more time
                self.monitor_thread.join(timeout=0.2)
            elif platform_name == 'windows':  # Windows
                # Windows needs immediate termination
                self.monitor_thread.join(timeout=0.05)
            else:  # Linux and others
                # Standard timeout for Linux
                self.monitor_thread.join(timeout=0.1)
            
            # Force daemon thread termination - don't wait beyond timeout

class BackgroundFileMonitor:
    """Background file system monitoring for automatic updates with thread safety.

    This implementation polls monitored directories for modification time changes,
    coalesces rapid events with a debounce window, and marshals callbacks to the
    Qt main thread using GuiInvoker.instance().invoke signal.
    """

    def __init__(self):
        # Core state
        self.monitored_directories = set()
        self.callbacks = defaultdict(list)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="FileMonitor")
        self.running = True

        # Thread-safety
        import threading
        self._lock = threading.RLock()

        # Debounce configuration: coalesce rapid modification events per-directory
        self._debounce_seconds = 0.5
        self._pending_events = {}  # directory -> last event timestamp

        # Drive change detection
        self._last_drives = set()
        self._drive_callbacks = []

        # Start monitoring thread
        self._start_monitoring()

    def _start_monitoring(self):
        """Start background file monitoring worker (runs in executor)."""

        def monitor_worker():
            directory_mtimes = {}
            while self.running:
                try:
                    now = time.time()

                    # Check monitored directories for mtime changes
                    for directory in list(self.monitored_directories):
                        if not os.path.exists(directory):
                            # If directory removed, stop monitoring it
                            try:
                                self.remove_directory(directory)
                            except Exception:
                                pass
                            continue

                        try:
                            current_mtime = os.path.getmtime(directory)
                            last_mtime = directory_mtimes.get(directory, 0)

                            if current_mtime > last_mtime:
                                # Update last seen mtime and note a pending event time
                                directory_mtimes[directory] = current_mtime
                                self._pending_events[directory] = now

                        except (OSError, PermissionError):
                            pass

                    # Check pending events and invoke callbacks only after debounce window
                    to_invoke = []
                    for d, ts in list(self._pending_events.items()):
                        if time.time() >= ts + getattr(self, '_debounce_seconds', 0.5):
                            to_invoke.append(d)

                    for d in to_invoke:
                        try:
                            for callback in list(self.callbacks.get(d, [])):
                                try:
                                    # Use GuiInvoker to marshal the callback to the main thread
                                    try:
                                        GuiInvoker.instance().invoke.emit(lambda dd=d, cb=callback: cb(dd))
                                    except Exception:
                                        callback(d)
                                except Exception:
                                    pass
                        finally:
                            # Remove pending event after invocation
                            try:
                                del self._pending_events[d]
                            except Exception:
                                pass

                    # Check for system drive changes (added/removed drives)
                    try:
                        drives = set()
                        try:
                            if os.name == 'nt':
                                import string, ctypes
                                bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
                                for i in range(26):
                                    if bitmask & (1 << i):
                                        drives.add(f"{string.ascii_uppercase[i]}:/")
                            else:
                                drives.add(os.path.abspath(os.sep))
                        except Exception:
                            drives.add(os.path.abspath(os.sep))

                        if drives != getattr(self, '_last_drives', set()):
                            self._last_drives = drives
                            # Notify drive callbacks on GUI thread
                            for cb in list(self._drive_callbacks):
                                try:
                                    try:
                                        GuiInvoker.instance().invoke.emit(lambda ds=drives, c=cb: c(ds))
                                    except Exception:
                                        cb(drives)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    time.sleep(0.25)  # Check frequently to keep debounce responsive
                except Exception:
                    time.sleep(0.5)

        # Submit the worker to the executor
        try:
            self.executor.submit(monitor_worker)
        except Exception:
            # If executor submission fails, ensure running flag is False
            self.running = False

    def add_directory(self, directory_path, callback):
        """Add directory to monitor with callback (thread-safe)."""
        with self._lock:
            self.monitored_directories.add(directory_path)
            self.callbacks[directory_path].append(callback)

    def remove_directory(self, directory_path):
        """Remove directory from monitoring (thread-safe)."""
        with self._lock:
            self.monitored_directories.discard(directory_path)
            if directory_path in self.callbacks:
                del self.callbacks[directory_path]

    def cleanup(self):
        """Clean up resources - PLATFORM AWARE"""
        self.running = False

        import platform
        platform_name = platform.system().lower()

        try:
            if platform_name == 'darwin':  # macOS
                # macOS can handle a brief wait for graceful shutdown
                try:
                    self.executor.shutdown(wait=True, timeout=0.1)
                except TypeError:
                    # Older Python versions don't support timeout arg
                    self.executor.shutdown(wait=True)
            elif platform_name == 'windows':  # Windows
                # Windows needs immediate shutdown
                self.executor.shutdown(wait=False)
            else:  # Linux and others
                # Standard immediate shutdown
                self.executor.shutdown(wait=False)
        except Exception:
            # Fallback for any platform
            try:
                self.executor.shutdown(wait=False)
            except Exception:
                pass

        self.monitored_directories.clear()
        self.callbacks.clear()

    def add_drive_callback(self, callback):
        """Register a callback to be invoked when system drives change.

        Callback will be called with the new set of drives.
        """
        with self._lock:
            if callback not in self._drive_callbacks:
                self._drive_callbacks.append(callback)

    def remove_drive_callback(self, callback):
        with self._lock:
            try:
                if callback in self._drive_callbacks:
                    self._drive_callbacks.remove(callback)
            except Exception:
                pass

# Advanced Search and Filtering Classes
class SearchEngine:
    """Advanced file search engine with multiple criteria and content search"""
    
    def __init__(self):
        self.search_index = {}  # Cache for metadata searches
        self.content_cache = {}  # Cache for content searches
        self.search_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Search")
        self.indexing_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Indexer")
        
        # Search filters
        self.filters = {
            'name': self._filter_by_name,
            'size': self._filter_by_size,
            'date_modified': self._filter_by_date_modified,
            'date_created': self._filter_by_date_created,
            'type': self._filter_by_type,
            'content': self._search_content,
            'extension': self._filter_by_extension,
            'permissions': self._filter_by_permissions
        }
        
        # File type categories
        self.file_types = {
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'],
            'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
            'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
            'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx'],
            'code': ['.py', '.js', '.html', '.css', '.cpp', '.c', '.java', '.php', '.rb', '.go'],
            'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
            'executable': ['.exe', '.msi', '.app', '.deb', '.rpm', '.dmg']
        }
        
        # Content search supported types
        self.text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml', 
                               '.md', '.rst', '.ini', '.cfg', '.conf', '.log', '.sql', '.csv'}
    
    def search_files_async(self, directory, query, filters=None, callback=None):
        """Asynchronous file search with progress callbacks"""
        future = self.search_executor.submit(self._search_files_worker, directory, query, filters, callback)
        return future
    
    def _search_files_worker(self, directory, query, filters, callback):
        """Worker method for file searching"""
        try:
            results = []
            total_files = 0
            processed_files = 0
            
            # First pass: count total files for progress tracking
            for root, dirs, files in os.walk(directory):
                total_files += len(files)
            
            if callback:
                callback('progress', {'current': 0, 'total': total_files, 'status': 'Starting search...'})
            
            # Second pass: actual search
            for root, dirs, files in os.walk(directory):
                try:
                    for file in files:
                        if processed_files % 100 == 0 and callback:  # Update every 100 files
                            callback('progress', {
                                'current': processed_files, 
                                'total': total_files, 
                                'status': f'Searching: {file[:30]}...'
                            })
                        
                        file_path = os.path.join(root, file)
                        processed_files += 1
                        
                        try:
                            # Get file info
                            stat_info = os.stat(file_path)
                            file_info = {
                                'path': file_path,
                                'name': file,
                                'size': stat_info.st_size,
                                'modified': stat_info.st_mtime,
                                'created': stat_info.st_ctime,
                                'extension': os.path.splitext(file)[1].lower(),
                                'is_dir': False
                            }
                            
                            # Apply search filters
                            if self._matches_search_criteria(file_info, query, filters):
                                results.append(file_info)
                                
                                # Report incremental results
                                if callback and len(results) % 50 == 0:
                                    callback('result', file_info)
                                    
                        except (OSError, PermissionError):
                            continue  # Skip inaccessible files
                            
                except (OSError, PermissionError):
                    continue  # Skip inaccessible directories
            
            # Include directories in search if requested
            if filters and filters.get('include_directories', False):
                for root, dirs, files in os.walk(directory):
                    for dir_name in dirs:
                        try:
                            dir_path = os.path.join(root, dir_name)
                            stat_info = os.stat(dir_path)
                            dir_info = {
                                'path': dir_path,
                                'name': dir_name,
                                'size': 0,
                                'modified': stat_info.st_mtime,
                                'created': stat_info.st_ctime,
                                'extension': '',
                                'is_dir': True
                            }
                            
                            if self._matches_search_criteria(dir_info, query, filters):
                                results.append(dir_info)
                                
                        except (OSError, PermissionError):
                            continue
            
            if callback:
                callback('complete', {'results': results, 'total_processed': processed_files})
                
            return results
            
        except Exception as e:
            if callback:
                callback('error', {'message': str(e)})
            return []
    
    def _matches_search_criteria(self, file_info, query, filters):
        """Check if file matches all search criteria"""
        # Basic name query (always applied if provided)
        if query and not self._filter_by_name(file_info, query):
            return False
        
        # Apply additional filters
        if filters:
            for filter_name, filter_value in filters.items():
                if filter_name in self.filters and filter_value is not None:
                    if not self.filters[filter_name](file_info, filter_value):
                        return False
        
        return True
    
    def _filter_by_name(self, file_info, pattern):
        """Filter by filename pattern (supports wildcards)"""
        import fnmatch
        return fnmatch.fnmatch(file_info['name'].lower(), pattern.lower())
    
    def _filter_by_size(self, file_info, size_criteria):
        """Filter by file size criteria: {'min': bytes, 'max': bytes}"""
        file_size = file_info['size']
        if 'min' in size_criteria and file_size < size_criteria['min']:
            return False
        if 'max' in size_criteria and file_size > size_criteria['max']:
            return False
        return True
    
    def _filter_by_date_modified(self, file_info, date_criteria):
        """Filter by modification date: {'after': timestamp, 'before': timestamp}"""
        mod_time = file_info['modified']
        if 'after' in date_criteria and mod_time < date_criteria['after']:
            return False
        if 'before' in date_criteria and mod_time > date_criteria['before']:
            return False
        return True
    
    def _filter_by_date_created(self, file_info, date_criteria):
        """Filter by creation date: {'after': timestamp, 'before': timestamp}"""
        create_time = file_info['created']
        if 'after' in date_criteria and create_time < date_criteria['after']:
            return False
        if 'before' in date_criteria and create_time > date_criteria['before']:
            return False
        return True
    
    def _filter_by_type(self, file_info, file_type):
        """Filter by file type category"""
        if file_type in self.file_types:
            return file_info['extension'] in self.file_types[file_type]
        return False
    
    def _filter_by_extension(self, file_info, extensions):
        """Filter by specific file extensions (list)"""
        if isinstance(extensions, str):
            extensions = [extensions]
        return file_info['extension'] in [ext.lower() for ext in extensions]
    
    def _filter_by_permissions(self, file_info, permission_criteria):
        """Filter by file permissions (readable, writable, executable)"""
        try:
            path = file_info['path']
            if permission_criteria.get('readable') and not os.access(path, os.R_OK):
                return False
            if permission_criteria.get('writable') and not os.access(path, os.W_OK):
                return False
            if permission_criteria.get('executable') and not os.access(path, os.X_OK):
                return False
            return True
        except:
            return False
    
    def _search_content(self, file_info, search_term):
        """Search file content for text"""
        if file_info['is_dir']:
            return False
            
        if file_info['extension'] not in self.text_extensions:
            return False
        
        # Check cache first
        cache_key = f"{file_info['path']}:{file_info['modified']}"
        if cache_key in self.content_cache:
            return search_term.lower() in self.content_cache[cache_key].lower()
        
        try:
            with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                # Read first 1MB for content search
                content = f.read(1024 * 1024)
                self.content_cache[cache_key] = content
                return search_term.lower() in content.lower()
        except:
            return False
    
    def cleanup(self):
        """Clean up search engine resources"""
        try:
            self.search_executor.shutdown(wait=False)
            self.indexing_executor.shutdown(wait=False)
            self.search_index.clear()
            self.content_cache.clear()
        except Exception as e:
            print(f"Error cleaning up search engine: {e}")



# Background Operations Classes
class AsyncFileOperation(QObject):
    def toggle_paused(self):
        """Toggle the paused state of the operation."""
        self.paused = not self.paused
    """Enhanced asynchronous file operations with detailed progress tracking"""
    progress = pyqtSignal(int)  # Progress percentage (0-100)
    fileProgress = pyqtSignal(int, int)  # Current file, total files
    byteProgress = pyqtSignal(int, int)  # Bytes processed, total bytes
    speedUpdate = pyqtSignal(str)  # Transfer speed
    etaUpdate = pyqtSignal(str)  # Estimated time remaining
    statusChanged = pyqtSignal(str)  # Current operation status
    finished = pyqtSignal(bool, str, dict)  # Success, message, stats
    errorOccurred = pyqtSignal(str, str, str)  # File path, error message, suggested action
    
    def __init__(self, source_paths, destination_path, operation_type):
        super().__init__()
        self.source_paths = source_paths
        self.destination_path = destination_path
        self.operation_type = operation_type  # 'copy', 'move', 'delete'
        self.cancelled = False
        self.paused = False
        self.start_time = None
        self.total_bytes = 0
        self.processed_bytes = 0
        self.skip_errors = False
        self.overwrite_all = False
        self.skip_all = False
        
    def cancel(self):
        self.cancelled = True
        
    def pause(self):
        self.paused = True
        
    def resume(self):
        self.paused = False
        
    def set_error_handling(self, skip_errors=False):
        self.skip_errors = skip_errors

class AsyncFileOperationWorker(QThread):
    """Advanced worker thread for asynchronous file operations"""
    progress = pyqtSignal(int)
    fileProgress = pyqtSignal(int, int)
    byteProgress = pyqtSignal(int, int)
    speedUpdate = pyqtSignal(str)
    etaUpdate = pyqtSignal(str)
    statusChanged = pyqtSignal(str)
    finished = pyqtSignal(bool, str, dict)
    error = pyqtSignal(str)  # Simplified error signal for compatibility
    errorOccurred = pyqtSignal(str, str, str)
    confirmationNeeded = pyqtSignal(str, str, str)  # Title, message, file path
    
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.buffer_size = 64 * 1024  # 64KB buffer for copying
        self.update_interval = 0.5  # Update progress every 500ms
        self.last_update_time = 0
        self.last_processed_bytes = 0
        
    def run(self):
        """Main execution thread"""
        try:
            self.operation.start_time = time.time()
            
            # Calculate total size for accurate progress
            if self.operation.operation_type in ['copy', 'move']:
                self.operation.total_bytes = self._calculate_total_size()
                
            if self.operation.operation_type == 'copy':
                self._async_copy_files()
            elif self.operation.operation_type == 'move':
                self._async_move_files()
            elif self.operation.operation_type == 'delete':
                self._async_delete_files()
            
            # Always emit finished signal, whether cancelled or completed
            if self.operation.cancelled:
                self.finished.emit(False, "Operation cancelled by user", {})
            else:
                # Calculate final statistics
                elapsed_time = time.time() - self.operation.start_time
                stats = {
                    'elapsed_time': elapsed_time,
                    'total_bytes': self.operation.total_bytes,
                    'average_speed': self.operation.total_bytes / elapsed_time if elapsed_time > 0 else 0,
                    'files_processed': len(self.operation.source_paths)
                }
                self.finished.emit(True, "Operation completed successfully", stats)
        except Exception as e:
            self.finished.emit(False, str(e), {})
    
    def _calculate_total_size(self):
        """Calculate total size of all files to be processed"""
        total_size = 0
        processed_paths = 0
        total_paths = len(self.operation.source_paths)
        
        # Emit initial status
        self.statusChanged.emit("Calculating total size...")
        
        for source_path in self.operation.source_paths:
            if self.operation.cancelled:
                return total_size
                
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
                futures = []
                for file_path in files:
                    futures.append(executor.submit(cache_one_file, file_path))
                def shutdown_executor():
                    import concurrent.futures as cf
                    try:
                        thumbnail_info("Waiting for {} thumbnail tasks to finish...", len(futures))
                        cf.wait(futures, timeout=60)
                        thumbnail_info("Thumbnail generation complete.")
                    except Exception as e:
                        thumbnail_error("Exception during thumbnail wait: {}", e)
                    executor.shutdown(wait=True)
                    # Force UI refresh after thumbnail generation
                    try:
                        from PyQt5.QtWidgets import QApplication
                        app = QApplication.instance()
                        if app:
                            thumbnail_info("Forcing UI refresh after thumbnail generation")
                            app.processEvents()
                    except Exception as e:
                        thumbnail_error("UI refresh error: {}", e)
                import threading
                threading.Thread(target=shutdown_executor, daemon=True).start()
            processed_paths += 1
            try:
                if os.path.isfile(source_path):
                    total_size += os.path.getsize(source_path)
                elif os.path.isdir(source_path):
                    # Emit progress while calculating
                    self.statusChanged.emit(f"Scanning: {os.path.basename(source_path)}...")
                    dir_size = 0
                    file_count = 0
                    
                    for root, dirs, files in os.walk(source_path):
                        if self.operation.cancelled:
                            return total_size
                            
                        for file in files:
                            if self.operation.cancelled:
                                return total_size
                                
                            try:
                                file_path = os.path.join(root, file)
                                file_size = os.path.getsize(file_path)
                                dir_size += file_size
                                file_count += 1
                                
                                # Update progress every 100 files to avoid UI spam
                                if file_count % 100 == 0:
                                    self.statusChanged.emit(f"Scanned {file_count} files in {os.path.basename(source_path)}...")
                                    
                            except (OSError, IOError):
                                continue  # Skip inaccessible files
                                
                    total_size += dir_size
                    
                # Update overall scanning progress
                scan_progress = int((processed_paths / total_paths) * 100)
                self.progress.emit(min(scan_progress, 99))  # Don't show 100% during scanning
                
            except (OSError, IOError):
                continue  # Skip inaccessible paths
                
        self.statusChanged.emit("Starting file operation...")
        return total_size
    
    def _async_copy_files(self):
        """Asynchronous file copying with detailed progress"""
        total_files = len(self.operation.source_paths)
        
        for file_index, source_path in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return
                
            # Wait if paused
            while self.operation.paused and not self.operation.cancelled:
                QThread.msleep(100)
            
            self.fileProgress.emit(file_index + 1, total_files)
            filename = os.path.basename(source_path)
            self.statusChanged.emit(f"Copying: {filename}")
            
            try:
                if os.path.isdir(source_path):
                    self._async_copy_directory(source_path, self.operation.destination_path)
                else:
                    dest_path = os.path.join(self.operation.destination_path, filename)
                    self._async_copy_file(source_path, dest_path)
            except Exception as e:
                if not self.operation.skip_errors:
                    self.errorOccurred.emit(source_path, str(e), "skip_retry_abort")
                    self.error.emit(f"Error copying {filename}: {str(e)}")
                    # Wait for user decision or continue if skip_errors is True
                
            self._update_progress()
    
    def _async_copy_file(self, source_path, dest_path):
        """Copy a single file with progress tracking"""
        file_size = os.path.getsize(source_path)
        copied_bytes = 0
        # Handle file conflicts: auto-rename with (copy) if exists
        dest_path = get_nonconflicting_name(dest_path)
        try:
            with open(source_path, 'rb') as src, open(dest_path, 'wb') as dst:
                while copied_bytes < file_size:
                    if self.operation.cancelled:
                        # Clean up partial file on cancellation
                        try:
                            dst.close()
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                        except:
                            pass
                        return
                    # Wait if paused
                    while self.operation.paused and not self.operation.cancelled:
                        QThread.msleep(100)
                    # Read chunk
                    chunk_size = min(self.buffer_size, file_size - copied_bytes)
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied_bytes += len(chunk)
                    self.operation.processed_bytes += len(chunk)
                    # Update progress periodically
                    if time.time() - self.last_update_time > self.update_interval:
                        self._update_progress()
            # Preserve file attributes
            try:
                shutil.copystat(source_path, dest_path)
            except (OSError, IOError):
                pass  # Not critical if we can't copy attributes
        except Exception as e:
            # Clean up partial file on error
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except:
                    pass
            raise e
    
    def _async_copy_directory(self, source_dir, dest_base):
        """Recursively copy directory structure"""
        dir_name = os.path.basename(source_dir)
        dest_dir = os.path.join(dest_base, dir_name)
        # Auto-rename destination directory if exists
        dest_dir = get_nonconflicting_name(dest_dir)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        
        # Copy all files and subdirectories
        for root, dirs, files in os.walk(source_dir):
            if self.operation.cancelled:
                return
                
            # Calculate relative path
            rel_path = os.path.relpath(root, source_dir)
            if rel_path == '.':
                target_dir = dest_dir
            else:
                target_dir = os.path.join(dest_dir, rel_path)
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
            
            # Copy files in current directory
            for file in files:
                if self.operation.cancelled:
                    return
                    
                source_file = os.path.join(root, file)
                dest_file = os.path.join(target_dir, file)
                
                try:
                    self._async_copy_file(source_file, dest_file)
                except Exception as e:
                    if not self.operation.skip_errors:
                        self.errorOccurred.emit(source_file, str(e), "skip_retry_abort")
    
    def _async_move_files(self):
        """Move files.

        Prefer an atomic/fast filesystem rename (os.replace) when possible
        (same filesystem). If that fails (cross-device link / EXDEV), fall
        back to copy+delete behavior for that specific item.
        """
        import errno

        total_files = len(self.operation.source_paths)

        for file_index, source_path in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return

            # Wait if paused
            while self.operation.paused and not self.operation.cancelled:
                QThread.msleep(100)

            self.fileProgress.emit(file_index + 1, total_files)
            filename = os.path.basename(source_path)
            self.statusChanged.emit(f"Moving: {filename}")

            try:
                # Determine final destination path
                dest_path = os.path.join(self.operation.destination_path, filename)
                dest_path = get_nonconflicting_name(dest_path)

                # Compute source size before any move/delete so we can track progress
                def _get_path_size(p):
                    if os.path.isfile(p):
                        try:
                            return os.path.getsize(p)
                        except Exception:
                            return 0
                    size = 0
                    for root, dirs, files in os.walk(p):
                        for f in files:
                            try:
                                size += os.path.getsize(os.path.join(root, f))
                            except Exception:
                                continue
                    return size

                src_size = _get_path_size(source_path)

                try:
                    # Try an atomic/fast move first
                    print(f"[MOVE-DEBUG] Attempting fast move (os.replace): {source_path} -> {dest_path}")
                    os.replace(source_path, dest_path)
                    # Update processed bytes and progress
                    self.operation.processed_bytes += src_size
                    self._update_progress()
                    print(f"[MOVE-DEBUG] Fast move succeeded: {dest_path}")

                except OSError as e:
                    # If cross-device link (EXDEV) or other issue, fall back to copy+delete
                    if getattr(e, 'errno', None) == errno.EXDEV:
                        print(f"[MOVE-DEBUG] EXDEV encountered, falling back to copy+delete for: {source_path}")
                        # Cross-device; perform per-item copy then delete
                        if os.path.isdir(source_path):
                            self._async_copy_directory(source_path, self.operation.destination_path)
                            # After copy, remove source directory
                            try:
                                shutil.rmtree(source_path)
                            except Exception as de:
                                if not self.operation.skip_errors:
                                    self.errorOccurred.emit(source_path, str(de), 'skip_retry_abort')
                        else:
                            dest_file = os.path.join(self.operation.destination_path, filename)
                            dest_file = get_nonconflicting_name(dest_file)
                            self._async_copy_file(source_path, dest_file)
                            try:
                                os.remove(source_path)
                            except Exception as de:
                                if not self.operation.skip_errors:
                                    self.errorOccurred.emit(source_path, str(de), 'skip_retry_abort')
                        print(f"[MOVE-DEBUG] Fallback copy+delete completed for: {source_path}")
                        # After fallback copy/delete, ensure progress updated (copy routines update bytes)
                    else:
                        print(f"[MOVE-DEBUG] OSError during os.replace for {source_path}: {e}")
                        # Unknown OSError; re-raise so caller can handle
                        raise

            except Exception as e:
                if not self.operation.skip_errors:
                    self.errorOccurred.emit(source_path, str(e), 'skip_retry_abort')
                    self.error.emit(f"Error moving {filename}: {str(e)}")

            # Update overall progress at end of item
            self._update_progress()
    
    def _async_delete_files(self):
        """Delete files with progress tracking"""
        total_files = len(self.operation.source_paths)
        
        for file_index, source_path in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return
                
            while self.operation.paused and not self.operation.cancelled:
                QThread.msleep(100)
            
            self.fileProgress.emit(file_index + 1, total_files)
            filename = os.path.basename(source_path)
            self.statusChanged.emit(f"Deleting: {filename}")
            
            try:
                if os.path.isdir(source_path):
                    shutil.rmtree(source_path)
                else:
                    os.remove(source_path)
            except Exception as e:
                if not self.operation.skip_errors:
                    self.errorOccurred.emit(source_path, str(e), "skip_retry_abort")
            
            # Update progress
            progress = int((file_index + 1) / total_files * 100)
            self.progress.emit(progress)
    
    def _update_progress(self):
        """Update progress indicators with speed and ETA calculations"""
        current_time = time.time()
        self.last_update_time = current_time
        
        if self.operation.total_bytes > 0:
            # Calculate overall progress
            progress = int((self.operation.processed_bytes / self.operation.total_bytes) * 100)
            self.progress.emit(progress)
            self.byteProgress.emit(self.operation.processed_bytes, self.operation.total_bytes)
            
            # Calculate speed
            elapsed = current_time - self.operation.start_time
            if elapsed > 0:
                bytes_per_second = self.operation.processed_bytes / elapsed
                speed_str = self._format_bytes_per_second(bytes_per_second)
                self.speedUpdate.emit(speed_str)
                
                # Calculate ETA
                if bytes_per_second > 0:
                    remaining_bytes = self.operation.total_bytes - self.operation.processed_bytes
                    eta_seconds = remaining_bytes / bytes_per_second
                    eta_str = self._format_time_duration(eta_seconds)
                    self.etaUpdate.emit(eta_str)
    
    def _format_bytes_per_second(self, bytes_per_second):
        """Format transfer speed in human readable format"""
        units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
        size = bytes_per_second
        for unit in units:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB/s"
    
    def _format_time_duration(self, seconds):
        """Format time duration in human readable format"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"

class EnhancedProgressDialog(QDialog):
    def cancel_operation(self):
        """Cancel the current file operation and update the UI."""
        if self.operation:
            self.operation.cancel()
            self.status_label.setText("Cancelling...")
            self.cancel_button.setEnabled(False)
    def toggle_pause(self):
        """Toggle pause/resume for the current operation and update button text."""
        if self.operation:
            self.operation.toggle_paused()
            if self.operation.paused:
                self.pause_button.setText("Resume")
                self.status_label.setText("Paused")
            else:
                self.pause_button.setText("Pause")
                self.status_label.setText("Resuming...")
    """Enhanced progress dialog with detailed statistics and controls"""
    
    def __init__(self, operation_name, total_files=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{operation_name} - File Operation")
        # Make dialog non-modal to prevent UI blocking
        self.setModal(False)
        self.setMinimumSize(450, 300)
        # Keep on top but don't block the main window
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.operation_worker = None
        self.operation = None
        self.total_files = total_files
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the enhanced progress dialog UI"""
        layout = QVBoxLayout()
        
        # Operation status
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        # Overall progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(True)
        layout.addWidget(self.overall_progress)
        
        # File progress
        self.file_progress_label = QLabel("Files: 0 of 0")
        layout.addWidget(self.file_progress_label)
        
        # Speed and ETA information
        info_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: --")
        self.eta_label = QLabel("ETA: --")
        info_layout.addWidget(self.speed_label)
        info_layout.addStretch()
        info_layout.addWidget(self.eta_label)
        layout.addLayout(info_layout)
        
        # Bytes progress bar
        self.bytes_progress = QProgressBar()
        self.bytes_progress.setRange(0, 100)
        self.bytes_progress.setValue(0)
        self.bytes_progress.setFormat("0 B / 0 B")
        layout.addWidget(self.bytes_progress)
        
        # Detailed statistics (expandable)
        self.stats_group = QGroupBox("Statistics")
        self.stats_group.setCheckable(True)
        self.stats_group.setChecked(False)
        stats_layout = QVBoxLayout()
        self.stats_text = QTextEdit()
        self.stats_text.setMaximumHeight(100)
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        self.stats_group.setLayout(stats_layout)
        layout.addWidget(self.stats_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.pause_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_operation)
        button_layout.addWidget(self.cancel_button)
        
        button_layout.addStretch()
        
        self.minimize_button = QPushButton("Minimize")
        self.minimize_button.clicked.connect(self.showMinimized)
        button_layout.addWidget(self.minimize_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def start_operation(self, operation):
        """Start the enhanced file operation"""
        self.operation = operation
        self.operation_worker = AsyncFileOperationWorker(operation)
        
        # Enable control buttons
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.status_label.setText("Starting operation...")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        
        # Connect all signals
        self.operation_worker.progress.connect(self.update_progress)
        self.operation_worker.fileProgress.connect(self.update_file_progress)
        self.operation_worker.byteProgress.connect(self.update_byte_progress)
        self.operation_worker.speedUpdate.connect(self.update_speed)
        self.operation_worker.etaUpdate.connect(self.update_eta)
        self.operation_worker.statusChanged.connect(self.update_status)
        self.operation_worker.finished.connect(self.on_finished)
        self.operation_worker.errorOccurred.connect(self.handle_error)
        
        self.operation_worker.start()
    
    def update_progress(self, percentage):
        """Update overall progress"""
        self.overall_progress.setValue(percentage)
    
    def update_file_progress(self, current, total):
        """Update file progress indicator"""
        self.file_progress_label.setText(f"Files: {current} of {total}")
    
    def update_byte_progress(self, processed, total):
        """Update byte progress bar"""
        if total > 0:
            percentage = int((processed / total) * 100)
            self.bytes_progress.setValue(percentage)
            self.bytes_progress.setFormat(f"{self._format_bytes(processed)} / {self._format_bytes(total)}")
    
    def update_speed(self, speed_str):
        """Update transfer speed display"""
        self.speed_label.setText(f"Speed: {speed_str}")
    
    def update_eta(self, eta_str):
        """Update estimated time remaining"""
        self.eta_label.setText(f"ETA: {eta_str}")
    
    def update_status(self, status):
        """Update current operation status"""
        self.status_label.setText(status)
        # Clear any special styling for normal status updates
        if self.operation and not self.operation.paused and not self.operation.cancelled:
            self.status_label.setStyleSheet("font-weight: bold; font-size: 12px;")
    
    def cleanup(self):
        """Clean up resources with improved shutdown handling"""
        try:
            if hasattr(self, 'loaded_chunks'):
                self.loaded_chunks.clear()
            if hasattr(self, 'directory_cache'):
                self.directory_cache.clear()
            if hasattr(self, 'executor') and self.executor:
                try:
                    self.executor.shutdown(wait=False)
                    import time
                    time.sleep(0.1)
                except Exception:
                    try:
                        self.executor.shutdown(wait=False)
                    except:
                        pass
        except Exception:
            pass
            # Set up a timeout to force close if cancellation hangs
            # This prevents the dialog from hanging indefinitely
            QTimer.singleShot(3000, self.force_close)  # 3 second timeout
        else:
            # Provide immediate feedback
            self.status_label.setText("Cannot cancel - no active operation")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
    
    def force_close(self):
        """Force close the dialog if cancellation is taking too long"""
        if self.operation and self.operation.cancelled:
            # If operation is cancelled but dialog still open, force close
            self.status_label.setText("Operation cancelled - closing dialog")
            self.accept()
    
    def handle_error(self, file_path, error_msg, suggested_action):
        """Handle errors during file operations"""
        reply = QMessageBox.question(
            self, 
            "File Operation Error",
            f"Error processing: {file_path}\n\nError: {error_msg}\n\nWhat would you like to do?",
            QMessageBox.Retry | QMessageBox.Ignore | QMessageBox.Abort,
            QMessageBox.Retry
        )
        
        if reply == QMessageBox.Abort:
            self.cancel_operation()
        elif reply == QMessageBox.Ignore:
            self.operation.skip_errors = True
    
    def on_finished(self, success, message, stats):
        """Handle operation completion"""
        if success:
            self.status_label.setText("Operation completed successfully!")
            self.overall_progress.setValue(100)
            
            # Update statistics
            if stats:
                stats_text = f"Completed in: {self._format_time_duration(stats.get('elapsed_time', 0))}\n"
                stats_text += f"Files processed: {stats.get('files_processed', 0)}\n"
                stats_text += f"Data processed: {self._format_bytes(stats.get('total_bytes', 0))}\n"
                if stats.get('average_speed', 0) > 0:
                    stats_text += f"Average speed: {self._format_bytes_per_second(stats.get('average_speed', 0))}\n"
                self.stats_text.setText(stats_text)
        else:
            self.status_label.setText(f"Operation failed: {message}")
        
        self.pause_button.setEnabled(False)
        self.cancel_button.setText("Close")
        self.cancel_button.clicked.disconnect()
        self.cancel_button.clicked.connect(self.accept)
        self.cancel_button.setEnabled(True)
        
        # Auto-close after successful operations (optional)
        if success:
            QTimer.singleShot(3000, self.accept)
    
    def _format_bytes(self, bytes_val):
        """Format bytes in human readable format"""
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(bytes_val)
        for unit in units:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    def _format_bytes_per_second(self, bytes_per_second):
        """Format transfer speed"""
        return self._format_bytes(bytes_per_second) + "/s"
    
    def _format_time_duration(self, seconds):
        """Format time duration"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            seconds = int(seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def closeEvent(self, event):
        """Handle dialog close event: just close immediately, no confirmation."""
        event.accept()

    def reject(self):
        """Handle dialog rejection (Escape key, X button): just close immediately, no confirmation."""
        super().reject()

class FileOperation(QObject):
    """Base class for file operations"""
    progress = pyqtSignal(int)  # Progress percentage
    finished = pyqtSignal(bool, str)  # Success, error message
    statusChanged = pyqtSignal(str)  # Status message
    
    def __init__(self, source_paths, destination_path, operation_type):
        super().__init__()
        self.source_paths = source_paths
        self.destination_path = destination_path
        self.operation_type = operation_type  # 'copy', 'move', 'delete'
        self.cancelled = False
        
    def cancel(self):
        self.cancelled = True

class FileOperationWorker(QThread):
    """Worker thread for file operations"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    statusChanged = pyqtSignal(str)
    
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        
    def run(self):
        try:
            if self.operation.operation_type == 'copy':
                self._copy_files()
            elif self.operation.operation_type == 'move':
                self._move_files()
            elif self.operation.operation_type == 'delete':
                self._delete_files()
            
            if not self.operation.cancelled:
                self.finished.emit(True, "Operation completed successfully")
        except Exception as e:
            self.finished.emit(False, str(e))
    
    def _copy_files(self):
        total_files = len(self.operation.source_paths)
        for i, source in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return
                
            self.statusChanged.emit(f"Copying {os.path.basename(source)}...")
            
            if os.path.isdir(source):
                dest = os.path.join(self.operation.destination_path, os.path.basename(source))
                dest = get_nonconflicting_name(dest)
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                dest = os.path.join(self.operation.destination_path, os.path.basename(source))
                dest = get_nonconflicting_name(dest)
                shutil.copy2(source, dest)
            
            self.progress.emit(int((i + 1) / total_files * 100))
    
    def _move_files(self):
        total_files = len(self.operation.source_paths)
        for i, source in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return
                
            self.statusChanged.emit(f"Moving {os.path.basename(source)}...")

            dest = os.path.join(self.operation.destination_path, os.path.basename(source))
            fast_move(source, dest)
            
            self.progress.emit(int((i + 1) / total_files * 100))
    
    def _delete_files(self):
        total_files = len(self.operation.source_paths)
        for i, source in enumerate(self.operation.source_paths):
            if self.operation.cancelled:
                return
                
                
            self.statusChanged.emit(f"Deleting {os.path.basename(source)}...")
            
            if os.path.isdir(source):
                shutil.rmtree(source)
            else:
                os.remove(source)
            
            self.progress.emit(int((i + 1) / total_files * 100))

class OperationProgressDialog(QProgressDialog):
    """Progress dialog for file operations"""
    
    def __init__(self, operation_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{operation_name} Progress")
        self.setLabelText("Initializing...")
        self.setRange(0, 100)
        self.setValue(0)
        self.setModal(True)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.operation_worker = None
        
    def start_operation(self, operation):
        """Start a background file operation"""
        self.operation_worker = AsyncFileOperationWorker(operation)
        self.operation_worker.progress.connect(self.setValue)
        self.operation_worker.statusChanged.connect(self.setLabelText)
        self.operation_worker.finished.connect(self._on_finished)
        self.canceled.connect(operation.cancel)
        self.operation_worker.start()
        
    def _on_finished(self, success, message, stats):
        if success:
            self.setLabelText("Operation completed successfully")
            self.setValue(100)
        else:
            self.setLabelText(f"Error: {message}")
        
        QTimer.singleShot(2000, self.close)

class SyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for code preview"""
    
    def __init__(self, document, file_extension):
        super().__init__(document)
        self.file_extension = file_extension.lower()
        self.setup_highlighting_rules()
    
    def setup_highlighting_rules(self):
        """Setup syntax highlighting rules based on file extension"""
        self.highlighting_rules = []
        
        # Python syntax
        if self.file_extension in ['.py', '.pyw']:
            self.setup_python_highlighting()
        # JavaScript/TypeScript
        elif self.file_extension in ['.js', '.ts', '.jsx', '.tsx']:
            self.setup_javascript_highlighting()
        # C/C++
        elif self.file_extension in ['.c', '.cpp', '.h', '.hpp']:
            self.setup_c_highlighting()
        # HTML/XML
        elif self.file_extension in ['.html', '.htm', '.xml']:
            self.setup_html_highlighting()
    
    def setup_python_highlighting(self):
        """Setup Python syntax highlighting"""
        keyword_format = QTextCharFormat()
        keyword_format.setColor(QColor(85, 85, 255))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 
                   'import', 'from', 'return', 'yield', 'with', 'as', 'pass', 'break', 'continue']
        for keyword in keywords:
            self.highlighting_rules.append((f'\\b{keyword}\\b', keyword_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setColor(QColor(0, 128, 0))
        self.highlighting_rules.append((r'".*?"', string_format))
        self.highlighting_rules.append((r"'.*?'", string_format))
        
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setColor(QColor(128, 128, 128))
        self.highlighting_rules.append((r'#.*', comment_format))
    
    def setup_javascript_highlighting(self):
        """Setup JavaScript syntax highlighting"""
        keyword_format = QTextCharFormat()
        keyword_format.setColor(QColor( 0 , 255 ,0))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ['function', 'var', 'let', 'const', 'if', 'else', 'for', 'while', 
                   'return', 'class', 'extends', 'import', 'export', 'default']
        for keyword in keywords:
            self.highlighting_rules.append((f'\\b{keyword}\\b', keyword_format))
    
    def setup_c_highlighting(self):
        """Setup C/C++ syntax highlighting"""
        keyword_format = QTextCharFormat()
        keyword_format.setColor(QColor( 0 , 255 ,0))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ['int', 'float', 'double', 'char', 'void', 'if', 'else', 'for', 
                   'while', 'return', 'struct', 'class', 'public', 'private', 'protected']
        for keyword in keywords:
            self.highlighting_rules.append((f'\\b{keyword}\\b', keyword_format))
    
    def setup_html_highlighting(self):
        """Setup HTML syntax highlighting"""
        tag_format = QTextCharFormat()
        tag_format.setColor(QColor(128, 0, 128))
        tag_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append((r'<[^>]+>', tag_format))
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        import re
        for pattern, format_obj in self.highlighting_rules:
            for match in re.finditer(pattern, text):
                start, end = match.span()
                self.setFormat(start, end - start, format_obj)

class ClipboardHistoryManager:
    """Advanced clipboard manager with history tracking"""
    def __init__(self):
        self.history = []
        self.max_history = 50
        self.current_operation = None  # 'cut' or 'copy'
        self.current_paths = []
    
    def add_to_history(self, operation, paths, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        
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
        """Enhanced content preview with syntax highlighting"""
        self.text_editor.hide()
        self.preview_area.show()
        
        file_ext = os.path.splitext(file_path)[1].lower()
        mime_type, _ = mimetypes.guess_type(file_path)
        
        # Check if it's an archive file first
        if ArchiveManager.is_archive(file_path):
            self.preview_archive_info(file_path)
        elif mime_type and mime_type.startswith('image/'):
            self.preview_image(file_path)
        elif self.is_code_file(file_ext):
            self.preview_code_file(file_path, file_ext)
        elif mime_type and mime_type.startswith('text/') or file_ext in ['.txt', '.log', '.md', '.json', '.xml', '.csv']:
            self.preview_text_file_enhanced(file_path, file_ext)
        elif file_ext in ['.pdf']:
            self.preview_pdf_info(file_path)
        elif mime_type and mime_type.startswith('video/'):
            self.preview_video_info(file_path)
        elif mime_type and mime_type.startswith('audio/'):
            self.preview_audio_info(file_path)
        else:
            self.preview_generic_file(file_path)
    
    def is_code_file(self, ext):
        """Check if file extension indicates a code file"""
        code_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', '.css', '.scss',
                          '.c', '.cpp', '.h', '.hpp', '.java', '.php', '.rb', '.go', '.rs', '.swift',
                          '.kt', '.scala', '.sh', '.bash', '.ps1', '.sql', '.r', '.matlab', '.m']
        return ext in code_extensions
    
    def preview_code_file(self, file_path, file_ext):
        """Preview code files with syntax highlighting"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 512 * 1024:  # 512KB limit for code files
                self.preview_content.setText(f"Code file too large to preview ({file_size} bytes)")
                return
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            
            # Switch to text editor for syntax highlighting
            self.preview_area.hide()
            self.text_editor.show()
            self.text_editor.setPlainText(content)
            
            # Apply syntax highlighting
            if hasattr(self, 'highlighter'):
                self.highlighter.setDocument(None)
            self.highlighter = SyntaxHighlighter(self.text_editor.document(), file_ext)
            
        except Exception as e:
            self.preview_content.setText(f"Error previewing code file: {str(e)}")
    
    def preview_text_file_enhanced(self, file_path, file_ext):
        """Enhanced text file preview with formatting"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 1024 * 1024:  # 1MB limit
                self.preview_content.setText(f"Text file too large to preview ({file_size} bytes)")
                return
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            
            # For structured text files, provide basic formatting
            if file_ext == '.json':
                try:
                    import json
                    parsed = json.loads(content)
                    content = json.dumps(parsed, indent=2)
                except:
                    pass  # Use original content if JSON parsing fails
            elif file_ext == '.md':
                # Basic markdown preview (simple formatting)
                content = self.format_markdown(content)
            
            self.preview_area.hide()
            self.text_editor.show()
            self.text_editor.setPlainText(content)
            
        except Exception as e:
            self.preview_content.setText(f"Error previewing text file: {str(e)}")
    
    def format_markdown(self, content):
        """Basic markdown formatting for preview"""
        lines = content.split('\n')
        formatted_lines = []
        for line in lines:
            if line.startswith('# '):
                formatted_lines.append(f"━━━ {line[2:]} ━━━")
            elif line.startswith('## '):
                formatted_lines.append(f"── {line[3:]} ──")
            elif line.startswith('### '):
                formatted_lines.append(f"• {line[4:]}")
            else:
                formatted_lines.append(line)
        return '\n'.join(formatted_lines)
    
    def preview_pdf_info(self, file_path):
        """Show PDF file information"""
        try:
            file_size = os.path.getsize(file_path)
            info_text = f"PDF Document\n\n"
            info_text += f"File Size: {self.format_file_size(file_size)}\n"
            info_text += f"Location: {file_path}\n\n"
            info_text += "PDF preview requires external viewer.\n"
            info_text += "Double-click to open with default application."
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading PDF info: {str(e)}")
    
    def preview_video_info(self, file_path):
        """Show video file information"""
        try:
            file_size = os.path.getsize(file_path)
            info_text = f"Video File\n\n"
            info_text += f"File Size: {self.format_file_size(file_size)}\n"
            info_text += f"Location: {file_path}\n\n"
            info_text += "Video preview requires external player.\n"
            info_text += "Double-click to open with default application."
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading video info: {str(e)}")
    
    def preview_audio_info(self, file_path):
        """Show audio file information"""
        try:
            file_size = os.path.getsize(file_path)
            info_text = f"Audio File\n\n"
            info_text += f"File Size: {self.format_file_size(file_size)}\n"
            info_text += f"Location: {file_path}\n\n"
            info_text += "Audio preview requires external player.\n"
            info_text += "Double-click to open with default application."

            # Show waveform thumbnail for all supported audio files
            _, ext = os.path.splitext(file_path)
            supported_audio_exts = ['.wav', '.flac', '.ogg', '.aiff', '.aif', '.aifc', '.au', '.snd', '.sf', '.caf', '.mp3', '.oga', '.aac', '.m4a', '.wma', '.opus', '.alac']
            if ext.lower() in supported_audio_exts:
                try:
                    thumbnail_debug('Calling get_waveform_thumbnail for: {}', file_path)
                    pixmap = get_waveform_thumbnail(file_path, width=400, height=80, thumbnail_cache=self.thumbnail_cache)
                    self.preview_content.setPixmap(pixmap)
                except Exception as e:
                    self.preview_content.setText(f"Error generating waveform: {str(e)}\n\n" + info_text)
                    return
                # Add info text below the waveform
                self.preview_content.setText(info_text)
            else:
                self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading audio info: {str(e)}")

    def preview_archive_info(self, file_path):
        """Show archive file information"""
        try:
            file_size = os.path.getsize(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Determine archive type
            archive_types = {
                '.zip': 'ZIP Archive',
                '.rar': 'RAR Archive', 
                '.tar': 'TAR Archive',
                '.gz': 'GZIP Archive',
                '.bz2': 'BZIP2 Archive',
                '.7z': '7-Zip Archive'
            }
            
            # Handle compound extensions
            if file_path.lower().endswith('.tar.gz') or file_path.lower().endswith('.tgz'):
                archive_type = 'TAR.GZ Archive'
            elif file_path.lower().endswith('.tar.bz2') or file_path.lower().endswith('.tbz2'):
                archive_type = 'TAR.BZ2 Archive'
            else:
                archive_type = archive_types.get(file_ext, 'Archive')
            
            info_text = f"{archive_type}\n\n"
            info_text += f"File Size: {self.format_file_size(file_size)}\n"
            info_text += f"Location: {file_path}\n\n"
            
            # Try to get archive contents info
            try:
                contents = ArchiveManager.list_archive_contents(file_path)
                if contents:
                    file_count = sum(1 for item in contents if not item['is_dir'])
                    dir_count = sum(1 for item in contents if item['is_dir'])
                    info_text += f"Contents: {file_count} files, {dir_count} folders\n\n"
                else:
                    info_text += "Archive contents could not be read.\n\n"
            except:
                info_text += "Archive contents could not be read.\n\n"
            
            info_text += "Double-click to browse archive contents\n"
            info_text += "Right-click for extraction options."
            
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading archive info: {str(e)}")
    
    def clear_preview(self):
        """Clear the preview pane content"""
        self.current_file = None
        self.header_label.setText("Preview")
        self.preview_content.clear()
        self.properties_text.clear()
        
        # Hide text editor and show preview area
        self.text_editor.hide()
        self.preview_area.show()
    
    def update_properties(self, file_info):
        """Update the properties tab with file information"""
        try:
            properties = []
            properties.append(f"Name: {file_info.fileName()}")
            properties.append(f"Size: {self.format_file_size(file_info.size())}")
            properties.append(f"Path: {file_info.absoluteFilePath()}")
            properties.append(f"Modified: {file_info.lastModified().toString()}")
            properties.append(f"Created: {file_info.birthTime().toString()}")
            properties.append(f"Permissions: {file_info.permissions()}")
            properties.append(f"Owner: {file_info.owner()}")
            
            self.properties_text.setText("\n".join(properties))
        except Exception as e:
            self.properties_text.setText(f"Error getting file properties: {str(e)}")
    
    def update_folder_preview(self, folder_path):
        """Update preview for folders"""
        try:
            file_count = 0
            folder_count = 0
            total_size = 0
            
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    file_count += 1
                    try:
                        total_size += os.path.getsize(item_path)
                    except:
                        pass
                elif os.path.isdir(item_path):
                    folder_count += 1
            
            info_text = f"Folder Contents\n\n"
            info_text += f"Files: {file_count}\n"
            info_text += f"Folders: {folder_count}\n"
            info_text += f"Total Size: {self.format_file_size(total_size)}\n"
            
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading folder: {str(e)}")
    
    def format_file_size(self, size):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def preview_image(self, file_path):
        """Preview image files"""
        try:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                self.preview_content.setText("Cannot preview image file")
                return
            
            # Scale image to fit preview area while maintaining aspect ratio
            max_size = 400
            scaled_pixmap = pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_content.setPixmap(scaled_pixmap)
            
        except Exception as e:
            self.preview_content.setText(f"Error previewing image: {str(e)}")
    
    def preview_generic_file(self, file_path):
        """Preview for generic/unknown file types"""
        try:
            file_size = os.path.getsize(file_path)
            file_ext = os.path.splitext(file_path)[1].upper()
            
            info_text = f"File Information\n\n"
            info_text += f"Type: {file_ext[1:] if file_ext else 'Unknown'} File\n"
            info_text += f"Size: {self.format_file_size(file_size)}\n"
            info_text += f"Location: {file_path}\n\n"
            info_text += "Double-click to open with default application."
            
            self.preview_content.setText(info_text)
        except Exception as e:
            self.preview_content.setText(f"Error reading file info: {str(e)}")

class DirectorySelectionDialog(QDialog):
    def create_new_folder(self):
        """Prompt for a folder name and create it in the currently selected directory."""
        base_dir = self.selected_directory or self.initial_dir
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:", text="New Folder")
        if ok and name.strip():
            new_folder_path = os.path.join(base_dir, name.strip())
            if os.path.exists(new_folder_path):
                QMessageBox.warning(self, "Error", f"A folder named '{name}' already exists.")
                return
            try:
                os.makedirs(new_folder_path)
                # Navigate to the base directory in the dialog
                try:
                    self.navigate_to(base_dir)
                except Exception:
                    pass
                # Try to refresh parent window views if available so the new folder appears immediately
                try:
                    parent = getattr(self, 'parent', None) or self.parent()
                    if parent and hasattr(parent, 'refresh_current_view'):
                        try:
                            parent.refresh_current_view()
                        except Exception:
                            pass
                    # Also attempt to refresh the active tab if there's a tab manager
                    if parent and hasattr(parent, 'tab_manager'):
                        try:
                            ct = parent.tab_manager.get_current_tab()
                            if ct and hasattr(ct, 'refresh_thumbnail_view'):
                                try:
                                    ct.refresh_thumbnail_view()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create folder: {str(e)}")
    def on_directory_double_clicked(self, index):
        """Handle double-click on a directory in the tree view: navigate into it."""
        path = self.file_model.filePath(index)
        if os.path.isdir(path):
            self.navigate_to(path)
    def on_directory_clicked(self, index):
        """Handle single click on a directory in the tree view."""
        path = self.file_model.filePath(index)
        if os.path.isdir(path):
            self.selected_directory = path
            self.selected_label.setText(path)
            self.ok_button.setEnabled(True)
    def navigate_home(self):
        """Navigate to the user's home directory."""
        home_dir = os.path.expanduser("~")
        self.navigate_to(home_dir)

    def show_my_computer(self):
        """Set the tree to show connected drives (My Computer view)."""
        try:
            # QFileSystemModel with rootPath set to empty string already exposes drives.
            # Use the model index for the filesystem root so the tree shows available drives.
            root_index = self.file_model.index("")
            self.tree_view.setRootIndex(root_index)
            self.path_label.setText("My Computer")
            self.selected_directory = None
            self.selected_label.setText("No directory selected")
            self.ok_button.setEnabled(False)
        except Exception:
            # Best-effort fallback: navigate to filesystem root
            try:
                self.navigate_to(os.path.abspath(os.sep))
            except Exception:
                pass

    def list_system_drives(self):
        """Return a list of available drive paths (Windows and Unix).

        On Windows this enumerates lettered drives; on Unix returns ['/'].
        """
        drives = []
        try:
            if os.name == 'nt':
                import string
                import ctypes
                bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
                for i in range(26):
                    if bitmask & (1 << i):
                        drives.append(f"{string.ascii_uppercase[i]}:/")
            else:
                drives.append(os.path.abspath(os.sep))
        except Exception:
            drives.append(os.path.abspath(os.sep))
        return drives
    """Built-in directory selection dialog using file manager components"""
    
    def __init__(self, title="Select Directory", initial_dir=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(600, 400)
        
        self.selected_directory = None
        self.initial_dir = initial_dir or os.path.expanduser("~")
        
        self.setup_ui()
        self.navigate_to(self.initial_dir)
    
    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)

        # Address bar (text entry)
        address_layout = QHBoxLayout()
        address_widget = QWidget()
        address_widget.setStyleSheet("background-color: #ffe066; border: 1px solid #aaa; padding: 4px;")
        address_inner_layout = QHBoxLayout(address_widget)
        address_inner_layout.setContentsMargins(0, 0, 0, 0)
        address_label = QLabel("Address:")
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Enter path and press Enter...")
        self.address_bar.returnPressed.connect(self.on_address_entered)
        address_inner_layout.addWidget(address_label)
        address_inner_layout.addWidget(self.address_bar)
        address_layout.addWidget(address_widget)
        layout.addLayout(address_layout)

        # Header with navigation controls and current path
        header_layout = QHBoxLayout()

        # Up button
        up_button = QPushButton("↑ Up")
        up_button.clicked.connect(self.navigate_up)
        header_layout.addWidget(up_button)

        # Home button
        home_button = QPushButton("🏠 Home")
        home_button.clicked.connect(self.navigate_home)
        header_layout.addWidget(home_button)

        # My Computer button - shows all connected drives
        mycomp_button = QPushButton("🖥️ My Computer")
        mycomp_button.setToolTip("Show all connected drives")
        mycomp_button.clicked.connect(self.show_my_computer)
        header_layout.addWidget(mycomp_button)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Current path label
        self.path_label = QLabel()
        self.path_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f0f0f0;")
        layout.addWidget(self.path_label)
        
        # Tree view for directory navigation
        self.tree_view = QTreeView()
        self.file_model = QFileSystemModel()

        # If this tab was created as a My Computer tab, show drive list only
        if isinstance(self.initial_dir, str) and self.initial_dir == "__MY_COMPUTER__":
            # Root path empty string exposes drives on most platforms
            self.file_model.setRootPath("")
            self.file_model.setFilter(QDir.Drives | QDir.Dirs | QDir.NoDotAndDotDot)
            self.tree_view.setModel(self.file_model)
            # Use empty root index so drives appear as top-level items
            self.tree_view.setRootIndex(self.file_model.index(""))
            # Update address bar and labels
            self.address_bar.setText("My Computer")
            self.selected_label.setText("My Computer")
        else:
            self.file_model.setRootPath("")
            self.file_model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
            self.tree_view.setModel(self.file_model)
            self.tree_view.setRootIndex(self.file_model.index(self.initial_dir))
        
        # Hide file columns, only show name
        for i in range(1, self.file_model.columnCount()):
            self.tree_view.hideColumn(i)
        
        self.tree_view.clicked.connect(self.on_directory_clicked)
        self.tree_view.doubleClicked.connect(self.on_directory_double_clicked)
        
        layout.addWidget(self.tree_view)
        
        # Selected directory label
        selected_layout = QHBoxLayout()
        selected_layout.addWidget(QLabel("Selected:"))
        self.selected_label = QLabel("No directory selected")
        self.selected_label.setStyleSheet("font-style: italic;")
        selected_layout.addWidget(self.selected_label)
        selected_layout.addStretch()
        layout.addLayout(selected_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # New folder button
        new_folder_button = QPushButton("Create New Folder")
        new_folder_button.clicked.connect(self.create_new_folder)
        button_layout.addWidget(new_folder_button)
        
        button_layout.addStretch()
        
        # Standard buttons
        self.ok_button = QPushButton("Select")
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
    
    def navigate_to(self, path):
        """Navigate to a specific directory"""
        try:
            # Handle My Computer sentinel explicitly
            if isinstance(path, str) and path == "__MY_COMPUTER__":
                try:
                    self.show_my_computer()
                except Exception:
                    pass
                return

            # Expand user-friendly paths and environment vars
            if isinstance(path, str):
                path = os.path.expanduser(os.path.expandvars(path))

            if os.path.isdir(path):
                index = self.file_model.index(path)
                try:
                    self.tree_view.setRootIndex(index)
                except Exception:
                    pass
                self.path_label.setText(f"Current: {path}")
                self.selected_directory = path
                self.selected_label.setText(path)
                self.address_bar.setStyleSheet("")
                self.address_bar.setToolTip("")
            else:
                # Invalid path entered
                self.address_bar.setStyleSheet("background-color: #ffcccc;")
                self.address_bar.setToolTip("Invalid directory path")
                return
        except Exception:
            try:
                self.address_bar.setStyleSheet("background-color: #ffcccc;")
            except Exception:
                pass

    def on_address_entered(self):
        """Handle Enter in the address bar: navigate or show error"""
        try:
            text = self.address_bar.text().strip()
            if not text:
                return
            # Accept My Computer keywords
            if text.lower() in ("my computer", "mycomputer", "__my_computer__"):
                self.show_my_computer()
                return

            # Expand and navigate
            path = os.path.expanduser(os.path.expandvars(text))
            if os.path.isdir(path):
                self.navigate_to(path)
            else:
                QMessageBox.warning(self, "Invalid Path", f"'{text}' is not a valid directory")
                self.address_bar.setStyleSheet("background-color: #ffcccc;")
                self.address_bar.setToolTip("Invalid directory path")
        except Exception:
            # Fallback: mark address bar red
            try:
                self.address_bar.setStyleSheet("background-color: #ffcccc;")
                self.address_bar.setToolTip("Invalid directory path")
            except Exception:
                pass
    
    def navigate_up(self):
        """Navigate to parent directory"""
        # Determine current folder from this tab's context (address bar or current_folder)
        try:
            current = getattr(self, 'current_folder', None) or self.address_bar.text() or ''
        except Exception:
            current = getattr(self, 'current_folder', '')

        # Normalize and compute parent
        current = os.path.normpath(current) if current else ''
        parent_path = os.path.dirname(current)

        # If current is a drive root (Windows like 'C:\') or filesystem root ('/') then
        # navigate to My Computer instead of trying to go above. Use os.path.ismount which
        # correctly identifies mount points/drive roots across platforms.
        try:
            is_drive_root = bool(current) and os.path.ismount(current)
        except Exception:
            # Fallback: treat filesystem root as drive root
            is_drive_root = (current == os.path.abspath(os.sep))

        if is_drive_root:
            # Switch this tab into My Computer drive-list mode
            try:
                # If this tab supports the sentinel, use it to show drives
                self.navigate_to("__MY_COMPUTER__")
            except Exception:
                # Fallback: set list/detail models to root path
                try:
                    self.list_model.setRootPath("")
                    self.list_view.setRootIndex(self.list_model.index(""))
                except Exception:
                    try:
                        self.list_model.setRootPath(QDir.rootPath())
                        self.list_view.setRootIndex(self.list_model.index(QDir.rootPath()))
                    except Exception:
                        pass
            return

        # Normal parent navigation
        if parent_path and parent_path != current:
            self.navigate_to(parent_path)
    
    def force_cleanup(self):
        """Force aggressive memory cleanup with detailed reporting"""
        try:
            try:
                import psutil
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024  # MB
            except ImportError:
                memory_before = 0
            for callback in self.cleanup_callbacks:
                try:
                    callback(aggressive=True)
                except Exception as e:
                    print(f"Aggressive cleanup callback error: {e}")
            import gc
            total_collected = 0
            for i in range(3):
                collected = gc.collect()
                total_collected += collected
                if gc.garbage:
                    print(f"Warning: {len(gc.garbage)} objects still in gc.garbage after pass {i+1}")
            try:
                if memory_before > 0:
                    memory_after = process.memory_info().rss / 1024 / 1024  # MB
                    memory_freed = memory_before - memory_after
            except:
                pass
            self.last_cleanup = time.time()
        except Exception as e:
            print(f"Error in aggressive cleanup: {e}")
    
    def get_selected_directory(self):
        """Get the selected directory path"""
        return self.selected_directory
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"


class PropertiesDialog(QDialog):
    """Properties dialog for files and directories"""
    
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setWindowTitle(f"Properties - {os.path.basename(file_path)}")
        self.setModal(True)
        self.setMinimumSize(400, 500)
        self.resize(450, 600)
        
        self.setup_ui()
        self.load_properties()
        
    def setup_ui(self):
        """Setup the properties dialog UI"""
        layout = QVBoxLayout(self)
        
        # Create tab widget for different property categories
        tabs = QTabWidget()
        
        # General tab
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)
        
        # File icon and name
        icon_layout = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(64, 64)
        self.icon_label.setScaledContents(True)
        icon_layout.addWidget(self.icon_label)
        
        name_layout = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.type_label = QLabel()
        name_layout.addWidget(self.name_label)
        name_layout.addWidget(self.type_label)
        name_layout.addStretch()
        
        icon_layout.addLayout(name_layout)
        icon_layout.addStretch()
        general_layout.addRow(icon_layout)
        
        # File properties
        self.location_label = QLabel()
        self.location_label.setWordWrap(True)
        general_layout.addRow("Location:", self.location_label)
        
        self.size_label = QLabel()
        general_layout.addRow("Size:", self.size_label)
        
        self.size_on_disk_label = QLabel()
        general_layout.addRow("Size on disk:", self.size_on_disk_label)
        
        self.created_label = QLabel()
        general_layout.addRow("Created:", self.created_label)
        
        self.modified_label = QLabel()
        general_layout.addRow("Modified:", self.modified_label)
        
        self.accessed_label = QLabel()
        general_layout.addRow("Accessed:", self.accessed_label)
        
        # Attributes section
        general_layout.addRow(QLabel(""))  # Spacer
        attributes_group = QGroupBox("Attributes")
        attr_layout = QVBoxLayout(attributes_group)
        
        self.readonly_checkbox = QCheckBox("Read-only")
        self.hidden_checkbox = QCheckBox("Hidden")
        self.archive_checkbox = QCheckBox("Archive")
        
        attr_layout.addWidget(self.readonly_checkbox)
        attr_layout.addWidget(self.hidden_checkbox)
        attr_layout.addWidget(self.archive_checkbox)
        
        general_layout.addRow(attributes_group)
        
        tabs.addTab(general_tab, "General")
        
        # Security tab (Windows-specific)
        if os.name == 'nt':
            security_tab = QWidget()
            security_layout = QVBoxLayout(security_tab)
            
            security_info = QTextEdit()
            security_info.setReadOnly(True)
            security_info.setPlainText("Security information will be displayed here...")
            security_layout.addWidget(security_info)
            
            tabs.addTab(security_tab, "Security")
        
        # Details tab
        details_tab = QWidget()
        details_layout = QVBoxLayout(details_tab)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        
        tabs.addTab(details_tab, "Details")
        
        layout.addWidget(tabs)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.apply_changes)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(apply_button)
        
        layout.addLayout(button_layout)
    
    def load_properties(self):
        """Load and display file properties"""
        try:
            stat_info = os.stat(self.file_path)
            
            # Basic info
            self.name_label.setText(os.path.basename(self.file_path))
            self.location_label.setText(os.path.dirname(self.file_path))
            
            # Determine file type
            if os.path.isdir(self.file_path):
                file_type = "Folder"
                # Count items in directory
                try:
                    items = os.listdir(self.file_path)
                    file_count = sum(1 for item in items if os.path.isfile(os.path.join(self.file_path, item)))
                    folder_count = sum(1 for item in items if os.path.isdir(os.path.join(self.file_path, item)))
                    if file_count > 0 and folder_count > 0:
                        file_type += f" ({file_count} files, {folder_count} folders)"
                    elif file_count > 0:
                        file_type += f" ({file_count} files)"
                    elif folder_count > 0:
                        file_type += f" ({folder_count} folders)"
                except PermissionError:
                    file_type += " (Access denied)"
            else:
                # Get file extension
                _, ext = os.path.splitext(self.file_path)
                if ext:
                    file_type = f"{ext.upper()[1:]} File"
                else:
                    file_type = "File"
                    
            self.type_label.setText(file_type)
            
            # File size
            if os.path.isfile(self.file_path):
                size = stat_info.st_size
                self.size_label.setText(f"{self.format_file_size(size)} ({size:,} bytes)")
                
                # Size on disk (approximate)
                block_size = 4096  # Typical block size
                blocks = (size + block_size - 1) // block_size
                size_on_disk = blocks * block_size
                self.size_on_disk_label.setText(f"{self.format_file_size(size_on_disk)} ({size_on_disk:,} bytes)")
            else:
                # For directories, calculate total size
                total_size = self.calculate_directory_size(self.file_path)
                if total_size >= 0:
                    self.size_label.setText(f"{self.format_file_size(total_size)} ({total_size:,} bytes)")
                    self.size_on_disk_label.setText("Calculating...")
                else:
                    self.size_label.setText("Unknown")
                    self.size_on_disk_label.setText("Unknown")
            
            # Dates
            self.created_label.setText(datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S'))
            self.modified_label.setText(datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'))
            self.accessed_label.setText(datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S'))
            
            # Attributes (Windows specific)
            if os.name == 'nt':
                import stat
                mode = stat_info.st_mode
                self.readonly_checkbox.setChecked(not (mode & stat.S_IWRITE))
                
                # Try to get Windows-specific attributes
                try:
                    import win32api
                    import win32con
                    attrs = win32api.GetFileAttributes(self.file_path)
                    self.hidden_checkbox.setChecked(attrs & win32con.FILE_ATTRIBUTE_HIDDEN)
                    self.archive_checkbox.setChecked(attrs & win32con.FILE_ATTRIBUTE_ARCHIVE)
                except ImportError:
                    self.hidden_checkbox.setEnabled(False)
                    self.archive_checkbox.setEnabled(False)
            else:
                # Unix permissions
                import stat
                mode = stat_info.st_mode
                self.readonly_checkbox.setChecked(not (mode & stat.S_IWUSR))
                self.hidden_checkbox.setChecked(os.path.basename(self.file_path).startswith('.'))
                self.archive_checkbox.setEnabled(False)
            
            # Load icon
            self.load_file_icon()
            
            # Load detailed information
            self.load_detailed_info()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load properties: {str(e)}")
    
    def calculate_directory_size(self, directory_path):
        """Calculate total size of directory"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        continue
            return total_size
        except (OSError, IOError):
            return -1
    
    def load_file_icon(self):
        """Load and display file icon"""
        try:
            # Use the icon cache from main window if available
            icon = QApplication.instance().style().standardIcon(
                QStyle.SP_DirIcon if os.path.isdir(self.file_path) else QStyle.SP_FileIcon
            )
            pixmap = icon.pixmap(64, 64)
            self.icon_label.setPixmap(pixmap)
        except Exception:
            pass
    
    def load_detailed_info(self):
        """Load detailed file information"""
        details = []
        
        try:
            stat_info = os.stat(self.file_path)
            
            details.append(f"Full Path: {self.file_path}")
            details.append(f"File Mode: {oct(stat_info.st_mode)}")
            details.append(f"Inode: {stat_info.st_ino}")
            details.append(f"Device: {stat_info.st_dev}")
            details.append(f"Links: {stat_info.st_nlink}")
            details.append(f"UID: {stat_info.st_uid}")
            details.append(f"GID: {stat_info.st_gid}")
            
            if hasattr(stat_info, 'st_blocks'):
                details.append(f"Blocks: {stat_info.st_blocks}")
            if hasattr(stat_info, 'st_blksize'):
                details.append(f"Block Size: {stat_info.st_blksize}")
                
            # MIME type for files
            if os.path.isfile(self.file_path):
                mime_type, _ = mimetypes.guess_type(self.file_path)
                if mime_type:
                    details.append(f"MIME Type: {mime_type}")
            
            self.details_text.setPlainText('\n'.join(details))
            
        except Exception as e:
            self.details_text.setPlainText(f"Error loading details: {str(e)}")
    
    def apply_changes(self):
        """Apply any changes made to file attributes"""
        try:
            if os.name == 'nt':
                # Windows attribute changes
                try:
                    import win32api
                    import win32con
                    
                    attrs = 0
                    if self.readonly_checkbox.isChecked():
                        attrs |= win32con.FILE_ATTRIBUTE_READONLY
                    if self.hidden_checkbox.isChecked():
                        attrs |= win32con.FILE_ATTRIBUTE_HIDDEN
                    if self.archive_checkbox.isChecked():
                        attrs |= win32con.FILE_ATTRIBUTE_ARCHIVE
                    
                    if attrs == 0:
                        attrs = win32con.FILE_ATTRIBUTE_NORMAL
                        
                    win32api.SetFileAttributes(self.file_path, attrs)
                    
                except ImportError:
                    QMessageBox.warning(self, "Warning", "Windows API not available for attribute changes")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not change attributes: {str(e)}")
            else:
                # Unix permission changes
                import stat
                current_mode = os.stat(self.file_path).st_mode
                
                if self.readonly_checkbox.isChecked():
                    # Remove write permission
                    new_mode = current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH
                else:
                    # Add write permission for user
                    new_mode = current_mode | stat.S_IWUSR
                
                os.chmod(self.file_path, new_mode)
            
            QMessageBox.information(self, "Success", "Properties updated successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not apply changes: {str(e)}")
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
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
            
            folder_name = os.path.basename(folder_path)
            formatted_folder_name = format_filename_with_underscore_wrap(folder_name)
            info_text = f"Folder: {formatted_folder_name}\n\n"
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

class EnhancedSearchEngine(QObject):
    """Advanced search engine with multiple search modes and content indexing"""
    searchCompleted = pyqtSignal(list)  # List of search results
    searchProgress = pyqtSignal(int, str)  # Progress percentage, current file
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_thread = None
        self.should_stop = False
        
    def search(self, root_path, search_criteria):
        """Perform search based on criteria"""
        if self.search_thread and self.search_thread.isRunning():
            self.stop_search()
        
        self.search_thread = SearchThread(root_path, search_criteria, self)
        self.search_thread.searchCompleted.connect(self.searchCompleted.emit)
        self.search_thread.searchProgress.connect(self.searchProgress.emit)
        self.search_thread.start()
    
    def stop_search(self):
        """Stop current search operation"""
        if self.search_thread:
            self.search_thread.stop()
            self.search_thread.wait(3000)  # Wait up to 3 seconds

class SearchThread(QThread):
    """Background thread for performing file searches"""
    searchCompleted = pyqtSignal(list)
    searchProgress = pyqtSignal(int, str)
    
    def __init__(self, root_path, search_criteria, parent=None):
        super().__init__(parent)
        self.root_path = root_path
        self.search_criteria = search_criteria
        self.should_stop = False
        
    def stop(self):
        self.should_stop = True
        
    def run(self):
        """Execute search in background thread"""
        results = []
        total_files = 0
        processed_files = 0
        
        # First pass: count total files for progress tracking
        try:
            for root, dirs, files in os.walk(self.root_path):
                if self.should_stop:
                    return
                total_files += len(files) + len(dirs)
        except PermissionError:
            total_files = 1000  # Fallback estimate
        
        # Second pass: actual search
        try:
            for root, dirs, files in os.walk(self.root_path):
                if self.should_stop:
                    break
                
                # Search in directories
                for dir_name in dirs[:]:  # Use slice to allow modification during iteration
                    if self.should_stop:
                        break
                    
                    full_path = os.path.join(root, dir_name)
                    if self._matches_criteria(full_path, dir_name, True):
                        results.append({
                            'path': full_path,
                            'name': dir_name,
                            'type': 'directory',
                            'size': 0,
                            'modified': os.path.getmtime(full_path),
                            'relative_path': os.path.relpath(full_path, self.root_path)
                        })
                    
                    processed_files += 1
                    if processed_files % 50 == 0:  # Update progress every 50 items
                        progress = int((processed_files / total_files) * 100)
                        self.searchProgress.emit(progress, f"Searching: {dir_name}")
                
                # Search in files
                for file_name in files:
                    if self.should_stop:
                        break
                    
                    full_path = os.path.join(root, file_name)
                    if self._matches_criteria(full_path, file_name, False):
                        try:
                            file_size = os.path.getsize(full_path)
                            file_modified = os.path.getmtime(full_path)
                            
                            result = {
                                'path': full_path,
                                'name': file_name,
                                'type': 'file',
                                'size': file_size,
                                'modified': file_modified,
                                'relative_path': os.path.relpath(full_path, self.root_path)
                            }
                            
                            # Add content search if enabled
                            if self.search_criteria.get('content_search') and self._is_text_file(file_name):
                                if self._search_file_content(full_path):
                                    result['content_match'] = True
                                    results.append(result)
                                elif not self.search_criteria.get('search_text'):
                                    results.append(result)
                            else:
                                results.append(result)
                        except (OSError, PermissionError):
                            continue  # Skip files we can't access
                    
                    processed_files += 1
                    if processed_files % 50 == 0:
                        progress = int((processed_files / total_files) * 100)
                        self.searchProgress.emit(progress, f"Searching: {file_name}")
        
        except Exception as e:
            print(f"Search error: {e}")
        
        self.searchCompleted.emit(results)
    
    def _matches_criteria(self, full_path, name, is_directory):
        """Check if item matches search criteria"""
        criteria = self.search_criteria
        
        # Text search
        search_text = criteria.get('search_text', '').lower()
        if search_text:
            if criteria.get('regex_mode'):
                try:
                    if not re.search(search_text, name, re.IGNORECASE):
                        return False
                except re.error:
                    # Invalid regex, fall back to plain text
                    if search_text not in name.lower():
                        return False
            else:
                if search_text not in name.lower():
                    return False
        
        # File type filter
        file_type = criteria.get('file_type', 'all')
        if file_type != 'all':
            if file_type == 'folders' and not is_directory:
                return False
            elif file_type == 'files' and is_directory:
                return False
            elif not is_directory:  # Specific file type filters
                ext = os.path.splitext(name)[1].lower()
                if file_type == 'images' and ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico']:
                    return False
                elif file_type == 'documents' and ext not in ['.txt', '.doc', '.docx', '.pdf', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx']:
                    return False
                elif file_type == 'videos' and ext not in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']:
                    return False
                elif file_type == 'audio' and ext not in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a']:
                    return False
                elif file_type == 'archives' and ext not in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz']:
                    return False
        
        # Size filter (only for files)
        if not is_directory:
            try:
                file_size = os.path.getsize(full_path)
                size_filter = criteria.get('size_filter', 'any')
                if size_filter == 'small' and file_size >= 1024 * 1024:  # > 1MB
                    return False
                elif size_filter == 'medium' and (file_size < 1024 * 1024 or file_size >= 10 * 1024 * 1024):  # 1-10MB
                    return False
                elif size_filter == 'large' and (file_size < 10 * 1024 * 1024 or file_size >= 100 * 1024 * 1024):  # 10-100MB
                    return False
                elif size_filter == 'very_large' and file_size < 100 * 1024 * 1024:  # < 100MB
                    return False
            except OSError:
                pass
        
        # Date filter
        try:
            file_time = os.path.getmtime(full_path)
            date_filter = criteria.get('date_filter', 'any')
            now = datetime.now()
            if date_filter == 'today':
                file_date = datetime.fromtimestamp(file_time).date()
                if file_date != now.date():
                    return False
            elif date_filter == 'week':
                week_ago = now - timedelta(days=7)
                if file_time < week_ago.timestamp():
                    return False
            elif date_filter == 'month':
                month_ago = now - timedelta(days=30)
                if file_time < month_ago.timestamp():
                    return False
            elif date_filter == 'year':
                year_ago = now - timedelta(days=365)
                if file_time < year_ago.timestamp():
                    return False
        except OSError:
            pass
        
        return True
    
    def _is_text_file(self, filename):
        """Check if file is likely a text file"""
        text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.xml', '.json', '.csv', '.log', '.md', '.rst'}
        ext = os.path.splitext(filename)[1].lower()
        return ext in text_extensions
    
    def _search_file_content(self, file_path):
        """Search within file content"""
        search_text = self.search_criteria.get('search_text', '').lower()
        if not search_text:
            return False
        
        try:
            # Limit file size for content search (max 10MB)
            if os.path.getsize(file_path) > 10 * 1024 * 1024:
                return False
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                if self.search_criteria.get('regex_mode'):
                    try:
                        return bool(re.search(search_text, content, re.IGNORECASE))
                    except re.error:
                        return search_text in content
                else:
                    return search_text in content
        except (OSError, UnicodeDecodeError, PermissionError):
            return False

class SearchFilterWidget(QWidget):
    """Enhanced search and filter widget with advanced filtering options"""
    searchRequested = pyqtSignal(str, dict)  # search_text, filter_options
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_engine = EnhancedSearchEngine(self)
        self.current_results = []
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._perform_delayed_search)
        self.setup_ui()
        self.connect_signals()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        
        # Search input with advanced options
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout()
        
        # Main search input
        input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files and folders...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        input_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        input_layout.addWidget(self.search_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_search)
        self.stop_button.setEnabled(False)
        input_layout.addWidget(self.stop_button)
        
        search_layout.addLayout(input_layout)
        
        # Search options
        options_layout = QHBoxLayout()
        self.regex_checkbox = QCheckBox("Regex")
        self.regex_checkbox.setToolTip("Use regular expressions for pattern matching")
        options_layout.addWidget(self.regex_checkbox)
        
        self.content_checkbox = QCheckBox("Search Content")
        self.content_checkbox.setToolTip("Search inside text files (slower)")
        options_layout.addWidget(self.content_checkbox)
        
        self.case_checkbox = QCheckBox("Case Sensitive")
        options_layout.addWidget(self.case_checkbox)
        
        options_layout.addStretch()
        search_layout.addLayout(options_layout)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        # Advanced filters
        filter_group = QGroupBox("Filters")
        filter_layout = QGridLayout()
        
        # File type filter
        filter_layout.addWidget(QLabel("Type:"), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "All", "Files Only", "Folders Only", "Images", "Documents", 
            "Videos", "Audio", "Archives"
        ])
        self.type_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_combo, 0, 1)
        
        # Size filter
        filter_layout.addWidget(QLabel("Size:"), 1, 0)
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "Any Size", "Small (<1MB)", "Medium (1-10MB)", 
            "Large (10-100MB)", "Very Large (>100MB)"
        ])
        self.size_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.size_combo, 1, 1)
        
        # Date filter
        filter_layout.addWidget(QLabel("Modified:"), 2, 0)
        self.date_combo = QComboBox()
        self.date_combo.addItems([
            "Any Time", "Today", "This Week", "This Month", "This Year"
        ])
        self.date_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.date_combo, 2, 1)
        
        # Extension filter
        filter_layout.addWidget(QLabel("Extension:"), 3, 0)
        self.extension_input = QLineEdit()
        self.extension_input.setPlaceholderText("e.g., .txt, .py")
        self.extension_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.extension_input, 3, 1)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Search results area
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout()
        
        # Results info
        self.results_info = QLabel("Ready to search")
        results_layout.addWidget(self.results_info)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        results_layout.addWidget(self.progress_bar)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        results_layout.addWidget(self.results_list)
        
        # Results actions
        results_actions = QHBoxLayout()
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self._open_selected_result)
        self.open_button.setEnabled(False)
        results_actions.addWidget(self.open_button)
        
        self.reveal_button = QPushButton("Show in Folder")
        self.reveal_button.clicked.connect(self._reveal_selected_result)
        self.reveal_button.setEnabled(False)
        results_actions.addWidget(self.reveal_button)
        
        self.clear_button = QPushButton("Clear Results")
        self.clear_button.clicked.connect(self.clear_results)
        results_actions.addWidget(self.clear_button)
        
        results_actions.addStretch()
        results_layout.addLayout(results_actions)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        self.setLayout(layout)
    
    def connect_signals(self):
        """Connect search engine signals"""
        self.search_engine.searchCompleted.connect(self._on_search_completed)
        self.search_engine.searchProgress.connect(self._on_search_progress)
        self.results_list.itemSelectionChanged.connect(self._on_selection_changed)
    
    def _on_search_text_changed(self):
        """Handle search text changes with delay"""
        self.search_timer.stop()
        if len(self.search_input.text()) >= 2:
            self.search_timer.start(500)  # 500ms delay
        elif len(self.search_input.text()) == 0:
            self.clear_results()
    
    def _on_filter_changed(self):
        """Handle filter changes"""
        if self.search_input.text():
            self.search_timer.stop()
            self.search_timer.start(300)  # Shorter delay for filter changes
    
    def _perform_delayed_search(self):
        """Perform search after delay"""
        self.perform_search()
    
    def perform_search(self):
        """Execute search with current criteria"""
        search_text = self.search_input.text().strip()
        
        # Get current tab's folder as search root
        parent_window = self.parent()
        while parent_window and not hasattr(parent_window, 'tab_manager'):
            parent_window = parent_window.parent()
        
        if not parent_window or not parent_window.tab_manager:
            return
        
        current_tab = parent_window.tab_manager.get_current_tab()
        if not current_tab:
            return
        
        search_root = current_tab.current_folder
        
        # Build search criteria
        criteria = {
            'search_text': search_text,
            'file_type': self._get_file_type_key(),
            'size_filter': self._get_size_key(),
            'date_filter': self._get_date_key(),
            'extension': self.extension_input.text().strip(),
            'regex_mode': self.regex_checkbox.isChecked(),
            'content_search': self.content_checkbox.isChecked(),
            'case_sensitive': self.case_checkbox.isChecked()
        }
        
        # Start search
        self.results_info.setText(f"Searching in {search_root}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.clear_results()
        
        self.search_engine.search(search_root, criteria)
    
    def stop_search(self):
        """Stop current search"""
        self.search_engine.stop_search()
        self.progress_bar.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.results_info.setText("Search stopped")
    
    def clear_results(self):
        """Clear search results"""
        self.results_list.clear()
        self.current_results = []
        self.open_button.setEnabled(False)
        self.reveal_button.setEnabled(False)
    
    def _get_file_type_key(self):
        """Convert combo box selection to internal key"""
        type_map = {
            "All": "all",
            "Files Only": "files", 
            "Folders Only": "folders",
            "Images": "images",
            "Documents": "documents",
            "Videos": "videos",
            "Audio": "audio",
            "Archives": "archives"
        }
        return type_map.get(self.type_combo.currentText(), "all")
    
    def _get_size_key(self):
        """Convert size combo to internal key"""
        size_map = {
            "Any Size": "any",
            "Small (<1MB)": "small",
            "Medium (1-10MB)": "medium",
            "Large (10-100MB)": "large",
            "Very Large (>100MB)": "very_large"
        }
        return size_map.get(self.size_combo.currentText(), "any")
    
    def _get_date_key(self):
        """Convert date combo to internal key"""
        date_map = {
            "Any Time": "any",
            "Today": "today",
            "This Week": "week", 
            "This Month": "month",
            "This Year": "year"
        }
        return date_map.get(self.date_combo.currentText(), "any")
    
    def _on_search_completed(self, results):
        """Handle search completion"""
        self.current_results = results
        self.progress_bar.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        self.results_list.clear()
        
        if not results:
            self.results_info.setText("No results found")
            return
        
        self.results_info.setText(f"Found {len(results)} items")
        
        # Sort results by relevance (directories first, then by name)
        results.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))
        
        for result in results:
            item_text = result['name']
            if result['type'] == 'directory':
                item_text = f"📁 {item_text}"
            else:
                # Add file size info
                size = result['size']
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size/1024:.1f} KB"
                elif size < 1024 * 1024 * 1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                else:
                    size_str = f"{size/(1024*1024*1024):.1f} GB"
                
                item_text = f"📄 {item_text} ({size_str})"
            
            # Add relative path info
            if result['relative_path'] != result['name']:
                item_text += f" - {os.path.dirname(result['relative_path'])}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, result)
            item.setToolTip(result['path'])
            self.results_list.addItem(item)
    
    def _on_search_progress(self, percentage, current_file):
        """Handle search progress updates"""
        self.progress_bar.setValue(percentage)
        if current_file:
            # Truncate long filenames
            if len(current_file) > 50:
                current_file = current_file[:47] + "..."
            self.results_info.setText(f"Searching... {current_file}")
    
    def _on_selection_changed(self):
        """Handle result selection changes"""
        has_selection = bool(self.results_list.currentItem())
        self.open_button.setEnabled(has_selection)
        self.reveal_button.setEnabled(has_selection)
    
    def _on_result_double_clicked(self, item):
        """Handle double-click on result item"""
        self._open_selected_result()
    
    def _open_selected_result(self):
        """Open the selected result"""
        current_item = self.results_list.currentItem()
        if not current_item:
            return
        
        result = current_item.data(Qt.UserRole)
        if result['type'] == 'directory':
            # Navigate to directory
            self._navigate_to_path(result['path'])
        elif ArchiveManager.is_archive(result['path']):
            # For archive files, use built-in browser
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'browse_archive_contents'):
                main_window = main_window.parent()
            if main_window:
                main_window.browse_archive_contents(result['path'])
            else:
                # Fallback if browse method not found
                QDesktopServices.openUrl(QUrl.fromLocalFile(result['path']))
        else:
            # Open file with default application
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(result['path']))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open file: {e}")
    
    def _reveal_selected_result(self):
        """Reveal selected result in file manager"""
        current_item = self.results_list.currentItem()
        if not current_item:
            return
        
        result = current_item.data(Qt.UserRole)
        if result['type'] == 'directory':
            self._navigate_to_path(result['path'])
        else:
            # Navigate to parent directory and select file
            parent_dir = os.path.dirname(result['path'])
            self._navigate_to_path(parent_dir)
    
    def _navigate_to_path(self, path):
        """Navigate to the specified path in the main window"""
        parent_window = self.parent()
        while parent_window and not hasattr(parent_window, 'tab_manager'):
            parent_window = parent_window.parent()
        
        if parent_window and parent_window.tab_manager:
            current_tab = parent_window.tab_manager.get_current_tab()
            if current_tab:
                current_tab.navigate_to(path)

class SearchFilterWidget_Old(QWidget):
    """Original simple search widget - kept for backward compatibility"""
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
    THUMBNAIL_VIEW = "thumbnail"
    ICON_VIEW = "icon"
    LIST_VIEW = "list"
    DETAIL_VIEW = "detail"
    
    def __init__(self):
        self.current_mode = self.THUMBNAIL_VIEW
        self.view_widgets = {}
    
    def set_mode(self, mode):
        # Accept ICON_VIEW as a valid mode as well
        if mode in [self.THUMBNAIL_VIEW, self.ICON_VIEW, self.LIST_VIEW, self.DETAIL_VIEW]:
            self.current_mode = mode
    
    def get_mode(self):
        return self.current_mode

class IconWidget(QWidget):
    clicked = pyqtSignal(str, object)  # Pass the event modifiers
    doubleClicked = pyqtSignal(str)
    rightClicked = pyqtSignal(str, QPoint)

    def __init__(self, file_name, full_path, is_dir, thumbnail_size=64, thumbnail_cache=None, use_icon_only=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.full_path = full_path
        self.is_dir = is_dir
        self.thumbnail_size = thumbnail_size
        self.thumbnail_cache = thumbnail_cache
        self.use_icon_only = use_icon_only
        self.dark_mode = False
        self.is_selected = False

        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        # Create icon or thumbnail
        pixmap = self.create_icon_or_thumbnail(full_path, is_dir)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.icon_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.icon_label.setMinimumHeight(self.thumbnail_size)
        self.icon_label.setMaximumHeight(16777215)
        self.icon_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.icon_label.setMinimumHeight(self.thumbnail_size)
        self.icon_label.setMaximumHeight(16777215)  # No artificial max height

        # Pie chart for drive usage (only for drives in My Computer)
        self.pie_chart_label = None
        show_drive_pie = False
        import os, shutil
        # Heuristic: show pie if this is a drive root (C:/ etc) and in My Computer
        try:
            # Only show for top-level drives (not folders/files)
            if os.name == 'nt' and len(full_path) >= 2 and full_path[1] == ':' and (full_path.endswith('/') or full_path.endswith('\\')):
                if os.path.ismount(full_path):
                    show_drive_pie = True
            elif os.name != 'nt' and os.path.ismount(full_path):
                show_drive_pie = True
        except Exception:
            pass
        if show_drive_pie:
            try:
                usage = shutil.disk_usage(full_path)
                percent = usage.used / usage.total if usage.total > 0 else 0
                pie_size = max(18, int(self.thumbnail_size * 0.38))
                # Make a larger pixmap for text to overflow
                margin = int(pie_size * 0.35)
                total_size = pie_size + margin * 2
                overlay_pixmap = QPixmap(total_size, total_size)
                overlay_pixmap.fill(Qt.transparent)
                painter = QPainter(overlay_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                # Draw pie chart centered
                pie_rect = QRect(margin, margin, pie_size, pie_size)
                painter.setBrush(QColor(220, 220, 220))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(pie_rect)
                painter.setBrush(QColor(0, 120, 215))
                start_angle = 90 * 16
                span_angle = -int(360 * percent * 16)
                painter.drawPie(pie_rect, start_angle, span_angle)
                # Overlay free space in GB as text (can overflow pie)
                free_gb = usage.free / (1024 ** 3)
                painter.setPen(QColor(0, 180, 0))
                font = painter.font()
                font.setPointSizeF(max(6, pie_size * 0.32 * 0.9))
                font.setBold(True)
                painter.setFont(font)
                text = f"{free_gb:.1f}G"
                painter.drawText(overlay_pixmap.rect(), Qt.AlignCenter, text)
                painter.end()
                self.pie_chart_label = QLabel()
                self.pie_chart_label.setPixmap(overlay_pixmap)
                self.pie_chart_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.pie_chart_label.setStyleSheet("background: transparent;")
            except Exception:
                self.pie_chart_label = None

        layout.addWidget(self.icon_label)

        # Create label with filename (apply truncation and underscore wrapping)
        self.label = QLabel()
        font = self.label.font()
        font.setPointSize(8)
        self.label.setFont(font)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.label.setContentsMargins(2, 2, 2, 2)
        self.label.setStyleSheet("QLabel { padding: 2px; }")
        try:
            self.label.setFixedWidth(self.thumbnail_size)
        except Exception:
            pass
        self.update_label_text()
        layout.addWidget(self.label)

        # Add pie chart below the label if it exists
        if self.pie_chart_label is not None:
            layout.addWidget(self.pie_chart_label)
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.setToolTip(full_path)
        self.setStyleSheet("QWidget { border: 2px solid transparent; }")
    
    def update_label_text(self):
        """Update label text based on selection state and apply formatting"""
        # Determine max characters based on current thumbnail width and label font metrics
        try:
            fm = self.label.fontMetrics()
            avg_char_w = max(6, fm.averageCharWidth() or 7)
            max_chars = max(6, int(self.thumbnail_size / avg_char_w))
        except Exception:
            max_chars = 13

        # Apply truncation based on selection state
        display_name = truncate_filename_for_display(self.file_name, max_chars=max_chars, selected=self.is_selected)

        # Apply underscore wrapping if showing full name or if short enough
        if self.is_selected or len(self.file_name) <= max_chars:
            display_name = format_filename_with_underscore_wrap(display_name)

        self.label.setText(display_name)
    
    def set_selected(self, selected):
        """Set the selection state and update display accordingly"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update_label_text()
            # Update border style to show selection
            if selected:
                self.setStyleSheet("QWidget { border: 2px solid #0078d4; background-color: rgba(0, 120, 212, 0.1); }")
            else:
                self.setStyleSheet("QWidget { border: 2px solid transparent; }")

    def update_style_for_theme(self, dark_mode):
        """Update the widget style based on the current theme"""
        self.dark_mode = dark_mode
        if dark_mode:
            self.label.setStyleSheet("QLabel { color: #ffffff; padding: 2px; }")
        else:
            self.label.setStyleSheet("QLabel { padding: 2px; }")
    
    def update_thumbnail_size(self, new_size):
        """Update the icon/thumbnail size for this widget"""
    # ...removed thumbnail debug message...
        if self.thumbnail_size != new_size:
            self.thumbnail_size = new_size
            # Regenerate the icon with the new size
            pixmap = self.create_icon_or_thumbnail(self.full_path, self.is_dir)
            self.icon_label.setPixmap(pixmap)
            # Resize icon_label widget area if possible
            try:
                self.icon_label.setFixedSize(new_size, new_size)
            except Exception:
                pass
            # Ensure filename label width matches new thumbnail width
            try:
                self.label.setFixedWidth(new_size)
            except Exception:
                pass
            # Refresh text to recalc truncation
            try:
                self.update_label_text()
            except Exception:
                pass
            self.update()  # Force a repaint

    def create_icon_or_thumbnail(self, full_path, is_dir):
        thumbnail_debug('create_icon_or_thumbnail called: {} (is_dir={})', full_path, is_dir)
        """Create either a file icon or an image thumbnail"""
        size = self.thumbnail_size
        # APK thumbnails are handled later once file_ext is available to avoid blocking other logic
        # Determine effective icon-only mode: respect the widget flag or fall back to main window's view mode
        effective_icon_only = getattr(self, 'use_icon_only', False)
        try:
            # Walk up to find the main window and check its view_mode_manager
            parent = self.parent()
            while parent is not None and not hasattr(parent, 'view_mode_manager'):
                parent = parent.parent()
            if parent is not None and hasattr(parent, 'view_mode_manager'):
                if parent.view_mode_manager.get_mode() == ViewModeManager.ICON_VIEW:
                    effective_icon_only = True
            # Respect the global user preference if set on main window
            try:
                if parent is not None and hasattr(parent, 'icon_view_use_icons_only') and not parent.icon_view_use_icons_only:
                    # User asked not to use icons-only behavior; disable the effective flag
                    effective_icon_only = False
                elif parent is not None and hasattr(parent, 'icon_view_use_icons_only') and parent.icon_view_use_icons_only and parent.view_mode_manager.get_mode() == ViewModeManager.ICON_VIEW:
                    effective_icon_only = True
            except Exception:
                pass
            # Also respect a direct flag on the main window if present
            try:
                if parent is not None and hasattr(parent, 'icon_view_active') and parent.icon_view_active:
                    effective_icon_only = True
            except Exception:
                pass
        except Exception:
            pass
        # Debug
        thumbnail_debug('effective_icon_only={} for {}', effective_icon_only, full_path)

        # If this is a directory, handle differently depending on mode
        if is_dir:
            # In icon-only mode show a simple folder icon (no composite previews)
            if effective_icon_only:
                try:
                    icon_provider = QFileIconProvider()
                    folder_info = QFileInfo(full_path)
                    folder_icon = icon_provider.icon(folder_info)
                    if not folder_icon.isNull():
                        pix = folder_icon.pixmap(size, size)
                        if pix.width() != size or pix.height() != size:
                            pix = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        return pix
                except Exception:
                    # Fallback to generic folder drawing
                    framed_pixmap = QPixmap(size, size)
                    framed_pixmap.fill(Qt.transparent)
                    painter = QPainter(framed_pixmap)
                    try:
                        self.draw_generic_file_icon(painter, size, True)
                    except Exception:
                        pass
                    painter.end()
                    return framed_pixmap
            # Not icon-only: use the composite folder preview as before
            return self.create_folder_preview(full_path, size)

        # Guard: do not attempt to generate thumbnails for thumbnail cache files themselves
        try:
            if is_thumb_file(full_path):
                thumbnail_debug('Skipping thumbnail generation for .thumb file: {}', full_path)
                framed_pixmap = QPixmap(size, size)
                framed_pixmap.fill(Qt.transparent)
                painter = QPainter(framed_pixmap)
                try:
                    # Draw a default file icon into the frame
                    self.draw_default_file_icon(painter, full_path, size)
                except Exception:
                    pass
                try:
                    painter.end()
                except Exception:
                    pass
                return framed_pixmap
        except Exception:
            # if guard check fails, continue with normal behavior
            pass

        # If we're in icon-only mode, avoid expensive thumbnail generation (images, video frames, waveforms)
        if effective_icon_only:
            framed_pixmap = QPixmap(size, size)
            framed_pixmap.fill(Qt.transparent)
            painter = QPainter(framed_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            try:
                file_ext = os.path.splitext(full_path)[1].lower()
                # In icon-only mode we handle archives/exes/default drawing below; do not special-case APK here
                if ArchiveManager.is_archive(full_path):
                    # For ISO archives, when we're in thumbnail view (not icon-only),
                    # prefer the enhanced/custom thumbnail generation path always.
                    try:
                        archive_type = ArchiveManager.get_archive_type(full_path)
                    except Exception:
                        archive_type = None
                    if archive_type == '.iso' and not effective_icon_only:
                        # Force custom enhanced ISO thumbnail rendering
                        try:
                            # draw_archive_icon supports a force_custom flag via locals()
                            self.draw_archive_icon(painter, full_path, size, force_custom=True)
                        except TypeError:
                            # Older call signature fallback
                            self.draw_custom_archive_icon(painter, full_path, size)
                    else:
                        self.draw_archive_icon(painter, full_path, size)
                elif file_ext == '.exe' and not is_dir:
                    try:
                        icon = get_exe_icon_qicon(full_path, size)
                        if not icon.isNull():
                            pixmap = icon.pixmap(size, size)
                            painter.drawPixmap(0, 0, pixmap)
                        else:
                            self.draw_default_file_icon(painter, full_path, size)
                    except Exception:
                        self.draw_default_file_icon(painter, full_path, size)
                else:
                    # Generic icon for all other file types in icon view
                    self.draw_default_file_icon(painter, full_path, size)
            except Exception:
                self.draw_generic_file_icon(painter, size, is_dir)
            painter.end()
            return framed_pixmap
        # Try to get thumbnail from cache first for files
        if self.thumbnail_cache:
            thumbnail_debug('Checking cache for {}', full_path)
            cached_thumbnail = self.thumbnail_cache.get(full_path, size)
            if cached_thumbnail:
                thumbnail_debug('Cache hit for {}, returning cached thumbnail', full_path)
                # Always return a QPixmap, never raw bytes
                if isinstance(cached_thumbnail, QPixmap):
                    return cached_thumbnail
                elif isinstance(cached_thumbnail, (bytes, bytearray)):
                    pixmap = QPixmap()
                    pixmap.loadFromData(cached_thumbnail, 'PNG')
                    return pixmap
                else:
                    thumbnail_debug('Unexpected cached_thumbnail type: {}', type(cached_thumbnail))
                    return QPixmap()
        # Create a consistent-sized frame for all icons
        framed_pixmap = QPixmap(size, size)
        framed_pixmap.fill(Qt.transparent)
        painter = QPainter(framed_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # If this is an ISO archive and we're not in icon-only mode, prefer the
        # enhanced ISO thumbnail path which extracts/examines the ISO contents.
        try:
            if ArchiveManager.is_archive(full_path):
                try:
                    archive_type = ArchiveManager.get_archive_type(full_path)
                except Exception:
                    archive_type = None
                if archive_type == '.iso' and not effective_icon_only:
                    try:
                        # draw_archive_icon supports a force_custom flag; use it to
                        # request the ISO-specific rendering.
                        self.draw_archive_icon(painter, full_path, size, force_custom=True)
                    except TypeError:
                        # older signature fallback
                        try:
                            self.draw_custom_archive_icon(painter, full_path, size)
                        except Exception:
                            pass
                    try:
                        painter.end()
                    except Exception:
                        pass
                    return framed_pixmap
        except Exception:
            # If any errors occur, fall through to the normal handling below
            pass
        try:
            # ...existing code for file icon/thumbnail drawing...
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico', '.xcf'}
                if not PlatformUtils.is_macos():
                    image_extensions.add('.svg')
                file_ext = os.path.splitext(full_path)[1].lower()
                thumbnail_debug('[THUMBNAIL-DEBUG] file_ext for {}: {}', full_path, file_ext)

                # APK/XAPK-specific thumbnail: compose Android robot base and overlay extracted icon if available
                if file_ext in ('.apk', '.xapk') and not is_dir:
                    try:
                        import zipfile
                        from io import BytesIO
                        icon_data = None
                        chosen_name = None
                        with zipfile.ZipFile(full_path, 'r') as z:
                            # Prefer using apkutils2 if available to get the declared icon path
                            try:
                                from apkutils2 import APK
                                apkinfo = APK(full_path)
                                icon_path = None
                                # Primary helper
                                try:
                                    icon_path = apkinfo.get_app_icon()
                                except Exception:
                                    icon_path = None
                                # Try several alternative helper names if available
                                if not icon_path:
                                    for meth in ('get_icon', 'get_manifest_icon', 'get_app_icon_path'):
                                        fn = getattr(apkinfo, meth, None)
                                        if callable(fn):
                                            try:
                                                res = fn()
                                                if res:
                                                    icon_path = res
                                                    break
                                            except Exception:
                                                continue
                                # Try to inspect manifest dictionaries returned by apkutils2
                                if not icon_path:
                                    for mf in ('get_manifest', 'get_android_manifest', 'get_manifest_dict'):
                                        fn = getattr(apkinfo, mf, None)
                                        if callable(fn):
                                            try:
                                                manifest = fn()
                                                if isinstance(manifest, dict):
                                                    app = manifest.get('application') or manifest.get('application', {})
                                                    if isinstance(app, dict):
                                                        icon_candidate = app.get('icon') or app.get('@icon') or app.get('android:icon')
                                                        if icon_candidate:
                                                            icon_path = icon_candidate
                                                            break
                                            except Exception:
                                                continue
                                # If icon_path is a resource name (like 'ic_launcher' or 'mipmap/ic_launcher'), map it to a file inside the APK
                                if icon_path and isinstance(icon_path, str):
                                    norm = icon_path
                                    # If it looks like resource reference (no slash, no extension), try to resolve by name
                                    if not norm.startswith('res/') and '/' not in norm and not norm.endswith(('.png', '.webp')):
                                        resname = norm.split('/')[-1]
                                        found = None
                                        for name in z.namelist():
                                            ln = name.lower()
                                            if ln.endswith((resname + '.png', resname + '.webp')):
                                                found = name
                                                break
                                        if found:
                                            icon_path = found
                                # If resolved path exists in the zip, read it
                                if icon_path and icon_path in z.namelist():
                                    try:
                                        icon_data = z.read(icon_path)
                                        chosen_name = icon_path
                                    except Exception:
                                        icon_data = None
                                print(f'[APK-ICON] apkutils2 resolved icon_path={icon_path}')
                            except Exception:
                                # Collect candidate icon files and pick the largest (likely highest-res)
                                candidates = []
                                for name in z.namelist():
                                    ln = name.lower()
                                    # Broader candidate matching: any png/webp under res/ or assets/ or files whose base name hints at an icon
                                    base = os.path.basename(ln)
                                    is_image = ln.endswith(('.png', '.webp'))
                                    likely_icon_name = any(k in base for k in ('icon', 'ic_', 'launcher', 'foreground', 'round', 'logo'))
                                    if is_image and (ln.startswith('res/') or '/assets/' in ln or likely_icon_name):
                                        try:
                                            info = z.getinfo(name)
                                            candidates.append((name, info.file_size))
                                        except Exception:
                                            candidates.append((name, 0))
                                if candidates:
                                    # choose candidate with largest file size
                                    candidates.sort(key=lambda t: t[1], reverse=True)
                                    # log candidate list for debugging
                                    try:
                                        print(f'[APK-ICON] candidates for {full_path}: ' + ', '.join([f"{n}({s})" for n, s in candidates[:10]]))
                                    except Exception:
                                        pass
                                    chosen_name = candidates[0][0]
                                    try:
                                        icon_data = z.read(chosen_name)
                                    except Exception:
                                        icon_data = None
                                # Fallback: if we still have no chosen_name, search for any res/*.png or res/*.webp and pick largest
                                if not icon_data and not chosen_name:
                                    try:
                                        png_candidates = []
                                        for name in z.namelist():
                                            ln = name.lower()
                                            if (ln.startswith('res/') or '/assets/' in ln) and ln.endswith(('.png', '.webp')):
                                                try:
                                                    info = z.getinfo(name)
                                                    png_candidates.append((name, info.file_size))
                                                except Exception:
                                                    png_candidates.append((name, 0))
                                        if png_candidates:
                                            png_candidates.sort(key=lambda t: t[1], reverse=True)
                                            chosen_name = png_candidates[0][0]
                                            try:
                                                icon_data = z.read(chosen_name)
                                                print(f'[APK-ICON] Fallback chose {chosen_name} from res/ entries')
                                            except Exception:
                                                icon_data = None
                                    except Exception:
                                        pass

                        try:
                            sig = None
                            if icon_data:
                                sig = ' '.join([f'{b:02x}' for b in icon_data[:12]])
                        except Exception:
                            sig = None
                        print(f'[APK-ICON] APK handler: chosen icon path={chosen_name} for {full_path}, bytes={'None' if icon_data is None else len(icon_data)}, sig={sig}')

                        # Final guaranteed fallback: if we still have no icon_data, try one more pass to pick largest res/*.png or .webp
                        if not icon_data:
                            try:
                                with zipfile.ZipFile(full_path, 'r') as z_final:
                                    png_candidates = []
                                    for name in z_final.namelist():
                                        ln = name.lower()
                                        if (ln.startswith('res/') or '/assets/' in ln) and ln.endswith(('.png', '.webp')):
                                            try:
                                                info = z_final.getinfo(name)
                                                png_candidates.append((name, info.file_size))
                                            except Exception:
                                                png_candidates.append((name, 0))
                                    if png_candidates:
                                        png_candidates.sort(key=lambda t: t[1], reverse=True)
                                        chosen_name = png_candidates[0][0]
                                        try:
                                            icon_data = z_final.read(chosen_name)
                                            print(f'[APK-ICON] Final fallback chose {chosen_name} ({len(icon_data) if icon_data else 0} bytes)')
                                        except Exception as e_final:
                                            print(f'[APK-ICON] Final fallback read failed: {e_final}')
                            except Exception:
                                pass

                        base_size = size
                        base_pixmap = QPixmap(base_size, base_size)
                        base_pixmap.fill(Qt.transparent)
                        painter_apk = QPainter(base_pixmap)
                        painter_apk.setRenderHint(QPainter.Antialiasing)
                        painter_apk.setBrush(QColor(164, 198, 57))
                        painter_apk.setPen(Qt.NoPen)
                        painter_apk.drawEllipse(base_size//8, base_size//8, base_size*3//4, base_size*3//4)
                        painter_apk.setBrush(Qt.white)
                        eye_r = max(2, base_size//16)
                        painter_apk.drawEllipse(base_size//3, base_size//2, eye_r, eye_r)
                        painter_apk.drawEllipse(base_size*2//3 - eye_r, base_size//2, eye_r, eye_r)
                        painter_apk.setPen(QPen(QColor(164, 198, 57), max(2, base_size//16)))
                        painter_apk.drawLine(base_size//3, base_size//8, base_size//4, base_size//4)
                        painter_apk.drawLine(base_size*2//3, base_size//8, base_size*3//4, base_size//4)
                        painter_apk.setPen(Qt.NoPen)
                        if icon_data:
                            loaded = False
                            try:
                                icon_pix = QPixmap()
                                if icon_pix.loadFromData(icon_data):
                                    loaded = True
                                    print(f'[APK-ICON] QPixmap.loadFromData succeeded for {chosen_name} ({len(icon_data)} bytes)')
                                else:
                                    print(f'[APK-ICON] QPixmap.loadFromData returned null for {chosen_name}, attempting Pillow fallback')
                            except Exception as e:
                                print(f'[APK-ICON] QPixmap.loadFromData exception for {chosen_name}: {e}')

                            if not loaded:
                                # Try Pillow fallback: convert webp or other bytes to PNG bytes
                                try:
                                    from PIL import Image
                                    buf = BytesIO(icon_data)
                                    img = Image.open(buf)
                                    img = img.convert('RGBA')
                                    out = BytesIO()
                                    img.save(out, format='PNG')
                                    png_bytes = out.getvalue()
                                    icon_pix = QPixmap()
                                    if icon_pix.loadFromData(png_bytes):
                                        loaded = True
                                        print(f'[APK-ICON] Pillow fallback succeeded for {chosen_name} (converted to PNG)')
                                except Exception as e:
                                    print(f'[APK-ICON] Pillow fallback failed for {chosen_name}: {e}')

                            if loaded and not icon_pix.isNull():
                                try:
                                    icon_pix = icon_pix.scaled(base_size*3//4, base_size*3//4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                    x = (base_size - icon_pix.width()) // 2
                                    y = (base_size - icon_pix.height()) // 2
                                    painter_apk.drawPixmap(x, y, icon_pix)
                                except Exception as e:
                                    print(f'[APK-ICON] Error drawing icon_pix for {full_path}: {e}')
                        else:
                            print(f'[APK-ICON] No direct icon_data extracted for {full_path} (chosen_name={chosen_name}), attempting adaptive icon resolution')
                            # Try to resolve adaptive icons: parse res XML files for foreground/background drawables
                            try:
                                from xml.etree import ElementTree as ET
                                from io import BytesIO as _BytesIO
                                try:
                                    from PIL import Image as _Image
                                except Exception:
                                    _Image = None
                                found_adaptive = False
                                with zipfile.ZipFile(full_path, 'r') as z2:
                                    # Scan all res/*.xml files (some adaptive XMLs use short names like gl.xml)
                                    xml_candidates = [n for n in z2.namelist() if n.lower().startswith('res/') and n.lower().endswith('.xml')]
                                    if xml_candidates:
                                        print(f'[APK-ICON] XML candidates scanning count={len(xml_candidates)} (showing up to 10): {xml_candidates[:10]}')
                                    for xmln in xml_candidates:
                                        try:
                                            xmlbytes = z2.read(xmln)
                                            # Some xml resources in APKs are binary XML; try to decode as utf-8, else skip
                                            try:
                                                xml_text = xmlbytes.decode('utf-8', errors='ignore')
                                            except Exception:
                                                xml_text = None
                                            if not xml_text:
                                                # try to parse as XML anyway
                                                try:
                                                    root = ET.fromstring(xmlbytes)
                                                except Exception:
                                                    continue
                                            else:
                                                try:
                                                    root = ET.fromstring(xml_text)
                                                except Exception:
                                                    # fall back to text-based regex extraction
                                                    root = None
                                        except Exception:
                                            continue
                                        fg_ref = None
                                        bg_ref = None
                                        # If we have an XML tree, scan attributes for references like @drawable/name or @mipmap/name
                                        if root is not None:
                                            for elem in root.iter():
                                                for attrname, val in list(elem.attrib.items()):
                                                    if not val or not isinstance(val, str):
                                                        continue
                                                    if val.startswith('@'):
                                                        lname = val.lower()
                                                        if 'foreground' in attrname.lower() or 'foreground' in lname:
                                                            fg_ref = val
                                                        elif 'background' in attrname.lower() or 'background' in lname:
                                                            bg_ref = val
                                                        else:
                                                            if not fg_ref:
                                                                fg_ref = val
                                        # If xml_text is available, also regex-scan for resource references as a fallback
                                        if ('xml_text' in locals()) and xml_text:
                                            import re
                                            for m in re.finditer(r"@(?:drawable|mipmap|raw)/([A-Za-z0-9_]+)", xml_text):
                                                name = m.group(1)
                                                # prefer to fill fg then bg
                                                if not fg_ref:
                                                    fg_ref = '@drawable/' + name
                                                elif not bg_ref:
                                                    bg_ref = '@drawable/' + name
                                        def resolve_ref(ref):
                                            if not ref:
                                                return None
                                            refname = ref.lstrip('@').split('/')[-1]
                                            # Search for exact filename matches first (res/.../refname.png)
                                            for p in z2.namelist():
                                                lp = p.lower()
                                                if lp.endswith(refname + '.png') or lp.endswith(refname + '.webp'):
                                                    return p
                                            # If not found, try looser match containing the name
                                            for p in z2.namelist():
                                                lp = p.lower()
                                                if refname in os.path.basename(lp):
                                                    if lp.endswith(('.png', '.webp')):
                                                        return p
                                            return None
                                        fg_path = resolve_ref(fg_ref)
                                        bg_path = resolve_ref(bg_ref)
                                        if fg_path or bg_path:
                                            print(f'[APK-ICON] adaptive xml {xmln} references fg={fg_path} bg={bg_path}')
                                            if _Image is None:
                                                print('[APK-ICON] Pillow not available; cannot compose adaptive icon, skipping')
                                            else:
                                                try:
                                                    # Load background and foreground images if available
                                                    bg_img = None
                                                    fg_img = None
                                                    if bg_path:
                                                        try:
                                                            bg_img = _Image.open(_BytesIO(z2.read(bg_path))).convert('RGBA')
                                                        except Exception:
                                                            bg_img = None
                                                    if fg_path:
                                                        try:
                                                            fg_img = _Image.open(_BytesIO(z2.read(fg_path))).convert('RGBA')
                                                        except Exception:
                                                            fg_img = None
                                                    if fg_img or bg_img:
                                                        # Ensure both images exist and are base_size x base_size
                                                        if not bg_img and fg_img:
                                                            bg_img = _Image.new('RGBA', fg_img.size, (0,0,0,0))
                                                        bg_img = bg_img.resize((base_size, base_size), _Image.LANCZOS)
                                                        if fg_img:
                                                            fg_img = fg_img.resize((base_size, base_size), _Image.LANCZOS)
                                                            bg_img.paste(fg_img, (0,0), fg_img)
                                                        outbuf = _BytesIO()
                                                        bg_img.save(outbuf, format='PNG')
                                                        png_bytes = outbuf.getvalue()
                                                        icon_pix = QPixmap()
                                                        if icon_pix.loadFromData(png_bytes):
                                                            loaded = True
                                                            print(f'[APK-ICON] Composed adaptive icon from {xmln} succeeded')
                                                            icon_pix = icon_pix.scaled(base_size*3//4, base_size*3//4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                                            x = (base_size - icon_pix.width()) // 2
                                                            y = (base_size - icon_pix.height()) // 2
                                                            painter_apk.drawPixmap(x, y, icon_pix)
                                                            found_adaptive = True
                                                            break
                                                except Exception as e_ad:
                                                    print(f'[APK-ICON] adaptive compose failed for {xmln}: {e_ad}')
                                        # end xmln loop
                                    if not found_adaptive:
                                        print(f'[APK-ICON] adaptive icon resolution found nothing for {full_path}')
                            except Exception as e_ad_outer:
                                print(f'[APK-ICON] adaptive icon parsing failed for {full_path}: {e_ad_outer}')
                        painter_apk.end()
                        painter.end()
                        # If no icon overlay was drawn, log that we're returning the base robot only
                        if not icon_data:
                            print(f'[APK-ICON] No overlay icon applied for {full_path}; returning base Android robot thumbnail')

                        # Cache the APK thumbnail if cache is available
                        try:
                            if getattr(self, 'thumbnail_cache', None):
                                from PyQt5.QtCore import QBuffer
                                buf = QBuffer()
                                buf.open(QBuffer.ReadWrite)
                                base_pixmap.save(buf, 'PNG')
                                png_bytes = buf.data().data()
                                self.thumbnail_cache.put(full_path, size, png_bytes)
                                thumbnail_info('[APK-ICON] Cached APK thumbnail for {} ({} bytes)', full_path, len(png_bytes))
                        except Exception as e_cache:
                            thumbnail_error('[APK-ICON] Caching APK thumbnail failed: {}', e_cache)
                        return base_pixmap
                    except Exception as e_apk:
                        print(f'[APK-ICON] APK overlay failed for {full_path}: {e_apk}')
                        # fall back to normal handling

                # Check for cached text/PDF/DOCX thumbnail
                text_exts = {'.txt', '.md', '.log', '.ini', '.csv', '.json', '.xml', '.py', '.c', '.cpp', '.h', '.java', '.js', '.html', '.css'}
                pdf_exts = {'.pdf'}
                docx_exts = {'.docx', '.doc'}
                audio_exts = {'.wav', '.mp3', '.flac', '.ogg', '.oga', '.aac', '.m4a', '.wma', '.opus', '.aiff', '.alac'}
                # Now include audio_exts in the cache lookup and drawing block
                if self.thumbnail_cache and (file_ext in text_exts or file_ext in pdf_exts or file_ext in docx_exts or file_ext in audio_exts):
                    thumbnail_debug('Entered text/pdf/docx/audio cache/painter block for {}', full_path)
                    cached_thumb = self.thumbnail_cache.get(full_path, size)
                    thumbnail_debug('After cache get for {}, cached_thumb type: {}', full_path, type(cached_thumb))
                    pixmap = None
                    if cached_thumb:
                        thumbnail_debug('Using cached text/pdf/docx/audio thumbnail for {}', full_path)
                        if isinstance(cached_thumb, bytes):
                            pixmap = QPixmap()
                            pixmap.loadFromData(cached_thumb, 'PNG')
                            thumbnail_debug('Loaded pixmap from bytes for {}, isNull={}', full_path, pixmap.isNull())
                        else:
                            pixmap = cached_thumb
                            thumbnail_debug('Loaded pixmap from QPixmap for {}, isNull={}', full_path, pixmap.isNull())
                    # If not cached and is a supported audio file, generate and cache on the fly
                    supported_audio_exts = ['.wav', '.flac', '.ogg', '.aiff', '.aif', '.aifc', '.au', '.snd', '.sf', '.caf', '.mp3', '.oga', '.aac', '.m4a', '.wma', '.opus', '.alac']
                    if not pixmap and file_ext in supported_audio_exts:
                        thumbnail_debug('No cached waveform for {}, generating on the fly', full_path)
                        try:
                            thumbnail_debug('Calling get_waveform_thumbnail for: {}', full_path)
                            pixmap = get_waveform_thumbnail(full_path, width=size, height=size, thumbnail_cache=self.thumbnail_cache)
                            if not pixmap.isNull():
                                # Save to cache as PNG bytes
                                from PyQt5.QtCore import QBuffer, QByteArray
                                buffer = QBuffer()
                                buffer.open(QBuffer.ReadWrite)
                                pixmap.save(buffer, 'PNG')
                                png_bytes = buffer.data().data()
                                self.thumbnail_cache.put(full_path, size, png_bytes)
                                thumbnail_debug('Cached waveform thumbnail for {} after on-the-fly gen', full_path)
                        except Exception as e:
                            thumbnail_error('Failed to generate waveform for {} in icon view: {}', full_path, e)
                    if pixmap and not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                        painter.drawPixmap(0, 0, pixmap)
                        painter.end()
                        thumbnail_debug('Returning framed_pixmap for {} (valid cached pixmap or on-the-fly)', full_path)
                        return framed_pixmap
                    else:
                        thumbnail_debug('Cached pixmap for {} is invalid or not found, drawing default icon', full_path)
                        self.draw_default_file_icon(painter, full_path, size)
                        painter.end()
                        thumbnail_debug('Returning framed_pixmap for {} (default icon)', full_path)
                        return framed_pixmap
                if ArchiveManager.is_archive(full_path):
                    self.draw_archive_icon(painter, full_path, size)
                elif file_ext == '.exe' and not is_dir:
                    # Use real EXE icon
                    try:
                        icon = get_exe_icon_qicon(full_path, size)
                        if not icon.isNull():
                            pixmap = icon.pixmap(size, size)
                            painter.drawPixmap(0, 0, pixmap)
                        else:
                            self.draw_default_file_icon(painter, full_path, size)
                    except Exception as e:
                        thumbnail_error('[EXE-ICON] Error drawing icon for {}: {}', full_path, e)
                        self.draw_default_file_icon(painter, full_path, size)
                elif file_ext in image_extensions and self.is_safe_image_file(full_path):
                    try:
                        if file_ext == '.xcf':
                            try:
                                from PIL import Image
                                import tempfile
                                with Image.open(full_path) as img:
                                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                                        img.save(tmp.name, 'PNG')
                                        png_path = tmp.name
                                original_pixmap = QPixmap(png_path)
                                # Optionally, clean up temp png if needed
                                # os.remove(png_path)
                            except Exception as e:
                                thumbnail_debug('XCF thumbnail error for {}: {}', full_path, e)
                                original_pixmap = QPixmap()
                        else:
                            original_pixmap = QPixmap(full_path)
                        if not original_pixmap.isNull() and original_pixmap.width() > 0 and original_pixmap.height() > 0:
                            thumbnail = original_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            x = (size - thumbnail.width()) // 2
                            y = (size - thumbnail.height()) // 2
                            painter.drawPixmap(x, y, thumbnail)
                            pen = QPen(Qt.lightGray, 1)
                            painter.setPen(pen)
                            painter.drawRect(x, y, thumbnail.width() - 1, thumbnail.height() - 1)
                        else:
                            self.draw_default_file_icon(painter, full_path, size)
                    except Exception:
                        self.draw_default_file_icon(painter, full_path, size)
                elif file_ext in {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}:
                    thumbnail_debug('Entered video thumbnail code for {} (ext={})', full_path, file_ext)
                    import sys
                    if sys.platform == 'darwin':
                        # On macOS, use cache if available, else generate on demand (with robust display fallback)
                        cached_thumb = self.thumbnail_cache.get(full_path, size) if self.thumbnail_cache else None
                        if cached_thumb:
                            thumbnail_debug('Using cached video thumbnail for {}', full_path)
                            if isinstance(cached_thumb, bytes):
                                pixmap = QPixmap()
                                pixmap.loadFromData(cached_thumb, 'PNG')
                                thumbnail_debug('Loaded pixmap from bytes for {}, isNull={}', full_path, pixmap.isNull())
                            else:
                                pixmap = cached_thumb
                                thumbnail_debug('Loaded pixmap from QPixmap for {}, isNull={}', full_path, pixmap.isNull())
                            if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                                painter.drawPixmap(0, 0, pixmap)
                                painter.end()
                                thumbnail_debug('Returning framed_pixmap for {} (valid cached video pixmap)', full_path)
                                return framed_pixmap
                            else:
                                thumbnail_debug('Cached video pixmap for {} is invalid, drawing default icon', full_path)
                                self.draw_default_file_icon(painter, full_path, size)
                                painter.end()
                                thumbnail_debug('Returning framed_pixmap for {} (default icon)', full_path)
                                return framed_pixmap
                        # If not cached, generate on demand (like other platforms)
                        thumbnail_debug('No cached video thumbnail for {}, generating on demand', full_path)
                        try:
                            import shutil
                            ffmpeg_path = shutil.which('ffmpeg')
                            if not ffmpeg_path:
                                thumbnail_debug('ffmpeg not found in PATH for {}', full_path)
                                self.draw_default_file_icon(painter, full_path, size)
                                painter.end()
                                return framed_pixmap
                            import ffmpeg
                            from PIL import Image
                            import tempfile
                            import threading
                            import time
                            thumb_result = {'success': False, 'path': None, 'error': None}
                            def ffmpeg_thumb():
                                try:
                                    thumbnail_debug('Running ffmpeg.probe on {}', full_path)
                                    probe = ffmpeg.probe(full_path)
                                    duration = float(probe['format']['duration'])
                                    seek_time = max(duration * 0.1, 1.0)
                                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                                        tmp_path = tmp.name
                                    thumbnail_debug('Extracting frame at {}s to {}', seek_time, tmp_path)
                                    (
                                        ffmpeg
                                        .input(full_path, ss=seek_time)
                                        .output(tmp_path, vframes=1, format='image2', vcodec='mjpeg')
                                        .overwrite_output()
                                        .run(quiet=True)
                                    )
                                    thumb_result['success'] = True
                                    thumb_result['path'] = tmp_path
                                except Exception as e:
                                    thumbnail_error('ffmpeg error: {}', e)
                                    thumb_result['error'] = str(e)
                            thread = threading.Thread(target=ffmpeg_thumb)
                            thread.start()
                            thread.join(timeout=5)
                            if thread.is_alive():
                                thumbnail_debug('ffmpeg thread timeout for {}', full_path)
                                thumb_result['error'] = 'timeout'
                            if thumb_result['success'] and thumb_result['path']:
                                try:
                                    thumbnail_debug('Opening image {}', thumb_result['path'])
                                    img = Image.open(thumb_result['path'])
                                    img = img.convert('RGBA').resize((size, size), Image.LANCZOS)
                                    img.save(thumb_result['path'], 'PNG')
                                    video_pixmap = QPixmap(thumb_result['path'])
                                    if video_pixmap.isNull():
                                        # Fallback: try QImage then convert to QPixmap
                                        from PyQt5.QtGui import QImage
                                        img_fallback = QImage(thumb_result['path'])
                                        if not img_fallback.isNull():
                                            video_pixmap = QPixmap.fromImage(img_fallback)
                                            thumbnail_debug('QImage fallback succeeded for {}', full_path)
                                        else:
                                            thumbnail_debug('QImage fallback also failed for {}', full_path)
                                    os.remove(thumb_result['path'])
                                    if not video_pixmap.isNull():
                                        thumbnail_debug('Successfully drew thumbnail for {}', full_path)
                                        painter.drawPixmap(0, 0, video_pixmap)
                                    else:
                                        thumbnail_debug('QPixmap is null for {}', full_path)
                                        self.draw_default_file_icon(painter, full_path, size)
                                except Exception as e:
                                    thumbnail_error('PIL/QPixmap error: {}', e)
                                    self.draw_default_file_icon(painter, full_path, size)
                            else:
                                thumbnail_debug('Thumbnail extraction failed for {}: {}', full_path, thumb_result['error'])
                                self.draw_default_file_icon(painter, full_path, size)
                        except Exception as e:
                            thumbnail_error('Exception in macOS video thumbnail code for {}: {}', full_path, e)
                            self.draw_default_file_icon(painter, full_path, size)
                        painter.end()
                        return framed_pixmap
                    # All other platforms: use cache if available, else generate on demand
                    # ...existing code for Linux/Windows video thumbnail extraction...
                    try:
                        if sys.platform.startswith('linux'):
                            print(f'[THUMBNAIL-DEBUG] Platform is Linux, using PyAV for {full_path}')
                            try:
                                print(f'[THUMBNAIL-DEBUG] PyAV: Opening {full_path}')
                                import av
                                from PIL import Image
                                import numpy as np
                                import tempfile
                                container = av.open(full_path)
                                video_streams = [s for s in container.streams if s.type == 'video']
                                if not video_streams:
                                    print(f'[THUMBNAIL-DEBUG] PyAV: No video streams found in {full_path}')
                                    self.draw_default_file_icon(painter, full_path, size)
                                    return
                                stream = video_streams[0]
                                print(f'[THUMBNAIL-DEBUG] PyAV: Using stream {stream.index}, duration={stream.duration}, time_base={stream.time_base}')
                                seek_time = max(float(stream.duration * stream.time_base) * 0.1, 1.0) if stream.duration else 1.0
                                print(f'[THUMBNAIL-DEBUG] PyAV: Seeking to {seek_time}s')
                                container.seek(int(seek_time / stream.time_base), any_frame=False, backward=True, stream=stream)
                                frame = next(container.decode(stream), None)
                                if frame is None:
                                    print(f'[THUMBNAIL-DEBUG] PyAV: No frame decoded for {full_path}')
                                    self.draw_default_file_icon(painter, full_path, size)
                                    return
                                print(f'[THUMBNAIL-DEBUG] PyAV: Got frame for {full_path}')
                                img = frame.to_image().convert('RGBA').resize((size, size), Image.LANCZOS)
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                                    img.save(tmp.name, 'PNG')
                                    video_pixmap = QPixmap(tmp.name)
                                if not video_pixmap.isNull():
                                    print(f'[THUMBNAIL-DEBUG] PyAV: Successfully drew thumbnail for {full_path}')
                                    painter.drawPixmap(0, 0, video_pixmap)
                                else:
                                    print(f'[THUMBNAIL-DEBUG] PyAV QPixmap is null for {full_path}')
                                    self.draw_default_file_icon(painter, full_path, size)
                            except Exception as e:
                                print(f'[THUMBNAIL-DEBUG] PyAV error: {e}')
                                self.draw_default_file_icon(painter, full_path, size)
                        else:
                            print(f'[THUMBNAIL-DEBUG] Platform is not Linux, using ffmpeg-python for {full_path}')
                            import shutil
                            ffmpeg_path = shutil.which('ffmpeg')
                            if not ffmpeg_path:
                                print(f'[THUMBNAIL-DEBUG] ffmpeg not found in PATH for {full_path}')
                                if 'painter' in locals() and painter is not None:
                                    self.draw_default_file_icon(painter, full_path, size)
                                # Ensure we do not proceed further to avoid segfaults
                                return
                            import ffmpeg
                            from PIL import Image
                            import tempfile
                            import threading
                            import time
                            thumb_result = {'success': False, 'path': None, 'error': None}
                            def ffmpeg_thumb():
                                try:
                                    print(f'[THUMBNAIL-DEBUG] Running ffmpeg.probe on {full_path}')
                                    probe = ffmpeg.probe(full_path)
                                    duration = float(probe['format']['duration'])
                                    seek_time = max(duration * 0.1, 1.0)
                                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                                        tmp_path = tmp.name
                                    print(f'[THUMBNAIL-DEBUG] Extracting frame at {seek_time}s to {tmp_path}')
                                    (
                                        ffmpeg
                                        .input(full_path, ss=seek_time)
                                        .output(tmp_path, vframes=1, format='image2', vcodec='mjpeg')
                                        .overwrite_output()
                                        .run(quiet=True)
                                    )
                                    thumb_result['success'] = True
                                    thumb_result['path'] = tmp_path
                                except Exception as e:
                                    print(f'[THUMBNAIL-DEBUG] ffmpeg error: {e}')
                                    thumb_result['error'] = str(e)
                            thread = threading.Thread(target=ffmpeg_thumb)
                            thread.start()
                            thread.join(timeout=5)
                            if thread.is_alive():
                                print(f'[THUMBNAIL-DEBUG] ffmpeg thread timeout for {full_path}')
                                thumb_result['error'] = 'timeout'
                            if thumb_result['success'] and thumb_result['path']:
                                try:
                                    print(f'[THUMBNAIL-DEBUG] Opening image {thumb_result["path"]}')
                                    img = Image.open(thumb_result['path'])
                                    img = img.convert('RGBA').resize((size, size), Image.LANCZOS)
                                    img.save(thumb_result['path'], 'PNG')
                                    video_pixmap = QPixmap(thumb_result['path'])
                                    os.remove(thumb_result['path'])
                                    if not video_pixmap.isNull():
                                        print(f'[THUMBNAIL-DEBUG] Successfully drew thumbnail for {full_path}')
                                        painter.drawPixmap(0, 0, video_pixmap)
                                    else:
                                        print(f'[THUMBNAIL-DEBUG] QPixmap is null for {full_path}')
                                        self.draw_default_file_icon(painter, full_path, size)
                                except Exception as e:
                                    print(f'[THUMBNAIL-DEBUG] PIL/QPixmap error: {e}')
                                    self.draw_default_file_icon(painter, full_path, size)
                            else:
                                print(f'[THUMBNAIL-DEBUG] Thumbnail extraction failed for {full_path}: {thumb_result["error"]}')
                                self.draw_default_file_icon(painter, full_path, size)
                    except Exception as e:
                        print(f'[THUMBNAIL-DEBUG] Exception in thumbnail code for {full_path}: {e}')
                        self.draw_default_file_icon(painter, full_path, size)
                else:
                    self.draw_default_file_icon(painter, full_path, size)
        except Exception:
            self.draw_generic_file_icon(painter, size, is_dir)
        painter.end()
        # Only cache generic icons for file types that are not text, PDF, DOCX, or audio
        text_exts = {'.txt', '.md', '.log', '.ini', '.csv', '.json', '.xml', '.py', '.c', '.cpp', '.h', '.java', '.js', '.html', '.css'}
        pdf_exts = {'.pdf'}
        docx_exts = {'.docx', '.doc'}
        audio_exts = {'.wav', '.mp3', '.flac', '.ogg', '.oga', '.aac', '.m4a', '.wma', '.opus', '.aiff', '.alac'}
        file_ext = os.path.splitext(full_path)[1].lower()
        if self.thumbnail_cache and not is_dir and file_ext not in text_exts | pdf_exts | docx_exts | audio_exts:
            self.thumbnail_cache.put(full_path, size, framed_pixmap)
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
                filename = os.path.basename(file_path)
                if (filename.startswith('._') or  # Resource forks
                    filename == '.DS_Store' or    # Finder metadata
                    filename == '.localized' or   # Localization files
                    filename.startswith('.fseventsd') or  # File system events
                    filename.startswith('.Spotlight-') or  # Spotlight index
                    filename.startswith('.Trashes') or     # Trash metadata
                    filename == '.com.apple.timemachine.donotpresent' or  # Time Machine
                    filename.endswith('.apdisk')):  # AirPort Disk metadata
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
        """Draw only the default system file icon, with no overlays or Windows logo, for all drives and files."""
        try:
            if PlatformUtils.is_windows():
                icon_provider = QFileIconProvider()
                file_info = QFileInfo(full_path)
                icon = icon_provider.icon(file_info)
                preferred_sizes = [256, 128, 64, 48, 32, 16]
                best_pixmap = None
                for icon_size in preferred_sizes:
                    file_pixmap = icon.pixmap(icon_size, icon_size)
                    if not file_pixmap.isNull() and file_pixmap.width() > 0 and file_pixmap.height() > 0:
                        best_pixmap = file_pixmap
                        break
                if best_pixmap:
                    if best_pixmap.width() != size or best_pixmap.height() != size:
                        best_pixmap = best_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    x = (size - best_pixmap.width()) // 2
                    y = (size - best_pixmap.height()) // 2
                    painter.drawPixmap(x, y, best_pixmap)
                    return
            else:
                icon_provider = QFileIconProvider()
                icon = icon_provider.icon(QFileInfo(full_path))
                if not icon.isNull():
                    preferred_sizes = [size * 2, size, 128, 64, 48, 32, 16]
                    for icon_size in preferred_sizes:
                        file_pixmap = icon.pixmap(icon_size, icon_size)
                        if not file_pixmap.isNull() and file_pixmap.width() > 0 and file_pixmap.height() > 0:
                            if file_pixmap.width() != size or file_pixmap.height() != size:
                                file_pixmap = file_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            x = (size - file_pixmap.width()) // 2
                            y = (size - file_pixmap.height()) // 2
                            painter.drawPixmap(x, y, file_pixmap)
                            return
        except Exception as e:
            print(f"Error getting system icon for {full_path}: {e}")
        self.draw_generic_file_icon(painter, size, False)
    
    def try_windows_icon_extraction(self, painter, full_path, size):
        """Try to extract Windows shell icons using various methods"""
        if not PlatformUtils.is_windows():
            return False
        
        try:
            # Method 1: Try using file extension-based icon lookup
            import os.path
            file_ext = os.path.splitext(full_path)[1].lower()
            
            if file_ext:
                try:
                    # Get the icon based on file extension with better size handling
                    icon_provider = QFileIconProvider()
                    
                    # Create a temporary file info with the same extension
                    temp_info = QFileInfo(f"temp{file_ext}")
                    type_icon = icon_provider.icon(temp_info)
                    
                    if not type_icon.isNull():
                        # Try multiple sizes to get the best quality
                        preferred_sizes = [256, 128, 64, 48, 32, 16]
                        best_pixmap = None
                        
                        for icon_size in preferred_sizes:
                            icon_pixmap = type_icon.pixmap(icon_size, icon_size)
                            if not icon_pixmap.isNull() and icon_pixmap.width() > 0:
                                best_pixmap = icon_pixmap
                                break
                        
                        if best_pixmap:
                            # Always scale to the exact requested size
                            if best_pixmap.width() != size or best_pixmap.height() != size:
                                best_pixmap = best_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            
                            x = (size - best_pixmap.width()) // 2
                            y = (size - best_pixmap.height()) // 2
                            painter.drawPixmap(x, y, best_pixmap)
                            return True
                except Exception as e:
                    print(f"Extension-based icon extraction failed for {file_ext}: {e}")
            
            # Method 2: Try using Windows registry/system associations
            try:
                # Alternative approach: try to get system icon through different means
                icon_provider = QFileIconProvider()
                
                # Try getting icon for the actual file if it exists
                if os.path.exists(full_path):
                    file_info = QFileInfo(full_path)
                    system_icon = icon_provider.icon(file_info)
                    
                    if not system_icon.isNull():
                        # Use the same multi-size approach
                        preferred_sizes = [256, 128, 64, 48, 32, 16]
                        
                        for icon_size in preferred_sizes:
                            sys_pixmap = system_icon.pixmap(icon_size, icon_size)
                            if not sys_pixmap.isNull() and sys_pixmap.width() > 0:
                                # Scale to exact requested size
                                if sys_pixmap.width() != size or sys_pixmap.height() != size:
                                    sys_pixmap = sys_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                
                                x = (size - sys_pixmap.width()) // 2
                                y = (size - sys_pixmap.height()) // 2
                                painter.drawPixmap(x, y, sys_pixmap)
                                return True
            except Exception as e:
                print(f"System icon extraction failed: {e}")
            
            return False
            
        except Exception as e:
            print(f"Windows icon extraction failed: {e}")
            return False
    
    def draw_archive_icon(self, painter, archive_path, size):
        """Draw a custom icon for archive files"""
        try:
            # Backwards-compatible: allow callers to force the enhanced/custom archive
            # rendering (useful for thumbnail mode where we prefer richer ISO thumbnails)
            force_custom = False
            try:
                # If caller passed a 4th arg, it'll be available in locals(); tolerate absence
                force_custom = locals().get('force_custom', False)
            except Exception:
                force_custom = False
            archive_type = ArchiveManager.get_archive_type(archive_path)
            if force_custom and archive_type == '.iso':
                try:
                    self.draw_custom_archive_icon(painter, archive_path, size)
                    return
                except Exception:
                    # Fall through to normal handling on error
                    pass
            # Try to get system icon first
            icon_provider = QFileIconProvider()
            file_info = QFileInfo(archive_path)
            icon = icon_provider.icon(file_info)
            
            if not icon.isNull():
                file_pixmap = icon.pixmap(size, size)
                if not file_pixmap.isNull():
                    painter.drawPixmap(0, 0, file_pixmap)
                    # Only add archive overlay if not a drive root (e.g., not C:/)
                    import os
                    # Heuristic: skip overlay for drive roots
                    if not (os.name == 'nt' and len(archive_path) >= 2 and archive_path[1] == ':' and (archive_path.endswith('/') or archive_path.endswith('\\')) and os.path.ismount(archive_path)):
                        self.draw_archive_overlay(painter, size)
                    return
            
            # Fallback: draw custom archive icon
            self.draw_custom_archive_icon(painter, archive_path, size)
            
        except Exception:
            # Ultimate fallback
            self.draw_custom_archive_icon(painter, archive_path, size)
    
    def draw_archive_overlay(self, painter, size):
        """Draw a small overlay to indicate this is an archive"""
        overlay_size = size // 4
        x = size - overlay_size - 2
        y = size - overlay_size - 2
        
        # Draw small archive symbol (like a box with lines)
        painter.setPen(QPen(Qt.darkBlue, 2))
        painter.setBrush(Qt.lightGray)
        painter.drawRect(x, y, overlay_size, overlay_size)
        
        # Draw horizontal lines to represent files
        line_y = y + overlay_size // 4
        for i in range(3):
            painter.drawLine(x + 2, line_y, x + overlay_size - 2, line_y)
            line_y += overlay_size // 4
    
    def draw_custom_archive_icon(self, painter, archive_path, size):
        """Draw a custom archive icon when system icon is not available"""
        archive_type = ArchiveManager.get_archive_type(archive_path)
        
        # Set colors based on archive type
        if archive_type == '.zip':
            fill_color = QColor(255, 215, 0)  # Gold
            border_color = QColor(184, 134, 11)  # Dark gold
        elif archive_type in ['.tar', '.tar.gz', '.tgz']:
            fill_color = QColor(139, 69, 19)  # Saddle brown
            border_color = QColor(101, 51, 14)  # Dark brown
        elif archive_type == '.rar':
            fill_color = QColor(128, 0, 128)  # Purple
            border_color = QColor(75, 0, 130)  # Indigo
        elif archive_type == '.iso':
            # Try to extract EXE icon from ISO for thumbnail
            # First, check if the ISO contains any EXE candidates so we can decide
            # whether to show a default EXE icon when extraction fails.
            had_exe = False
            try:
                s, entries_or_err = ArchiveManager.list_archive_contents(archive_path)
                if s:
                    exe_candidates = [e for e in entries_or_err if (not e.get('is_dir')) and e['name'].lower().endswith('.exe')]
                    if exe_candidates:
                        had_exe = True
            except Exception:
                had_exe = False

            # Prefer to find an image (png/jpg) inside the ISO to overlay on the disc
            img_pix = None
            try:
                cache = get_global_thumbnail_cache()
                # Look for image entries inside the ISO listing
                success, entries_or_err = ArchiveManager.list_archive_contents(archive_path)
                image_entry = None
                if success and entries_or_err:
                    # Improved selection heuristics:
                    # - prefer names containing 'cover' or 'front' or 'folder'
                    # - prefer shallower (root-level) paths
                    # - prefer larger file size when available
                    IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
                    candidates = []
                    for ent in entries_or_err:
                        if ent.get('is_dir'):
                            continue
                        ext = os.path.splitext(ent['name'])[1].lower()
                        if ext in IMAGE_EXTS:
                            candidates.append(ent)
                    if candidates:
                        def _score(ent):
                            name = (ent.get('name') or '').lower()
                            # base score from presence of desirable keywords
                            score = 0
                            if 'cover' in name or 'front' in name or 'folder' in name:
                                score += 2000
                            # prefer root-level (fewer '/')
                            depth = name.count('/')
                            score += max(0, 500 - depth * 50)
                            # prefer larger sizes (if available)
                            try:
                                sz = int(ent.get('size') or 0)
                            except Exception:
                                sz = 0
                            # scale size contribution modestly
                            score += min(sz, 5_000_000) // 1024
                            return score

                        best = max(candidates, key=_score)
                        image_entry = best['name']
                if image_entry:
                    # Prepare cache key based on ISO path + entry + size
                    cache_key_path = f"{archive_path}::{image_entry}"
                    if cache and cache.is_cached(cache_key_path, size):
                        img_pix = cache.get(cache_key_path, size)
                    else:
                        # Extract the image to a temp file then load and cache it
                        import tempfile
                        import pycdlib
                        iso = pycdlib.PyCdlib()
                        try:
                            iso.open(archive_path)
                            tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image_entry)[1])
                            tmpf.close()
                            extracted = False
                            # Build a set of candidate paths for pycdlib to try. pycdlib
                            # can require different forms (leading slash, uppercase,
                            # or ISO version suffix like ';1'), so try variants.
                            candidates = []
                            base = image_entry
                            candidates.append(base)
                            candidates.append(base.lstrip('/'))
                            candidates.append(base.lstrip('/').upper())
                            # Add ';1' version on final segment (with/without leading slash)
                            try:
                                stripped = base.lstrip('/')
                                parts = stripped.split('/')
                                parts_semiv = parts[:-1] + [parts[-1] + ';1']
                                candidates.append('/' + '/'.join(parts_semiv))
                                candidates.append('/' + '/'.join(parts_semiv).upper())
                                candidates.append('/'.join(parts_semiv))
                                candidates.append('/'.join(parts_semiv).upper())
                            except Exception:
                                pass

                            for kw in ('iso_path', 'joliet_path', 'rr_path'):
                                for candidate in candidates:
                                    try:
                                        with open(tmpf.name, 'wb') as out_f:
                                            iso.get_file_from_iso_fp(out_f, **{kw: candidate})
                                        extracted = True
                                        break
                                    except Exception as ex_get:
                                        # If we get a pycdlib parsing error, continue trying
                                        # other candidate forms/namespace keywords.
                                        msg = str(ex_get).lower()
                                        # If the error looks fatal for this candidate, continue
                                        try:
                                            if os.path.exists(tmpf.name):
                                                os.remove(tmpf.name)
                                        except Exception:
                                            pass
                                        continue
                                if extracted:
                                    break
                            iso.close()
                            if extracted and os.path.exists(tmpf.name):
                                try:
                                    from PIL import Image
                                except Exception:
                                    Image = None
                                if Image is None:
                                    img_pix = None
                                else:
                                    img = Image.open(tmpf.name).convert('RGBA')
                                    img = img.resize((size, size), Image.LANCZOS)
                                    # Save to a cache temp PNG and load into QPixmap
                                    cache_tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                                    img.save(cache_tmp.name, 'PNG')
                                    cache_tmp.close()
                                    img_pix = QPixmap(cache_tmp.name)
                                    try:
                                        os.remove(cache_tmp.name)
                                    except Exception:
                                        pass
                                    try:
                                        os.remove(tmpf.name)
                                    except Exception:
                                        pass
                                    if cache and img_pix and not img_pix.isNull():
                                        try:
                                            cache.put(cache_key_path, size, img_pix)
                                        except Exception:
                                            pass
                        except Exception:
                            try:
                                iso.close()
                            except Exception:
                                pass
                            img_pix = None
            except Exception:
                img_pix = None

            # If we obtained an image pixmap, draw disc then overlay
            if img_pix and not getattr(img_pix, 'isNull', lambda: False)():
                try:
                    from PyQt5.QtGui import QRadialGradient
                    center = QPoint(size // 2, size // 2)
                    radius = size // 2 - 4
                    grad = QRadialGradient(center, radius)
                    grad.setColorAt(0.0, QColor(230, 230, 230))
                    grad.setColorAt(0.6, QColor(200, 200, 220))
                    grad.setColorAt(1.0, QColor(160, 160, 200))
                    painter.setBrush(grad)
                    painter.setPen(QPen(QColor(90, 90, 120), 2))
                    painter.drawEllipse(center, radius, radius)
                    # Overlay the image centered with padding
                    padding = max(4, size // 10)
                    target = QRect(padding, padding, size - padding * 2, size - padding * 2)
                    painter.drawPixmap(target, img_pix)
                    return
                except Exception:
                    pass

            # If we didn't find an image inside the ISO, try EXE icon extraction as fallback
            try:
                pixmap = ArchiveManager.extract_exe_icon_from_iso(archive_path, size=size)
                if pixmap and not pixmap.isNull():
                    painter.drawPixmap(0, 0, pixmap)
                    return
            except Exception:
                pass

            # If no image was used, and an EXE exists, draw a default EXE icon
            if had_exe:
                try:
                    default_pix = QPixmap(size, size)
                    default_pix.fill(Qt.transparent)
                    p2 = QPainter(default_pix)
                    p2.setRenderHint(QPainter.Antialiasing)
                    # Background box
                    p2.setBrush(QColor(240, 240, 240))
                    p2.setPen(QPen(QColor(60, 60, 60), 2))
                    rect = QRect(4, 4, size - 8, size - 8)
                    p2.drawRoundedRect(rect, 6, 6)
                    # EXE label
                    font = p2.font()
                    font.setBold(True)
                    font.setPointSize(max(8, size // 6))
                    p2.setFont(font)
                    p2.setPen(QColor(30, 30, 30))
                    p2.drawText(rect, Qt.AlignCenter, 'EXE')
                    p2.end()
                    painter.drawPixmap(0, 0, default_pix)
                    return
                except Exception:
                    # If even this fails, continue to disc fallback
                    pass
            # (Duplicate image-extraction block removed: images are attempted above first.)
            # Fallback: draw disc-style icon
            try:
                from PyQt5.QtGui import QRadialGradient
                center = QPoint(size // 2, size // 2)
                radius = size // 2 - 4
                grad = QRadialGradient(center, radius)
                grad.setColorAt(0.0, QColor(230, 230, 230))
                grad.setColorAt(0.6, QColor(200, 200, 220))
                grad.setColorAt(1.0, QColor(160, 160, 200))
                painter.setBrush(grad)
                painter.setPen(QPen(QColor(90, 90, 120), 2))
                painter.drawEllipse(center, radius, radius)
                # Inner shiny ring
                inner_radius = max(6, size // 6)
                painter.setBrush(QColor(240, 240, 255, 200))
                painter.setPen(QPen(QColor(120, 120, 140), 1))
                painter.drawEllipse(center, inner_radius, inner_radius)
                # Small central hole
                hole_radius = max(3, size // 14)
                painter.setBrush(QColor(20, 20, 20))
                painter.drawEllipse(center, hole_radius, hole_radius)
                # Draw 'ISO' label at bottom
                font = painter.font()
                font.setPointSize(max(6, size // 10))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(40, 40, 60))
                painter.drawText(QRect(0, size - size//4, size, size//4), Qt.AlignCenter, 'ISO')
                return
            except Exception:
                # Fallback to generic archive rendering below
                fill_color = QColor(169, 169, 169)  # Dark gray
                border_color = QColor(105, 105, 105)  # Dim gray
        else:
            fill_color = QColor(169, 169, 169)  # Dark gray
            border_color = QColor(105, 105, 105)  # Dim gray
        
        # Draw main archive box
        margin = size // 8
        box_rect = QRect(margin, margin, size - 2 * margin, size - 2 * margin)
        
        painter.setBrush(fill_color)
        painter.setPen(QPen(border_color, 2))
        painter.drawRoundedRect(box_rect, 4, 4)
        
        # Draw "zip" lines pattern
        painter.setPen(QPen(border_color, 1))
        line_spacing = size // 6
        start_y = margin + line_spacing
        
        for i in range(3):
            y = start_y + i * line_spacing
            if y < size - margin:
                painter.drawLine(margin + 4, y, size - margin - 4, y)
        
        # Draw file type label
        if archive_type:
            label = archive_type[1:].upper()  # Remove the dot
            painter.setPen(Qt.white)
            font = painter.font()
            font.setPointSize(max(6, size // 10))
            font.setBold(True)
            painter.setFont(font)
            
            text_rect = QRect(margin, size - margin - size//4, size - 2*margin, size//4)
            painter.drawText(text_rect, Qt.AlignCenter, label)

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
            
            if PlatformUtils.is_windows():
                # On Windows, try to get the actual folder icon for the specific path
                try:
                    folder_info = QFileInfo(folder_path)
                    folder_icon = icon_provider.icon(folder_info)
                except:
                    folder_icon = icon_provider.icon(QFileIconProvider.Folder)
            else:
                folder_icon = icon_provider.icon(QFileIconProvider.Folder)
            
            if not folder_icon.isNull():
                # Try different sizes for better quality at all thumbnail sizes
                preferred_sizes = [256, 128, 64, 48, 32, 16]
                folder_pixmap = None
                
                for icon_size in preferred_sizes:
                    temp_pixmap = folder_icon.pixmap(icon_size, icon_size)
                    if not temp_pixmap.isNull() and temp_pixmap.width() > 0 and temp_pixmap.height() > 0:
                        folder_pixmap = temp_pixmap
                        break
                
                if folder_pixmap:
                    # Always scale to the exact requested size for consistency
                    if folder_pixmap.width() != size or folder_pixmap.height() != size:
                        folder_pixmap = folder_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    
                    # Center and draw the folder icon
                    x = (size - folder_pixmap.width()) // 2
                    y = (size - folder_pixmap.height()) // 2
                    painter.drawPixmap(x, y, folder_pixmap)
                else:
                    # Draw generic folder if system icon fails
                    self.draw_generic_file_icon(painter, size, True)
            else:
                self.draw_generic_file_icon(painter, size, True)
        except Exception as e:
            print(f"Error getting folder icon for {folder_path}: {e}")
            self.draw_generic_file_icon(painter, size, True)
        
        # Try to find previewable files in the folder (image, video, exe)
        try:
            # Supported extensions for previews
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'}
            video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv', '.mpg', '.mpeg', '.3gp'}
            audio_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.oga', '.aac', '.m4a', '.wma', '.opus', '.aiff', '.alac'}
            pdf_extensions = {'.pdf'}
            text_extensions = {'.txt', '.md', '.log', '.ini', '.csv', '.json', '.xml', '.py', '.c', '.cpp', '.h', '.java', '.js', '.html', '.css'}
            docx_extensions = {'.docx', '.doc'}
            exe_extensions = {'.exe'}
            preview_files = []
            files = os.listdir(folder_path)
            # Platform-specific file filtering
            if PlatformUtils.is_macos():
                files = [f for f in files if not f.startswith('.') and not f.startswith('._')]
            elif PlatformUtils.is_windows():
                files = [f for f in files if f.lower() not in ('thumbs.db', 'desktop.ini')]
            else:  # Linux/Unix
                files = [f for f in files if not f.startswith('.')]
            # Limit the number of files scanned for previews to the first 20 for performance
            files = files[:20]
            only_folders = True
            only_isos = True
            only_archives = True
            folder_paths = []
            iso_paths = []
            archive_paths = []
            for file_name in files:
                file_ext = os.path.splitext(file_name)[1].lower()
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):
                    only_folders = False
                    if file_ext == '.iso':
                        iso_paths.append(file_path)
                        # Add ISO as a preview type (after other thumbnails)
                        preview_files.append(('iso', file_path))
                    else:
                        only_isos = False
                    if file_ext in {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2', '.lz', '.lzma', '.z', '.cab', '.arj', '.ace', '.jar'}:
                        archive_paths.append(file_path)
                        preview_files.append(('archive', file_path))
                    else:
                        only_archives = False
                    if file_ext in image_extensions and self.is_safe_image_file(file_path):
                        preview_files.append(('image', file_path))
                    elif file_ext in video_extensions:
                        preview_files.append(('video', file_path))
                    elif file_ext in audio_extensions:
                        preview_files.append(('audio', file_path))
                    elif file_ext in pdf_extensions:
                        preview_files.append(('pdf', file_path))
                    elif file_ext in text_extensions:
                        preview_files.append(('text', file_path))
                    elif file_ext in docx_extensions:
                        preview_files.append(('docx', file_path))
                    elif file_ext in exe_extensions:
                        preview_files.append(('exe', file_path))
                elif os.path.isdir(file_path):
                    only_isos = False
                    only_archives = False
                    folder_paths.append(file_path)
            if only_archives and archive_paths:
                # Composite up to 4 small archive icons
                preview_size = max(8, size // 4)
                positions = [
                    (size - preview_size - 2, 2),
                    (size - preview_size - 2, preview_size + 4),
                    (size - preview_size * 2 - 4, 2),
                    (size - preview_size * 2 - 4, preview_size + 4)
                ]
                icon_provider = QFileIconProvider()
                for i, archive in enumerate(archive_paths[:4]):
                    archive_icon = icon_provider.icon(QFileInfo(archive))
                    if archive_icon.isNull():
                        archive_icon = icon_provider.icon(QFileIconProvider.File)
                    archive_pixmap = archive_icon.pixmap(preview_size, preview_size)
                    pos_x, pos_y = positions[i]
                    painter.drawPixmap(pos_x, pos_y, archive_pixmap)
            elif only_isos and iso_paths:
                # Composite up to 4 small ISO icons
                preview_size = max(8, size // 4)
                positions = [
                    (size - preview_size - 2, 2),
                    (size - preview_size - 2, preview_size + 4),
                    (size - preview_size * 2 - 4, 2),
                    (size - preview_size * 2 - 4, preview_size + 4)
                ]
                # Use a generic CD/DVD icon for ISO, or fallback to exe icon if not available
                icon_provider = QFileIconProvider()
                for i, iso in enumerate(iso_paths[:4]):
                    iso_icon = icon_provider.icon(QFileInfo(iso))
                    if iso_icon.isNull():
                        iso_icon = icon_provider.icon(QFileIconProvider.File)
                    iso_pixmap = iso_icon.pixmap(preview_size, preview_size)
                    pos_x, pos_y = positions[i]
                    painter.drawPixmap(pos_x, pos_y, iso_pixmap)
            elif only_folders and folder_paths:
                # Composite up to 4 small folder icons
                preview_size = max(8, size // 4)
                positions = [
                    (size - preview_size - 2, 2),
                    (size - preview_size - 2, preview_size + 4),
                    (size - preview_size * 2 - 4, 2),
                    (size - preview_size * 2 - 4, preview_size + 4)
                ]
                icon_provider = QFileIconProvider()
                for i, subfolder in enumerate(folder_paths[:4]):
                    try:
                        folder_icon = icon_provider.icon(QFileIconProvider.Folder)
                        folder_pixmap = folder_icon.pixmap(preview_size, preview_size)
                        pos_x, pos_y = positions[i]
                        painter.drawPixmap(pos_x, pos_y, folder_pixmap)
                    except Exception:
                        continue
            elif preview_files:
                preview_size = max(8, size // 4)
                positions = [
                    (size - preview_size - 2, 2),
                    (size - preview_size - 2, preview_size + 4),
                    (size - preview_size * 2 - 4, 2),
                    (size - preview_size * 2 - 4, preview_size + 4)
                ]
                # Compose up to 4: prefer thumbnails, fill with icons if needed
                composited = 0
                used_files = set()
                # 1. Try to composite all available thumbnails first
                for ftype, fpath in preview_files:
                    if composited >= 4:
                        break
                    try:
                        thumbnail = None
                        if ftype == 'image':
                            img_pixmap = QPixmap(fpath)
                            if not img_pixmap.isNull() and img_pixmap.width() > 0 and img_pixmap.height() > 0:
                                thumbnail = img_pixmap.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        elif ftype == 'video':
                            thumb = None
                            if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                                thumb = self.thumbnail_cache.get(fpath, preview_size)
                            if not thumb:
                                try:
                                    from PyQt5.QtMultimedia import QMediaPlayer, QVideoWidget
                                except Exception:
                                    pass
                            if thumb:
                                if isinstance(thumb, (bytes, bytearray)):
                                    img_pixmap = QPixmap()
                                    img_pixmap.loadFromData(thumb, 'PNG')
                                    if not img_pixmap.isNull():
                                        thumbnail = img_pixmap.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                elif isinstance(thumb, QPixmap):
                                    thumbnail = thumb.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            if thumbnail is None:
                                thumbnail = self.create_icon_or_thumbnail(fpath, False)
                        elif ftype == 'audio':
                            thumb = None
                            if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                                thumb = self.thumbnail_cache.get(fpath, preview_size)
                            if not thumb:
                                try:
                                    thumbnail = get_waveform_thumbnail(fpath, width=preview_size, height=preview_size)
                                except Exception:
                                    thumbnail = None
                            if thumb and thumbnail is None:
                                if isinstance(thumb, (bytes, bytearray)):
                                    img_pixmap = QPixmap()
                                    img_pixmap.loadFromData(thumb, 'PNG')
                                    if not img_pixmap.isNull():
                                        thumbnail = img_pixmap.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                elif isinstance(thumb, QPixmap):
                                    thumbnail = thumb.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            if thumbnail is None:
                                thumbnail = self.create_icon_or_thumbnail(fpath, False)
                        elif ftype == 'pdf' or ftype == 'text' or ftype == 'docx':
                            thumb = None
                            if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                                thumb = self.thumbnail_cache.get(fpath, preview_size)
                            if not thumb:
                                try:
                                    thumbnail = self.create_icon_or_thumbnail(fpath, False)
                                except Exception:
                                    thumbnail = None
                            if thumb and thumbnail is None:
                                if isinstance(thumb, (bytes, bytearray)):
                                    img_pixmap = QPixmap()
                                    img_pixmap.loadFromData(thumb, 'PNG')
                                    if not img_pixmap.isNull():
                                        thumbnail = img_pixmap.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                elif isinstance(thumb, QPixmap):
                                    thumbnail = thumb.scaled(preview_size, preview_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            if thumbnail is None:
                                thumbnail = self.create_icon_or_thumbnail(fpath, False)
                        elif ftype == 'exe':
                            icon = get_exe_icon_qicon(fpath, size=preview_size)
                            thumbnail = icon.pixmap(preview_size, preview_size)
                        elif ftype == 'archive':
                            # Use the file type icon for the archive as a thumbnail
                            icon = icon_provider.icon(QFileInfo(fpath))
                            if icon.isNull():
                                icon = icon_provider.icon(QFileIconProvider.File)
                            thumbnail = icon.pixmap(preview_size, preview_size)
                        elif ftype == 'iso':
                            # Try to extract EXE icon from ISO for thumbnail
                            try:
                                thumbnail = ArchiveManager.extract_exe_icon_from_iso(fpath, size=preview_size)
                            except Exception:
                                thumbnail = None
                            if not thumbnail or thumbnail.isNull():
                                icon = icon_provider.icon(QFileInfo(fpath))
                                if icon.isNull():
                                    icon = icon_provider.icon(QFileIconProvider.File)
                                thumbnail = icon.pixmap(preview_size, preview_size)
                        else:
                            continue
                        if thumbnail is not None:
                            preview_frame = QPixmap(preview_size, preview_size)
                            preview_frame.fill(Qt.white)
                            frame_painter = QPainter(preview_frame)
                            frame_painter.setRenderHint(QPainter.Antialiasing)
                            thumb_x = (preview_size - thumbnail.width()) // 2
                            thumb_y = (preview_size - thumbnail.height()) // 2
                            frame_painter.drawPixmap(thumb_x, thumb_y, thumbnail)
                            pen = QPen(Qt.darkGray, 1)
                            frame_painter.setPen(pen)
                            frame_painter.drawRect(0, 0, preview_size - 1, preview_size - 1)
                            frame_painter.end()
                            pos_x, pos_y = positions[composited]
                            painter.drawPixmap(pos_x, pos_y, preview_frame)
                            used_files.add(fpath)
                            composited += 1
                    except Exception:
                        continue
                # 2. Fill remaining slots with icons for other files
                if composited < 4:
                    for file_name in files:
                        if composited >= 4:
                            break
                        file_path = os.path.join(folder_path, file_name)
                        if os.path.isfile(file_path) and file_path not in used_files:
                            icon = icon_provider.icon(QFileInfo(file_path))
                            if icon.isNull():
                                icon = icon_provider.icon(QFileIconProvider.File)
                            icon_pixmap = icon.pixmap(preview_size, preview_size)
                            pos_x, pos_y = positions[composited]
                            painter.drawPixmap(pos_x, pos_y, icon_pixmap)
                            composited += 1
        except Exception:
            pass
        
        painter.end()
        return preview_pixmap

    def mousePressEvent(self, event):
        try:
            icon_container_debug('mousePressEvent button={} pos={} global={} modifiers={}', getattr(event, 'button', lambda: None)(), getattr(event, 'pos', lambda: '<no-pos>')(), getattr(event, 'globalPos', lambda: '<no-global>')(), getattr(event, 'modifiers', lambda: 0)())
        except Exception:
            pass
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.full_path, event.modifiers())
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self.full_path, event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.full_path)
            event.accept()  # Explicitly accept to prevent propagation issues on Linux

    def mousePressEvent(self, event):
        # Record position for potential drag start and emit click signals
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._press_global_pos = event.globalPos()
            # Emit clicked signal for single-click handling
            self.clicked.emit(self.full_path, event.modifiers())
            event.accept()
            return
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self.full_path, event.globalPos())
            event.accept()
            return
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Start drag if moved beyond threshold
        try:
            from PyQt5.QtCore import QUrl, QMimeData
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtGui import QDrag
        except Exception:
            # If imports fail for any reason, fall back to default handling
            super().mouseMoveEvent(event)
            return

        if hasattr(self, '_press_pos') and event.buttons() & Qt.LeftButton:
            dist = (event.pos() - self._press_pos).manhattanLength()
            start_dist = QApplication.startDragDistance()
            print(f"[DRAG-DEBUG] mouseMoveEvent: pos={event.pos()}, press_pos={self._press_pos}, dist={dist}, threshold={start_dist}")
            if dist >= start_dist:
                # Determine selected items (support multi-select)
                container = self.parent()
                while container is not None and not isinstance(container, IconContainer):
                    container = container.parent()
                if container and getattr(container, 'selected_widgets', None):
                    paths = [w.full_path for w in container.selected_widgets]
                else:
                    paths = [self.full_path]

                mime = QMimeData()
                urls = [QUrl.fromLocalFile(p) for p in paths]
                mime.setUrls(urls)
                drag = QDrag(self)
                drag.setMimeData(mime)
                # Set a drag pixmap from the icon for visual feedback
                try:
                    pix = self.icon_label.pixmap()
                    if pix and not pix.isNull():
                        drag_pix = pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        drag.setPixmap(drag_pix)
                except Exception as e:
                    print(f"[DRAG-DEBUG] failed to set drag pixmap: {e}")


                print(f"[DRAG-DEBUG] Starting drag for paths: {paths}")

                # If dragging to browser, use CopyAction. If dragging to a directory in-app, ask user.
                drop_action = Qt.CopyAction
                # Try to detect if the drag is internal (to another directory in the app)
                # If so, ask user whether to Move or Copy
                # This is a heuristic: if QApplication.widgetAt(QCursor.pos()) is an IconContainer, treat as internal
                try:
                    from PyQt5.QtWidgets import QApplication, QMessageBox
                    from PyQt5.QtGui import QCursor
                    widget = QApplication.widgetAt(QCursor.pos())
                    if widget is not None:
                        # Check if it's a directory drop target (IconContainer or similar)
                        # You may need to adjust this type check for your app
                        if widget.__class__.__name__ == "IconContainer":
                            reply = QMessageBox.question(self, "Move or Copy?", "Do you want to Move or Copy the file(s)?", QMessageBox.Move | QMessageBox.Copy, QMessageBox.Move)
                            if reply == QMessageBox.Move:
                                drop_action = Qt.MoveAction
                            else:
                                drop_action = Qt.CopyAction
                except Exception as e:
                    print(f"[DRAG-DEBUG] Could not determine drop target: {e}")

                drag.exec_(drop_action)
                # Clear press pos so we don't restart drag
                try:
                    del self._press_pos
                except Exception:
                    pass
                return

        super().mouseMoveEvent(event)

class IconContainer(QWidget):
    emptySpaceClicked = pyqtSignal()
    emptySpaceRightClicked = pyqtSignal(QPoint)
    selectionChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QGridLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSizeConstraint(QGridLayout.SetMinAndMaxSize)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setLayout(layout)

        # Selection / drag state
        self.drag_start = None
        self.drag_end = None
        self.selection_rect = QRect()
        self.is_dragging = False
        self.selected_widgets = set()
        self.last_width = 0

        # Enable mouse tracking and expandability
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 100)

        # Visual background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.transparent)
        self.setPalette(palette)

        # Auto-scroll timer for selection drag
        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.setInterval(30)
        self.auto_scroll_timer.timeout.connect(self._auto_scroll_during_drag)
        self._auto_scroll_direction = None
        self._auto_scroll_margin = 30
        self._auto_scroll_speed = 20

        # Track press for fallback container-level drags
        self._press_pos = None
        self._press_widget = None

        # Accept drops
        super().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            try:
                self._handle_drag_position(event.pos())
            except Exception:
                pass
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            try:
                self._handle_drag_position(event.pos())
            except Exception:
                pass
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._auto_scroll_direction = None
        try:
            if self.auto_scroll_timer.isActive():
                self.auto_scroll_timer.stop()
        except Exception:
            pass
        event.accept()

    def _handle_drag_position(self, pos):
        parent_scroll = self._get_parent_scroll_area()
        if parent_scroll:
            view_rect = parent_scroll.viewport().rect()
            mapped_pos = self.mapToParent(pos)
            direction = None
            if mapped_pos.y() < self._auto_scroll_margin:
                direction = 'up'
            elif mapped_pos.y() > view_rect.height() - self._auto_scroll_margin:
                direction = 'down'
            elif mapped_pos.x() < self._auto_scroll_margin:
                direction = 'left'
            elif mapped_pos.x() > view_rect.width() - self._auto_scroll_margin:
                direction = 'right'

            if direction:
                self._auto_scroll_direction = direction
                if not self.auto_scroll_timer.isActive():
                    self.auto_scroll_timer.start()
            else:
                self._auto_scroll_direction = None
                if self.auto_scroll_timer.isActive():
                    self.auto_scroll_timer.stop()
        else:
            self._auto_scroll_direction = None
            if self.auto_scroll_timer.isActive():
                self.auto_scroll_timer.stop()

    def dropEvent(self, event):
        import os
        if event.mimeData().hasUrls():
            drop_pos = event.pos()
            candidate = self.childAt(drop_pos)
            target_widget = candidate
            while target_widget is not None and not hasattr(target_widget, 'full_path'):
                if target_widget is self:
                    target_widget = None
                    break
                target_widget = target_widget.parent()

            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            print(f"[DROP-DEBUG] dropEvent: pos={drop_pos}, candidate={getattr(candidate, '__class__', None)}, resolved_target={getattr(target_widget, 'full_path', None)}, paths={paths}")

            if target_widget is not None and os.path.isdir(getattr(target_widget, 'full_path', '')):
                for src_path in paths:
                    try:
                        if not src_path:
                            continue
                        if not os.path.exists(src_path):
                            print(f"[DROP-DEBUG] source does not exist: {src_path}")
                            continue
                        dest_path = os.path.join(target_widget.full_path, os.path.basename(src_path))
                        if os.path.exists(dest_path):
                            base, ext = os.path.splitext(dest_path)
                            i = 1
                            new_dest = f"{base} ({i}){ext}"
                            while os.path.exists(new_dest):
                                i += 1
                                new_dest = f"{base} ({i}){ext}"
                            dest_path = new_dest
                        # If moving a folder into itself or its subfolder, block and warn
                        if os.path.isdir(src_path):
                            abs_src = os.path.abspath(src_path)
                            abs_dest = os.path.abspath(dest_path)
                            if abs_dest.startswith(abs_src + os.sep):
                                print(f"[DROP-ERROR] Cannot move folder into itself or subfolder: {src_path} -> {dest_path}")
                                continue
                        fast_move(src_path, dest_path)
                        print(f"[DROP-DEBUG] moved {src_path} -> {dest_path}")
                    except Exception as e:
                        print(f"[DROP-ERROR] Failed to move {src_path} to {dest_path}: {e}")

                # Refresh view (FileManagerTab)
                ancestor = self.parent()
                while ancestor is not None and not hasattr(ancestor, 'refresh_current_view'):
                    ancestor = ancestor.parent()
                if ancestor is not None and hasattr(ancestor, 'refresh_current_view'):
                    try:
                        ancestor.refresh_current_view()
                        print(f"[DROP-DEBUG] refresh_current_view called on {ancestor}")
                    except Exception as e:
                        print(f"[DROP-ERROR] refresh_current_view failed: {e}")
                event.acceptProposedAction()
            else:
                print("[DROP-DEBUG] no valid folder target under drop")
                event.ignore()
        else:
            event.ignore()

    def startDrag(self, supportedActions):
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtGui import QDrag
        mime_data = QMimeData()
        selected_paths = [w.full_path for w in self.selected_widgets]
        urls = [QUrl.fromLocalFile(p) for p in selected_paths]
        mime_data.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        try:
            first_widget = next(iter(self.selected_widgets)) if self.selected_widgets else None
            if first_widget and hasattr(first_widget, 'icon_label'):
                pix = first_widget.icon_label.pixmap()
                if pix and not pix.isNull():
                    drag_pix = pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    drag.setPixmap(drag_pix)
        except Exception:
            pass
        drag.exec_(supportedActions)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.drag_start:
            if (event.pos() - self.drag_start).manhattanLength() > QApplication.startDragDistance():
                self.is_dragging = False
                self.startDrag(Qt.MoveAction)
        else:
            try:
                if self._press_pos and (event.buttons() & Qt.LeftButton):
                    dist = (event.pos() - self._press_pos).manhattanLength()
                    if dist > QApplication.startDragDistance():
                        if self._press_widget and hasattr(self._press_widget, 'full_path'):
                            if self._press_widget in self.selected_widgets or getattr(self, 'selected_widgets_paths', None) and self._press_widget.full_path in self.selected_widgets_paths:
                                self._press_pos = None
                                self._press_widget = None
                                self.startDrag(Qt.MoveAction)
                                return
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def setAcceptDrops(self, accept):
        super().setAcceptDrops(accept)

    def _get_parent_scroll_area(self):
        parent = self.parent()
        while parent and not isinstance(parent, QScrollArea):
            parent = parent.parent()
        return parent if isinstance(parent, QScrollArea) else None

    def _auto_scroll_during_drag(self):
        parent_scroll = self._get_parent_scroll_area()
        if not parent_scroll or not self._auto_scroll_direction:
            self.auto_scroll_timer.stop()
            return
        vbar = parent_scroll.verticalScrollBar()
        hbar = parent_scroll.horizontalScrollBar()
        if self._auto_scroll_direction == 'up':
            vbar.setValue(vbar.value() - self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'down':
            vbar.setValue(vbar.value() + self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'left':
            hbar.setValue(hbar.value() - self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'right':
            hbar.setValue(hbar.value() + self._auto_scroll_speed)

    # ... keep the rest of methods like sizeHint, resizeEvent, mousePressEvent, selection helpers unchanged
    
    def sizeHint(self):
        """Provide size hint to ensure proper expansion"""
        # Get the size needed for all widgets
        layout = self.layout()
        if layout.count() == 0:
            return QSize(400, 300)  # Default minimum size
        
        # Calculate minimum size based on content and parent
        min_width = 400
        min_height = 300
        
        # Get the parent scroll area size if available
        parent_widget = self.parent()
        while parent_widget and not isinstance(parent_widget, QScrollArea):
            parent_widget = parent_widget.parent()
            
        if parent_widget and isinstance(parent_widget, QScrollArea):
            viewport_size = parent_widget.viewport().size()
            min_width = max(min_width, viewport_size.width())
            min_height = max(min_height, viewport_size.height())
        
        return QSize(min_width, min_height)
    
    def resizeEvent(self, event):
        """Handle resize events to ensure proper layout"""
        super().resizeEvent(event)
        # Force layout update when resized
        self.layout().activate()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Determine if click is on empty space or on an icon.
            # childAt may return a QLabel or internal child inside an IconWidget.
            # Walk up the parent chain to find a widget that has 'full_path'.
            raw_clicked = self.childAt(event.pos())
            clicked_widget = None
            candidate = raw_clicked
            while candidate is not None and candidate is not self:
                if hasattr(candidate, 'full_path'):
                    clicked_widget = candidate
                    break
                candidate = candidate.parent()

            is_empty_space = (clicked_widget is None or 
                              clicked_widget == self or 
                              clicked_widget == self.layout() or
                              isinstance(clicked_widget, QLayout))

            # If clicking empty space, start selection drag (rubber-band)
            if is_empty_space:
                # Start drag-selection
                self.drag_start = event.pos()
                self.is_dragging = True
                # If not holding Ctrl, clear previous selection
                if not (event.modifiers() & Qt.ControlModifier):
                    self.clear_selection()

                # Special logic: allow single click to the right of the furthest right icon to only register for drag selection
                layout = self.layout()
                if layout.count() > 0:
                    # Find the bottom-most, right-most widget
                    max_right = 0
                    max_bottom = 0
                    for i in range(layout.count()):
                        item = layout.itemAt(i)
                        if item and item.widget():
                            rect = item.widget().geometry()
                            max_right = max(max_right, rect.right())
                            max_bottom = max(max_bottom, rect.bottom())
                    # If click is to the right of the right-most icon (and within the vertical bounds of icons)
                    if event.pos().x() > max_right and event.pos().y() <= max_bottom:
                        # Treat as empty space: clear selection handled above, and allow drag selection to start
                        self.emptySpaceClicked.emit()
                        event.accept()
                        return

                # Default empty-space click behavior
                self.emptySpaceClicked.emit()
                event.accept()
                return
            else:
                # Click landed on a widget (icon) — record press so container can start a drag fallback if needed
                # clicked_widget already resolved to the IconWidget (or None)
                clicked_widget = clicked_widget if clicked_widget is not None else self.childAt(event.pos())
                try:
                    # Record press position and widget for fallback
                    self._press_pos = event.pos()
                    self._press_widget = clicked_widget
                except Exception:
                    self._press_pos = None
                    self._press_widget = None

                # Let the child handle click/selection as before
                super().mousePressEvent(event)
                return
        elif event.button() == Qt.RightButton:
            # Determine if right-click hit an icon by walking up parent chain similar to left-click
            raw_clicked = self.childAt(event.pos())
            clicked_widget = None
            candidate = raw_clicked
            while candidate is not None and candidate is not self:
                if hasattr(candidate, 'full_path'):
                    clicked_widget = candidate
                    break
                candidate = candidate.parent()

            is_empty_space = (clicked_widget is None or 
                              clicked_widget == self or 
                              clicked_widget == self.layout() or
                              isinstance(clicked_widget, QLayout))
            if is_empty_space:
                try:
                    icon_container_debug('Right click in container empty space at pos={} global={}', event.pos(), event.globalPos())
                except Exception:
                    pass
                self.emptySpaceRightClicked.emit(event.globalPos())
                event.accept()
                return
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.drag_start:
            self.drag_end = event.pos()
            self.selection_rect = QRect(self.drag_start, self.drag_end).normalized()
            self.update_selection()
            self.update()  # Trigger repaint

            # --- Auto-scroll logic ---
            parent_scroll = self._get_parent_scroll_area()
            if parent_scroll:
                view_rect = parent_scroll.viewport().rect()
                mapped_pos = self.mapToParent(event.pos())
                # Determine scroll direction
                direction = None
                if mapped_pos.y() < self._auto_scroll_margin:
                    direction = 'up'
                elif mapped_pos.y() > view_rect.height() - self._auto_scroll_margin:
                    direction = 'down'
                elif mapped_pos.x() < self._auto_scroll_margin:
                    direction = 'left'
                elif mapped_pos.x() > view_rect.width() - self._auto_scroll_margin:
                    direction = 'right'
                if direction:
                    self._auto_scroll_direction = direction
                    if not self.auto_scroll_timer.isActive():
                        self.auto_scroll_timer.start()
                else:
                    self._auto_scroll_direction = None
                    self.auto_scroll_timer.stop()
            else:
                self._auto_scroll_direction = None
                self.auto_scroll_timer.stop()
        else:
            # Fallback: if user pressed on an icon (not empty space) and moved beyond drag threshold, start drag of selected items
            try:
                if self._press_pos and (event.buttons() & Qt.LeftButton):
                    dist = (event.pos() - self._press_pos).manhattanLength()
                    if dist > QApplication.startDragDistance():
                        # Only start container drag if the pressed widget is part of the selection
                        if self._press_widget and hasattr(self._press_widget, 'full_path'):
                            if self._press_widget in self.selected_widgets or self._press_widget.full_path in getattr(self, 'selected_widgets_paths', []):
                                # Reset press tracking to avoid re-entrancy
                                self._press_pos = None
                                self._press_widget = None
                                # Start drag using container's selected widgets
                                self.startDrag(Qt.MoveAction)
                                return
            except Exception:
                pass
            self._auto_scroll_direction = None
            self.auto_scroll_timer.stop()

    def _get_parent_scroll_area(self):
        parent = self.parent()
        while parent and not isinstance(parent, QScrollArea):
            parent = parent.parent()
        return parent if isinstance(parent, QScrollArea) else None

    def _auto_scroll_during_drag(self):
        parent_scroll = self._get_parent_scroll_area()
        if not parent_scroll or not self._auto_scroll_direction:
            self.auto_scroll_timer.stop()
            return
        vbar = parent_scroll.verticalScrollBar()
        hbar = parent_scroll.horizontalScrollBar()
        if self._auto_scroll_direction == 'up':
            vbar.setValue(vbar.value() - self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'down':
            vbar.setValue(vbar.value() + self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'left':
            hbar.setValue(hbar.value() - self._auto_scroll_speed)
        elif self._auto_scroll_direction == 'right':
            hbar.setValue(hbar.value() + self._auto_scroll_speed)

    def mouseReleaseEvent(self, event):
        try:
            icon_container_debug('mouseReleaseEvent button={} pos={} global={}', getattr(event, 'button', lambda: None)(), getattr(event, 'pos', lambda: '<no-pos>')(), getattr(event, 'globalPos', lambda: '<no-global>')())
        except Exception:
            pass
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.drag_start = None
            self.drag_end = None
            self.update()  # Clear selection rectangle
            self._auto_scroll_direction = None
            self.auto_scroll_timer.stop()

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
                # Update IconWidget selection state for truncation
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(False)
        self.selected_widgets.clear()
        self.selectionChanged.emit([])

    def add_to_selection(self, widget):
        self.selected_widgets.add(widget)
        widget.setStyleSheet("QWidget { border: 2px solid #0078d7; background-color: rgba(0, 120, 215, 0.2); }")
        # Update IconWidget selection state for truncation
        if hasattr(widget, 'set_selected'):
            widget.set_selected(True)
        selected_paths = [w.full_path for w in self.selected_widgets]
        self.selectionChanged.emit(selected_paths)

    def remove_from_selection(self, widget):
        if widget in self.selected_widgets:
            self.selected_widgets.remove(widget)
            widget.setStyleSheet("QWidget { border: 2px solid transparent; }")
            # Update IconWidget selection state for truncation
            if hasattr(widget, 'set_selected'):
                widget.set_selected(False)
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
        # Prevent recursive calls during relayout
        if hasattr(self, '_in_add_widget') and self._in_add_widget:
            return
        self._in_add_widget = True
        
        try:
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
                # Get the actual available width from the scroll area viewport
                parent = self.parent()
                scroll_area = None
                while parent:
                    if hasattr(parent, 'viewport'):
                        scroll_area = parent
                        break
                    parent = parent.parent()
                if scroll_area:
                    viewport_width = scroll_area.viewport().width()
                else:
                    viewport_width = self.width()
                # Get layout margins
                layout_margins = self.layout().contentsMargins()
                left_margin = layout_margins.left()
                right_margin = layout_margins.right()
                spacing = layout.spacing()
                # Calculate available width for icons (viewport minus margins)
                available_width = viewport_width - left_margin - right_margin
                # Calculate max icons per row that fit without scrolling
                if available_width < effective_widget_width:
                    icons_per_row = 1
                else:
                    # n*W + (n-1)*S <= available_width  =>  n = floor((available_width + S) / (W + S))
                    icons_per_row = max(1, (available_width + spacing) // (effective_widget_width))
            
            # Calculate current position
            current_count = layout.count()
            row = current_count // icons_per_row
            col = current_count % icons_per_row
            
            # Force widget size BEFORE adding to layout to ensure proper grid display
            widget.setMinimumSize(widget_width, widget_height)
            widget.setMaximumWidth(widget_width + 20)  # Allow some flexibility
            widget.setFixedSize(widget_width, widget_height)  # Force exact size for grid layout
            
            # Add widget at calculated position
            layout.addWidget(widget, row, col)
            
        finally:
            self._in_add_widget = False

    def resizeEvent(self, event):
        """Handle resize events to re-layout icons in auto-width mode"""
        super().resizeEvent(event)
        
        # Prevent recursive resize events
        if hasattr(self, '_in_resize') and self._in_resize:
            return
        self._in_resize = True
        
        try:
            # Check scroll area viewport width instead of container width for better auto-width calculation
            scroll_area = None
            parent = self.parent()
            while parent:
                if hasattr(parent, 'viewport'):
                    scroll_area = parent
                    break
                parent = parent.parent()
            
            # Get current available width
            if scroll_area:
                current_width = scroll_area.viewport().width()
            else:
                current_width = self.width()
            
            if not hasattr(self, 'last_available_width'):
                self.last_available_width = current_width
            
            # Only re-layout if width changed significantly and we're in auto-width mode
            if abs(current_width - self.last_available_width) > 50:  # Significant width change
                self.last_available_width = current_width
                
                # Check if we're in auto-width mode by trying to get the setting from parent
                main_window = None
                parent = self.parent()
                while parent:
                    if hasattr(parent, 'main_window'):
                        main_window = parent.main_window
                        break
                    elif hasattr(parent, 'icons_wide'):
                        main_window = parent
                        break
                    parent = parent.parent()
                
                # Re-layout icons if in auto-width mode (icons_wide == 0)
                if main_window and getattr(main_window, 'icons_wide', 0) == 0:
                    # Use a timer to prevent excessive calls
                    if not hasattr(self, '_resize_timer'):
                        from PyQt5.QtCore import QTimer
                        self._resize_timer = QTimer()
                        self._resize_timer.setSingleShot(True)
                        self._resize_timer.timeout.connect(self.relayout_icons)
                    
                    self._resize_timer.stop()
                    self._resize_timer.start(100)  # Delay 100ms before relayout
        finally:
            self._in_resize = False
    
    def relayout_icons(self):
        """Re-layout existing icons to adjust to new container width"""
        layout = self.layout()
        widgets = []
        
        # Collect all existing widgets
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                widgets.append(item.widget())
        
        # Clear the layout
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item:
                layout.removeItem(item)
        
        # Re-add widgets with new layout calculation
        if widgets:
            # Get current settings
            main_window = None
            parent = self.parent()
            while parent and not main_window:
                if hasattr(parent, 'thumbnail_size'):
                    main_window = parent
                    break
                parent = parent.parent()
            
            thumbnail_size = getattr(main_window, 'thumbnail_size', 64) if main_window else 64
            icons_wide = getattr(main_window, 'icons_wide', 0) if main_window else 0
            
            for widget in widgets:
                self.add_widget_optimized(widget, thumbnail_size, icons_wide)

class BreadcrumbWidget(QWidget):
    """Breadcrumb navigation widget"""
    pathClicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(5, 0, 5, 0)  # Reduced vertical margins for less spacing
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignLeft)  # Explicitly set left alignment
        self.setLayout(self.layout)
        
        # Make breadcrumb bar more compact to reduce vertical space
        self.setFixedHeight(24)  # Reduced from 40 to 24
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        
        # Use normal font size instead of enlarged
        font = self.font()
        font.setPointSize(font.pointSize())  # Keep original size, don't multiply by 2
        self.setFont(font)
        
    def set_path(self, path):
        """Set the current path and update breadcrumb buttons"""
        # Clear existing widgets and layout items (including stretch)
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                # Remove spacer items (stretch)
                del item
        
        if not path:
            # Even with no path, add stretch to maintain left alignment
            self.layout.addStretch()
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
            
            # Create clickable button for path part with underscore wrapping
            formatted_name = format_filename_with_underscore_wrap(name)
            button = QPushButton(formatted_name)
            button.setFlat(True)
            button.setStyleSheet("""
                QPushButton {
                    border: none;
                    padding: 4px 8px;
                    color: green;
                    text-decoration: underline;
                    text-align: left;
                    font-size: 20px;
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

class FileManagerTab(QWidget):
    def prompt_credentials(self, url, default_user='', default_pass=''):
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QPalette
        class CredDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle('Enter Credentials')
                self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setAttribute(Qt.WA_DontShowOnScreen, False)
                self.setAttribute(Qt.WA_NativeWindow, False)
                layout = QFormLayout(self)
                self.user = QLineEdit(default_user)
                self.pw = QLineEdit(default_pass)
                self.pw.setEchoMode(QLineEdit.Password)
                layout.addRow('Username:', self.user)
                layout.addRow('Password:', self.pw)
                buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                buttons.accepted.connect(self.accept)
                buttons.rejected.connect(self.reject)
                layout.addWidget(buttons)

                # Always use PyQt dialog and apply dark mode if parent has it enabled
                dark_mode = False
                if parent and hasattr(parent, 'dark_mode'):
                    dark_mode = parent.dark_mode
                if dark_mode:
                    dark_palette = QPalette()
                    dark_palette.setColor(QPalette.Window, Qt.black)
                    dark_palette.setColor(QPalette.WindowText, Qt.white)
                    dark_palette.setColor(QPalette.Base, Qt.black)
                    dark_palette.setColor(QPalette.AlternateBase, Qt.black)
                    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
                    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
                    dark_palette.setColor(QPalette.Text, Qt.white)
                    dark_palette.setColor(QPalette.Button, Qt.black)
                    dark_palette.setColor(QPalette.ButtonText, Qt.white)
                    dark_palette.setColor(QPalette.BrightText, Qt.red)
                    dark_palette.setColor(QPalette.Highlight, Qt.darkGray)
                    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
                    self.setPalette(dark_palette)
                    dark_style = """
                    QDialog {
                        background-color: #232323;
                        color: #ffffff;
                    }
                    QLabel {
                        color: #ffffff;
                        background-color: transparent;
                    }
                    QLineEdit {
                        background-color: #2b2b2b;
                        color: #ffffff;
                        border: 1px solid #555555;
                    }
                    QDialogButtonBox QPushButton {
                        background-color: #404040;
                        color: #ffffff;
                        border: 1px solid #555555;
                        border-radius: 3px;
                        padding: 5px 15px;
                    }
                    QDialogButtonBox QPushButton:hover {
                        background-color: #4a4a4a;
                    }
                    QDialogButtonBox QPushButton:pressed {
                        background-color: #0078d7;
                    }
                    QDialogButtonBox QPushButton:default {
                        border: 2px solid #0078d7;
                    }
                    """
                    self.setStyleSheet(dark_style)
                else:
                    self.setStyleSheet("")
        dlg = CredDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.user.text(), dlg.pw.text()
        return None, None
    """Individual file manager tab"""
    
    def __init__(self, initial_path, tab_manager):
        super().__init__()
    # FileManagerTab.__init__ called
        # Preserve the initial path/sentinel for setup_tab_ui
        self.initial_dir = initial_path
        self.current_folder = initial_path
        self.tab_manager = tab_manager

        # Navigation history
        self.navigation_history = [initial_path]
        self.history_index = 0
        
        # Sorting options (per tab) - set defaults first
        self.sort_by = "name"  # name, size, date, type, extension
        self.sort_order = "ascending"  # ascending, descending
        self.directories_first = True
        self.case_sensitive = False
        self.group_by_type = False
        self.natural_sort = True  # Natural sorting for numbers in names
        
        # Load saved sort settings BEFORE setting up UI
        if self.tab_manager and self.tab_manager.main_window:
            self.tab_manager.main_window.load_tab_sort_settings(self)
        
        self.setup_tab_ui()
        
    def setup_tab_ui(self):
        """Setup the UI for this tab"""
        layout = QVBoxLayout()

        # Address bar (always visible)
        address_layout = QHBoxLayout()
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Enter path and press Enter...")
        self.address_bar.returnPressed.connect(self.on_address_entered)
        address_layout.addWidget(QLabel("Address:"))
        address_layout.addWidget(self.address_bar)
        layout.addLayout(address_layout)

        # Breadcrumb for this tab
        self.breadcrumb = BreadcrumbWidget()
        self.breadcrumb.pathClicked.connect(self.navigate_to)
        layout.addWidget(self.breadcrumb)

        # File view area
        self.view_stack = QStackedWidget()

        # Thumbnail view (was Icon view)
        self.setup_thumbnail_view()

        # List view
        self.setup_list_view()

        # Detail view
        self.setup_detail_view()

        layout.addWidget(self.view_stack)
        self.setLayout(layout)

        # Initialize with current folder, remote location, or My Computer drive list
        self.is_drive_list = False
        if isinstance(self.current_folder, str):
            if self.current_folder.startswith('ftp://'):
                self.browse_ftp(self.current_folder)
            elif self.current_folder.startswith('sftp://'):
                self.browse_sftp(self.current_folder)
            elif self.current_folder == "__MY_COMPUTER__":
                # Configure models to show connected drives only
                try:
                    self.is_drive_list = True
                    drives_filter = QDir.Drives | QDir.Dirs | QDir.NoDotAndDotDot

                    # Configure list model to show drives
                    self.list_model = FormattedFileSystemModel()
                    self.list_model.setFilter(drives_filter)
                    # Use empty rootPath so QFileSystemModel enumerates drives on Windows
                    try:
                        self.list_model.setRootPath("")
                        self.list_view.setModel(self.list_model)
                        self.list_view.setRootIndex(self.list_model.index(""))
                    except Exception:
                        # Fallback to QDir.rootPath()
                        self.list_model.setRootPath(QDir.rootPath())
                        self.list_view.setModel(self.list_model)
                        self.list_view.setRootIndex(self.list_model.index(QDir.rootPath()))

                    # Configure detail model similarly
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_model.setFilter(drives_filter)
                    try:
                        self.detail_model.setRootPath("")
                        self.detail_view.setModel(self.detail_model)
                        self.detail_view.setRootIndex(self.detail_model.index(""))
                    except Exception:
                        self.detail_model.setRootPath(QDir.rootPath())
                        self.detail_view.setModel(self.detail_model)
                        self.detail_view.setRootIndex(self.detail_model.index(QDir.rootPath()))

                    # Update UI elements
                    if hasattr(self, 'address_bar'):
                        self.address_bar.setText("My Computer")
                    if hasattr(self, 'breadcrumb'):
                        try:
                            self.breadcrumb.set_path("My Computer")
                        except Exception:
                            pass
                    # Sync visible widget to the main window's current view mode so My Computer follows other tabs
                    try:
                        main_window = self.tab_manager.main_window if self.tab_manager else None
                        mode = None
                        if main_window and hasattr(main_window, 'view_mode_manager'):
                            mode = main_window.view_mode_manager.get_mode()
                        if mode == ViewModeManager.THUMBNAIL_VIEW:
                            # Thumbnail view - use thumbnail widget
                            try:
                                self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
                            except Exception:
                                self.view_stack.setCurrentWidget(self.list_view)
                            try:
                                self.refresh_thumbnail_view()
                            except Exception:
                                pass
                        elif mode == ViewModeManager.ICON_VIEW:
                            # Icon view uses same widget as thumbnail but mark icon flag
                            try:
                                self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
                                setattr(self, 'icon_view_active', True)
                            except Exception:
                                self.view_stack.setCurrentWidget(self.list_view)
                            try:
                                self.refresh_current_view()
                            except Exception:
                                pass
                        elif mode == ViewModeManager.LIST_VIEW:
                            try:
                                self.view_stack.setCurrentWidget(self.list_view)
                                self.refresh_list_view()
                            except Exception:
                                pass
                        elif mode == ViewModeManager.DETAIL_VIEW:
                            try:
                                self.view_stack.setCurrentWidget(self.detail_view)
                                self.refresh_detail_view()
                            except Exception:
                                pass
                        else:
                            # Default to list view
                            try:
                                self.view_stack.setCurrentWidget(self.list_view)
                                self.refresh_list_view()
                            except Exception:
                                pass

                    except Exception:
                        try:
                            self.view_stack.setCurrentWidget(self.list_view)
                        except Exception:
                            pass

                    # Update tab title
                    try:
                        if self.tab_manager:
                            self.tab_manager.update_tab_title(self, "My Computer")
                    except Exception:
                        pass
                except Exception:
                    # Fall back to home if something goes wrong
                    self.navigate_to(os.path.expanduser("~"))
            else:
                self.navigate_to(self.current_folder)

    def show_my_computer(self):
        """Configure this tab to show connected drives (My Computer)"""
        try:
            self.is_drive_list = True
            # Mark current_folder as sentinel so navigation state is clear
            try:
                self.current_folder = "__MY_COMPUTER__"
            except Exception:
                pass
            drives_filter = QDir.Drives | QDir.Dirs | QDir.NoDotAndDotDot

            # List model
            self.list_model = FormattedFileSystemModel()
            self.list_model.setFilter(drives_filter)
            try:
                self.list_model.setRootPath("")
                self.list_view.setModel(self.list_model)
                self.list_view.setRootIndex(self.list_model.index(""))
            except Exception:
                self.list_model.setRootPath(QDir.rootPath())
                self.list_view.setModel(self.list_model)
                self.list_view.setRootIndex(self.list_model.index(QDir.rootPath()))

            # Detail model
            self.detail_model = FormattedFileSystemModel()
            self.detail_model.setFilter(drives_filter)
            try:
                self.detail_model.setRootPath("")
                self.detail_view.setModel(self.detail_model)
                self.detail_view.setRootIndex(self.detail_model.index(""))
            except Exception:
                self.detail_model.setRootPath(QDir.rootPath())
                self.detail_view.setModel(self.detail_model)
                self.detail_view.setRootIndex(self.detail_model.index(QDir.rootPath()))

            if hasattr(self, 'address_bar'):
                self.address_bar.setText("My Computer")
            if hasattr(self, 'breadcrumb'):
                try:
                    self.breadcrumb.set_path("My Computer")
                except Exception:
                    pass

            # Sync view mode
            try:
                main_window = self.tab_manager.main_window if self.tab_manager else None
                mode = None
                if main_window and hasattr(main_window, 'view_mode_manager'):
                    mode = main_window.view_mode_manager.get_mode()
                if mode == ViewModeManager.THUMBNAIL_VIEW:
                    try:
                        self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
                    except Exception:
                        self.view_stack.setCurrentWidget(self.list_view)
                    try:
                        self.refresh_thumbnail_view()
                    except Exception:
                        pass
                elif mode == ViewModeManager.ICON_VIEW:
                    try:
                        self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
                        setattr(self, 'icon_view_active', True)
                    except Exception:
                        self.view_stack.setCurrentWidget(self.list_view)
                    try:
                        self.refresh_current_view()
                    except Exception:
                        pass
                elif mode == ViewModeManager.LIST_VIEW:
                    try:
                        self.view_stack.setCurrentWidget(self.list_view)
                        self.refresh_list_view()
                    except Exception:
                        pass
                elif mode == ViewModeManager.DETAIL_VIEW:
                    try:
                        self.view_stack.setCurrentWidget(self.detail_view)
                        self.refresh_detail_view()
                    except Exception:
                        pass
                else:
                    try:
                        self.view_stack.setCurrentWidget(self.list_view)
                        self.refresh_list_view()
                    except Exception:
                        pass
            except Exception:
                try:
                    self.view_stack.setCurrentWidget(self.list_view)
                except Exception:
                    pass

            try:
                if self.tab_manager:
                    self.tab_manager.update_tab_title(self, "My Computer")
            except Exception:
                pass
        except Exception:
            # As a safe fallback, navigate to user's home
            try:
                self.navigate_to(os.path.expanduser('~'))
            except Exception:
                pass

    def on_address_entered(self):
        path = self.address_bar.text().strip()
        if path.startswith('ftp://'):
            # Open FTP in a new tab
            if self.tab_manager:
                self.tab_manager.new_tab(path)
            return
        elif path.startswith('sftp://'):
            # Optionally, do the same for SFTP if desired
            if self.tab_manager:
                self.tab_manager.new_tab(path)
            return
        if os.path.isdir(path):
            self.navigate_to(path)
            self.address_bar.setStyleSheet("")
            self.address_bar.setToolTip("")
        else:
            self.address_bar.setStyleSheet("background-color: #ffcccc;")
            self.address_bar.setToolTip("Invalid directory path")

    def browse_ftp(self, url):
        # Parse ftp://[user[:pass]@]host[:port]/path
        match = re.match(r'ftp://(?:(?P<user>[^:@/]+)(?::(?P<passwd>[^@/]*))?@)?(?P<host>[^:/]+)(?::(?P<port>\\d+))?(?P<path>/.*)?', url)
        if not match:
            self.address_bar.setStyleSheet("background-color: #ffcccc;")
            self.address_bar.setToolTip("Invalid FTP address")
            return
        user = match.group('user') or ''
        passwd = match.group('passwd') or ''
        host = match.group('host')
        port = int(match.group('port')) if match.group('port') else 21
        path = match.group('path') or '/'
        if not user or not passwd:
            u, p = self.prompt_credentials(url, user, passwd)
            if u is None:
                return
            user, passwd = u, p
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=10)
            ftp.login(user, passwd)
            ftp.cwd(path)
            files = []
            ftp.retrlines('LIST', files.append)
            self.ftp_conn = ftp
            self.ftp_conn_url = url
            self.ftp_conn_path = path
            self.show_remote_listing(files, url, protocol='ftp')
            self.address_bar.setStyleSheet("")
            self.address_bar.setToolTip("")
        except Exception as e:
            self.address_bar.setStyleSheet("background-color: #ffcccc;")
            self.address_bar.setToolTip(f"FTP error: {e}")

    def browse_sftp(self, url):
        # Parse sftp://[user[:pass]@]host[:port]/path
        match = re.match(r'sftp://(?:(?P<user>[^:@/]+)(?::(?P<passwd>[^@/]*))?@)?(?P<host>[^:/]+)(?::(?P<port>\\d+))?(?P<path>/.*)?', url)
        if not match:
            self.address_bar.setStyleSheet("background-color: #ffcccc;")
            self.address_bar.setToolTip("Invalid SFTP address")
            return
        user = match.group('user') or ''
        passwd = match.group('passwd') or ''
        host = match.group('host')
        port = int(match.group('port')) if match.group('port') else 22
        path = match.group('path') or '/'
        if not user or not passwd:
            u, p = self.prompt_credentials(url, user, passwd)
            if u is None:
                return
            user, passwd = u, p
        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=user, password=passwd)
            sftp = paramiko.SFTPClient.from_transport(transport)
            files = sftp.listdir(path)
            self.sftp_conn = sftp
            self.sftp_conn_transport = transport
            self.sftp_conn_url = url
            self.sftp_conn_path = path
            self.show_remote_listing(files, url, protocol='sftp')
            self.address_bar.setStyleSheet("")
            self.address_bar.setToolTip("")
        except Exception as e:
            self.address_bar.setStyleSheet("background-color: #ffcccc;")
            self.address_bar.setToolTip(f"SFTP error: {e}")

    def show_remote_listing(self, files, url, protocol=None):
        # Replace file view with a simple list for remote files, with upload/download
        from PyQt5.QtWidgets import QListWidget, QVBoxLayout, QWidget, QLabel, QHBoxLayout
        remote_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Remote listing: {url}"))
        list_widget = QListWidget()
        for f in files:
            list_widget.addItem(str(f))
        layout.addWidget(list_widget)
        btn_layout = QHBoxLayout()
        download_btn = QPushButton('Download Selected')
        upload_btn = QPushButton('Upload File...')
        btn_layout.addWidget(download_btn)
        btn_layout.addWidget(upload_btn)
        layout.addLayout(btn_layout)
        remote_widget.setLayout(layout)
        self.view_stack.addWidget(remote_widget)
        self.view_stack.setCurrentWidget(remote_widget)

        def do_download():
            selected = list_widget.currentItem()
            if not selected:
                QMessageBox.warning(self, 'No selection', 'Select a file to download.')
                return
            fname = selected.text().split()[-1]  # crude, works for FTP LIST output or SFTP name
            file_dialog = QFileDialog(self, 'Save As')
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.selectFile(fname)
            file_dialog.setOption(QFileDialog.DontUseNativeDialog, True)
            if file_dialog.exec_() == QFileDialog.Accepted:
                save_path = file_dialog.selectedFiles()[0]
            else:
                return
            try:
                if protocol == 'ftp':
                    with open(save_path, 'wb') as f:
                        self.ftp_conn.retrbinary(f'RETR {fname}', f.write)
                elif protocol == 'sftp':
                    self.sftp_conn.get(self.sftp_conn_path.rstrip('/') + '/' + fname, save_path)
                QMessageBox.information(self, 'Download', f'Downloaded {fname} to {save_path}')
            except Exception as e:
                QMessageBox.critical(self, 'Download Error', str(e))

        def do_upload():
            file_path, _ = QFileDialog.getOpenFileName(self, 'Select file to upload')
            if not file_path:
                return
            fname = os.path.basename(file_path)
            try:
                if protocol == 'ftp':
                    with open(file_path, 'rb') as f:
                        self.ftp_conn.storbinary(f'STOR {fname}', f)
                elif protocol == 'sftp':
                    self.sftp_conn.put(file_path, self.sftp_conn_path.rstrip('/') + '/' + fname)
                QMessageBox.information(self, 'Upload', f'Uploaded {fname} to remote folder')
            except Exception as e:
                QMessageBox.critical(self, 'Upload Error', str(e))

        download_btn.clicked.connect(do_download)
        upload_btn.clicked.connect(do_upload)

    def navigate_to(self, path, add_to_history=True):
        """Navigate to the specified path"""
        # Only save sort settings if we're actually changing folders
        if hasattr(self, 'current_folder') and self.current_folder != path:
            if hasattr(self, 'tab_manager') and self.tab_manager and hasattr(self.tab_manager, 'main_window'):
                self.tab_manager.main_window.save_tab_sort_settings(self)

        # Ensure path is a string
        if not isinstance(path, str):
            return

        # Special sentinel: show My Computer (drive list)
        if path == "__MY_COMPUTER__":
            try:
                self.show_my_computer()
                # Optionally add sentinel to navigation history so forward/back
                # navigation will work across My Computer entries.
                if add_to_history:
                    try:
                        # Trim any forward history when navigating to a new location
                        self.navigation_history = self.navigation_history[:self.history_index + 1]
                    except Exception:
                        self.navigation_history = getattr(self, 'navigation_history', [])
                        self.history_index = getattr(self, 'history_index', -1)
                    if not self.navigation_history or self.navigation_history[-1] != path:
                        self.navigation_history.append(path)
                        self.history_index = len(self.navigation_history) - 1
                return
            except Exception:
                # If show_my_computer fails, fall back to home
                try:
                    self.navigate_to(os.path.expanduser("~"))
                except Exception:
                    pass
                return

        if os.path.exists(path) and os.path.isdir(path):
            # If we were showing the drive list (My Computer), switch back to normal
            # filesystem models so the directory loads correctly in this tab.
            try:
                if getattr(self, 'is_drive_list', False):
                    self.is_drive_list = False
                    # Recreate normal filesystem models for listing and details
                    self.list_model = FormattedFileSystemModel()
                    self.list_view.setModel(self.list_model)
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_view.setModel(self.detail_model)
            except Exception:
                pass
            self.current_folder = path
            self.breadcrumb.set_path(path)
            if hasattr(self, 'address_bar'):
                self.address_bar.setText(path)
                self.address_bar.setStyleSheet("")
                self.address_bar.setToolTip("")

            # Load sort settings for the new folder
            if hasattr(self, 'tab_manager') and self.tab_manager and hasattr(self.tab_manager, 'main_window'):
                self.tab_manager.main_window.load_tab_sort_settings(self)

            self.refresh_current_view()

            # Register directory with background monitor to auto-refresh on changes
            try:
                if hasattr(self, 'tab_manager') and self.tab_manager and hasattr(self.tab_manager, 'main_window'):
                    main = self.tab_manager.main_window
                    if hasattr(main, 'background_monitor') and main.background_monitor:
                        # Remove previous directory if any
                        try:
                            prev = getattr(self, '_monitored_directory', None)
                            if prev and prev != path:
                                main.background_monitor.remove_directory(prev)
                        except Exception:
                            pass
                        # Add new directory monitor and refresh tab when change detected
                        def _on_dir_changed(d):
                            try:
                                self.refresh_current_view()
                            except Exception:
                                pass
                        main.background_monitor.add_directory(path, _on_dir_changed)
                        self._monitored_directory = path
            except Exception:
                pass

            # Add to navigation history if this is a new navigation (not back/forward)
            if add_to_history:
                # Remove any forward history if we're navigating to a new location
                self.navigation_history = self.navigation_history[:self.history_index + 1]
                # Add new path if it's different from current
                if not self.navigation_history or self.navigation_history[-1] != path:
                    self.navigation_history.append(path)
                    self.history_index = len(self.navigation_history) - 1

            # Update tab title with underscore wrapping
            title = os.path.basename(path) or os.path.dirname(path) or "Home"
            formatted_title = format_filename_with_underscore_wrap(title)
            self.tab_manager.update_tab_title(self, formatted_title)
        else:
            if hasattr(self, 'address_bar'):
                self.address_bar.setStyleSheet("background-color: #ffcccc;")
                self.address_bar.setToolTip("Invalid directory path")
        
    def setup_thumbnail_view(self):
        """Setup thumbnail view for this tab (replaces icon view)"""
        self.thumbnail_view_widget = QWidget()
        icon_layout = QVBoxLayout()
        icon_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area to contain the thumbnail grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Icon container (grid of IconWidget instances) - keep class name for compatibility
        self.icon_container = IconContainer()
        self.icon_container.setAcceptDrops(True)
        self.icon_container.setMouseTracking(True)
        self.scroll_area.setWidget(self.icon_container)

        # Optionally the main window can install an event filter on the viewport
        # self.scroll_area.viewport().installEventFilter(self)

        icon_layout.addWidget(self.scroll_area)
        self.thumbnail_view_widget.setLayout(icon_layout)
        self.view_stack.addWidget(self.thumbnail_view_widget)

        # Set thumbnail view as default
        self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
    
    def setup_list_view(self):
        """Setup list view for this tab"""
        self.list_view = QListView()
        self.list_model = FormattedFileSystemModel()
        self.list_view.setModel(self.list_model)
        # Enable word wrapping for long names with underscores
        self.list_view.setWordWrap(True)
        # Set custom delegate for proper word wrapping with zero-width spaces
        self.list_view.setItemDelegate(WordWrapDelegate())

        # Connect list view events
        self.list_view.clicked.connect(self.on_list_item_clicked)
        self.list_view.doubleClicked.connect(self.on_list_item_double_clicked)

        self.view_stack.addWidget(self.list_view)
    
    def setup_detail_view(self):
        """Setup detail view for this tab"""
        self.detail_view = QTableView()
        self.detail_model = FormattedFileSystemModel()
        self.detail_view.setModel(self.detail_model)
        # Enable word wrapping for long names with underscores
        self.detail_view.setWordWrap(True)
        # Set custom delegate for proper word wrapping with zero-width spaces
        self.detail_view.setItemDelegate(WordWrapDelegate())
        # Connect detail view events
        self.detail_view.clicked.connect(self.on_detail_item_clicked)
        self.detail_view.doubleClicked.connect(self.on_detail_item_double_clicked)
        
        self.view_stack.addWidget(self.detail_view)
    
    def on_list_item_clicked(self, index):
        """Handle list view item clicks"""
        if index.isValid():
            file_path = self.list_model.filePath(index)
            # If this tab is a My Computer drive-list and a drive was clicked, open it immediately
            try:
                if getattr(self, 'is_drive_list', False):
                    # Reset drive-list flag so tab behaves like a normal folder tab
                    self.is_drive_list = False
                    # Recreate models for normal listing
                    self.list_model = FormattedFileSystemModel()
                    self.list_view.setModel(self.list_model)
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_view.setModel(self.detail_model)
                    # Navigate into the clicked drive
                    if os.path.isdir(file_path):
                        self.navigate_to(file_path)
                        return
            except Exception:
                pass
            # Update preview pane if main window has one
            if hasattr(self.tab_manager, 'main_window') and hasattr(self.tab_manager.main_window, 'preview_pane'):
                self.tab_manager.main_window.preview_pane.preview_file(file_path)
            # Update selection
            if hasattr(self.tab_manager, 'main_window'):
                self.tab_manager.main_window.selected_items = [file_path]
                if hasattr(self.tab_manager.main_window, 'safe_update_status_bar'):
                    self.tab_manager.main_window.safe_update_status_bar()

    def on_list_item_double_clicked(self, index):
        """Handle list view double clicks"""
        if index.isValid():
            try:
                file_path = self.list_model.filePath(index)
            except Exception:
                file_path = '<error>'
            try:
                # placeholder - on_list_item_double_clicked
                _ = None
            except Exception:
                pass
            # If we are in My Computer drive-list mode and a drive was double-clicked, open it
            try:
                if getattr(self, 'is_drive_list', False):
                    self.is_drive_list = False
                    self.list_model = FormattedFileSystemModel()
                    self.list_view.setModel(self.list_model)
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_view.setModel(self.detail_model)
                    if os.path.isdir(file_path):
                        self.navigate_to(file_path)
                        return
            except Exception:
                pass
            self.handle_double_click(file_path)

    def on_detail_item_clicked(self, index):
        """Handle detail view item clicks"""
        if index.isValid():
            file_path = self.detail_model.filePath(index)
            # Similar behavior for detail view when in My Computer drive-list
            try:
                if getattr(self, 'is_drive_list', False):
                    self.is_drive_list = False
                    self.list_model = FormattedFileSystemModel()
                    self.list_view.setModel(self.list_model)
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_view.setModel(self.detail_model)
                    if os.path.isdir(file_path):
                        self.navigate_to(file_path)
                        return
            except Exception:
                pass
            # Update preview pane if main window has one
            if hasattr(self.tab_manager, 'main_window') and hasattr(self.tab_manager.main_window, 'preview_pane'):
                self.tab_manager.main_window.preview_pane.preview_file(file_path)
            # Update selection
            if hasattr(self.tab_manager, 'main_window'):
                self.tab_manager.main_window.selected_items = [file_path]
                if hasattr(self.tab_manager.main_window, 'safe_update_status_bar'):
                    self.tab_manager.main_window.safe_update_status_bar()

    def on_detail_item_double_clicked(self, index):
        """Handle detail view double clicks"""
        if index.isValid():
            try:
                file_path = self.detail_model.filePath(index)
                if not file_path:
                    try:
                        root = self.detail_model.rootPath() or ""
                        name = index.data(Qt.DisplayRole) or index.data()
                        file_path = os.path.join(root, name) if root else name
                    except Exception:
                        file_path = '<error>'
            except Exception:
                file_path = '<error>'
            try:
                # placeholder - on_detail_item_double_clicked
                _ = None
            except Exception:
                pass
            # If in My Computer drive-list mode, open drive on double click
            try:
                if getattr(self, 'is_drive_list', False):
                    self.is_drive_list = False
                    self.list_model = FormattedFileSystemModel()
                    self.list_view.setModel(self.list_model)
                    self.detail_model = FormattedFileSystemModel()
                    self.detail_view.setModel(self.detail_model)
                    if isinstance(file_path, str) and os.path.isdir(file_path):
                        self.navigate_to(file_path)
                        return
            except Exception:
                pass
            self.handle_double_click(file_path)
    
    # Removed duplicate/old navigate_to method to ensure only the correct one is used
    
    def can_go_back(self):
        """Check if we can go back in history"""
        return self.history_index > 0
    
    def can_go_forward(self):
        """Check if we can go forward in history"""
        return self.history_index < len(self.navigation_history) - 1
    
    def go_back(self):
        """Navigate back in history"""
        if self.can_go_back():
            self.history_index -= 1
            path = self.navigation_history[self.history_index]
            # If the history entry is the My Computer sentinel, show drives
            if isinstance(path, str) and path == "__MY_COMPUTER__":
                try:
                    self.show_my_computer()
                    try:
                        self.current_folder = "__MY_COMPUTER__"
                    except Exception:
                        pass
                    # Do not add the sentinel to normal history when restoring
                except Exception:
                    # fallback to normal navigate behavior
                    self.navigate_to(path, add_to_history=False)
                if hasattr(self, 'address_bar'):
                    # Show a friendly label for the sentinel in the address bar
                    try:
                        self.address_bar.setText('My Computer')
                    except Exception:
                        pass
                return

            # Default behavior for filesystem paths
            self.navigate_to(path, add_to_history=False)
            if hasattr(self, 'address_bar'):
                self.address_bar.setText(path)
    
    def go_forward(self):
        """Navigate forward in history"""
        if self.can_go_forward():
            self.history_index += 1
            path = self.navigation_history[self.history_index]
            # If the forward entry is the My Computer sentinel, show drives
            if isinstance(path, str) and path == "__MY_COMPUTER__":
                try:
                    self.show_my_computer()
                    try:
                        self.current_folder = "__MY_COMPUTER__"
                    except Exception:
                        pass
                    if hasattr(self, 'address_bar'):
                        try:
                            self.address_bar.setText('My Computer')
                        except Exception:
                            pass
                except Exception:
                    # Fallback to normal navigation if show_my_computer fails
                    self.navigate_to(path, add_to_history=False)
                return

            # Default behavior for filesystem paths
            self.navigate_to(path, add_to_history=False)
            if hasattr(self, 'address_bar'):
                self.address_bar.setText(path)
    
    def sort_items(self, items, folder_path):
        """Sort items according to current tab's sort settings"""
        import re
        
        def natural_sort_key(text):
            """Convert a string to a list of mixed strings and numbers for natural sorting"""
            if not self.natural_sort:
                return text.lower() if not self.case_sensitive else text
                
            # Split string into chunks of letters and numbers
            chunks = re.split(r'(\d+)', text)
            # Convert number chunks to integers for proper sorting
            for i in range(len(chunks)):
                if chunks[i].isdigit():
                    chunks[i] = int(chunks[i])
                else:
                    chunks[i] = chunks[i].lower() if not self.case_sensitive else chunks[i]
            return chunks
        
        def get_sort_key(item_name):
            """Get the sort key for an item based on current sort settings"""
            full_path = os.path.join(folder_path, item_name)
            is_dir = os.path.isdir(full_path)
            
            # Primary sort: directories first if enabled
            primary_key = not is_dir if self.directories_first else 0
            
            # Secondary sort: by group type if enabled
            secondary_key = ""
            if self.group_by_type and not is_dir:
                extension = os.path.splitext(item_name)[1].lower()
                # Group by file type categories
                if extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                    secondary_key = "1_images"
                elif extension in ['.txt', '.pdf', '.doc', '.docx', '.rtf', '.odt']:
                    secondary_key = "2_documents"
                elif extension in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']:
                    secondary_key = "3_videos"
                elif extension in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma']:
                    secondary_key = "4_audio"
                elif extension in ['.py', '.js', '.html', '.css', '.cpp', '.java', '.c']:
                    secondary_key = "5_code"
                elif extension in ['.zip', '.rar', '.7z', '.tar', '.gz']:
                    secondary_key = "6_archives"
                else:
                    secondary_key = "7_other"
            
            # Tertiary sort: by the selected criteria
            tertiary_key = None
            try:
                if self.sort_by == "name":
                    tertiary_key = natural_sort_key(item_name)
                elif self.sort_by == "size":
                    if is_dir:
                        # For directories, use 0 size or count of items
                        try:
                            tertiary_key = len(os.listdir(full_path))
                        except:
                            tertiary_key = 0
                    else:
                        tertiary_key = os.path.getsize(full_path)
                elif self.sort_by == "date":
                    tertiary_key = os.path.getmtime(full_path)
                elif self.sort_by == "type":
                    if is_dir:
                        tertiary_key = "0_directory"  # Directories first in type sort
                    else:
                        extension = os.path.splitext(item_name)[1].lower()
                        tertiary_key = f"1_{extension}" if extension else "1_no_extension"
                elif self.sort_by == "extension":
                    if is_dir:
                        tertiary_key = ""
                    else:
                        extension = os.path.splitext(item_name)[1].lower()
                        tertiary_key = extension[1:] if extension else "zzz_no_extension"
                        if not self.case_sensitive:
                            tertiary_key = tertiary_key.lower()
                else:
                    tertiary_key = natural_sort_key(item_name)
            except (OSError, IOError):
                # If we can't get file info, fall back to name sorting
                tertiary_key = natural_sort_key(item_name)
            
            return (primary_key, secondary_key, tertiary_key)
        
        # Sort items
        sorted_items = sorted(items, key=get_sort_key)
        
        # Reverse if descending order
        if self.sort_order == "descending":
            sorted_items.reverse()
            
        return sorted_items

    def refresh_current_view(self):
        """Refresh the current view with files from current folder"""
        # This will be implemented based on the current view mode
        if self.view_stack.currentWidget() == self.thumbnail_view_widget:
            self.refresh_thumbnail_view()
        elif self.view_stack.currentWidget() == self.list_view:
            self.refresh_list_view()
        elif self.view_stack.currentWidget() == self.detail_view:
            self.refresh_detail_view()
    
    def refresh_thumbnail_view(self):
        """Refresh thumbnail view with current folder contents"""
        # Get settings from main window using direct reference
        main_window = self.tab_manager.main_window if self.tab_manager else None
        thumbnail_size = getattr(main_window, 'thumbnail_size', 64) if main_window else 64
        icons_wide = getattr(main_window, 'icons_wide', 0) if main_window else 0

        # If this tab is a My Computer drive-list, render connected drives instead
        if getattr(self, 'is_drive_list', False):
            try:
                icon_container = self.get_icon_container_safely()
                if not icon_container:
                    return
                layout = icon_container.layout()
                for i in reversed(range(layout.count())):
                    child = layout.itemAt(i).widget()
                    if child:
                        child.setParent(None)

                from PyQt5.QtCore import QDir
                # --- List drives first ---
                drives = QDir.drives()
                for d in drives:
                    try:
                        drive_path = d.absolutePath()
                        drive_name = drive_path
                        is_dir = True
                        icon_widget = IconWidget(drive_name, drive_path, is_dir, thumbnail_size, getattr(main_window, 'thumbnail_cache', None), use_icon_only=getattr(self, 'icon_view_active', False))
                        def _drv_dd(p, tab=self):
                            try:
                                if getattr(tab, 'is_drive_list', False) and isinstance(p, str) and os.path.isdir(p):
                                    tab.is_drive_list = False
                                    tab.list_model = FormattedFileSystemModel()
                                    tab.list_view.setModel(tab.list_model)
                                    tab.detail_model = FormattedFileSystemModel()
                                    tab.detail_view.setModel(tab.detail_model)
                                    tab.navigate_to(p)
                                    return
                                tab.handle_double_click(p)
                            except Exception:
                                pass
                        icon_widget.doubleClicked.connect(_drv_dd)
                        if self.tab_manager and self.tab_manager.main_window:
                            mw = self.tab_manager.main_window
                            icon_widget.clicked.connect(mw.icon_clicked)
                            icon_widget.rightClicked.connect(mw.icon_right_clicked)
                        icon_container.add_widget_optimized(icon_widget, thumbnail_size, icons_wide)
                    except Exception:
                        pass

                # --- Then add standard user folders (including Music) ---
                std_folders = [
                    ("Desktop", PlatformUtils.get_desktop_directory()),
                    ("Documents", PlatformUtils.get_documents_directory()),
                    ("Downloads", PlatformUtils.get_downloads_directory()),
                    ("Music", PlatformUtils.get_music_directory()),
                    ("Pictures", PlatformUtils.get_pictures_directory()),
                    ("Videos", PlatformUtils.get_videos_directory()),
                ]
                for label, folder_path in std_folders:
                    try:
                        if folder_path and os.path.exists(folder_path):
                            icon_widget = IconWidget(label, folder_path, True, thumbnail_size, getattr(main_window, 'thumbnail_cache', None), use_icon_only=getattr(self, 'icon_view_active', False))
                            def _std_dd(p, tab=self):
                                try:
                                    tab.is_drive_list = False
                                    tab.list_model = FormattedFileSystemModel()
                                    tab.list_view.setModel(tab.list_model)
                                    tab.detail_model = FormattedFileSystemModel()
                                    tab.detail_view.setModel(tab.detail_model)
                                    tab.navigate_to(p)
                                except Exception:
                                    pass
                            icon_widget.doubleClicked.connect(_std_dd)
                            if self.tab_manager and self.tab_manager.main_window:
                                mw = self.tab_manager.main_window
                                icon_widget.clicked.connect(mw.icon_clicked)
                                icon_widget.rightClicked.connect(mw.icon_right_clicked)
                            icon_container.add_widget_optimized(icon_widget, thumbnail_size, icons_wide)
                    except Exception:
                        pass

                layout.update()
                icon_container.update()
            except Exception:
                pass
            return

        # Pre-cache thumbnails for text and PDF files in the current folder for the current icon size only
        thumbnail_debug('Checking if main_window and thumbnail_cache exist for pre-caching in {}', self.current_folder)
        # Only precache thumbnails when not in Icon View (icon-only mode)
        try:
            in_icon_view = False
            if hasattr(main_window, 'icon_view_active'):
                in_icon_view = bool(main_window.icon_view_active)
            elif hasattr(main_window, 'view_mode_manager'):
                in_icon_view = (main_window.view_mode_manager.get_mode() == ViewModeManager.ICON_VIEW)
        except Exception:
            in_icon_view = False

        def after_thumbnailing():
            # Clear existing icons
            icon_container = self.get_icon_container_safely()
            if not icon_container:
                return  # Cannot refresh icons without icon_container
            layout = icon_container.layout()
            for i in reversed(range(layout.count())):
                child = layout.itemAt(i).widget()
                if child:
                    child.setParent(None)
            # Force layout update after clearing
            layout.update()
            icon_container.update()
            # Check if directory is large and use virtual loading if needed
            try:
                if main_window and hasattr(main_window, 'virtual_file_loader') and main_window.virtual_file_loader:
                    # Count items first to decide on loading strategy
                    item_count = len([name for name in os.listdir(self.current_folder) 
                                    if not name.startswith('.')])
                    if item_count > 1000:  # Use virtual loading for large directories
                        # Use virtual file loader for large directories
                        main_window.virtual_file_loader.load_directory_async(
                            self.current_folder,
                            lambda chunk, is_final: self._add_icons_chunk(chunk, is_final, thumbnail_size, icons_wide, main_window),
                            sort_func=lambda items: self.sort_items(items, self.current_folder)
                        )
                        return
                # Standard loading for smaller directories
                self._load_icons_standard(thumbnail_size, icons_wide, main_window)
            except PermissionError:
                pass

        if not in_icon_view and main_window and hasattr(main_window, 'thumbnail_cache') and main_window.thumbnail_cache:
            thumbnail_debug('About to call precache_text_pdf_thumbnails_in_directory for {} size={}', self.current_folder, thumbnail_size)
            try:
                precache_text_pdf_thumbnails_in_directory(
                    self.current_folder,
                    main_window.thumbnail_cache,
                    size=thumbnail_size,
                    on_complete=after_thumbnailing,
                    parent=main_window,
                    show_progress=True
                )
                thumbnail_debug('Finished call to precache_text_pdf_thumbnails_in_directory for {}', self.current_folder)
            except Exception as e:
                thumbnail_error('Exception in precache_text_pdf_thumbnails_in_directory: {}', e)
            return  # Only refresh after thumbnailing completes

        # If not thumbnailing, just refresh immediately
        after_thumbnailing()

        # Clear existing icons
        icon_container = self.get_icon_container_safely()
        if not icon_container:
            return  # Cannot refresh icons without icon_container
            
        layout = icon_container.layout()
        for i in reversed(range(layout.count())):
            child = layout.itemAt(i).widget()
            if child:
                child.setParent(None)
        
        # Force layout update after clearing
        layout.update()
        icon_container.update()
        
    # Check if directory is large and use virtual loading if needed
        try:
            if main_window and hasattr(main_window, 'virtual_file_loader') and main_window.virtual_file_loader:
                # Count items first to decide on loading strategy
                item_count = len([name for name in os.listdir(self.current_folder) 
                                if not name.startswith('.')])
                
                if item_count > 1000:  # Use virtual loading for large directories
                    # Use virtual file loader for large directories
                    main_window.virtual_file_loader.load_directory_async(
                        self.current_folder,
                        lambda chunk, is_final: self._add_icons_chunk(chunk, is_final, thumbnail_size, icons_wide, main_window),
                        sort_func=lambda items: self.sort_items(items, self.current_folder)
                    )
                    return
            
            # Standard loading for smaller directories
            self._load_icons_standard(thumbnail_size, icons_wide, main_window)
            
        except PermissionError:
            # Handle permission errors gracefully
            # ...removed thumbnail debug message...
            pass
    
    def _load_icons_standard(self, thumbnail_size, icons_wide, main_window):
        """Standard icon loading for smaller directories"""
        icon_container = self.get_icon_container_safely()
        if not icon_container:
            return  # Cannot load icons without icon_container
            
        items = os.listdir(self.current_folder)
        # If we're at the user's home or the filesystem root, show standard folders first
        try:
            home_dir = os.path.expanduser('~')
            cur_abs = os.path.abspath(self.current_folder)
            root_abs = os.path.abspath(os.sep)
            if cur_abs == os.path.abspath(home_dir) or cur_abs == root_abs:
                std_names = ['Desktop', 'Documents', 'Downloads', 'Pictures', 'Music', 'Videos']
                prepend = []
                for name in std_names:
                    candidate = os.path.join(home_dir, name)
                    # If the candidate exists and isn't already listed, show it first
                    if os.path.exists(candidate):
                        base = os.path.basename(candidate)
                        if base not in items:
                            prepend.append(base)
                # Prepend in reverse order so Desktop ends up first
                if prepend:
                    items = prepend + items
        except Exception:
            # Don't block listing if this logic fails
            pass
        
        # Use advanced sorting
        sorted_items = self.sort_items(items, self.current_folder)
        
        for item in sorted_items:
            self._create_and_add_icon(item, thumbnail_size, icons_wide, main_window)
        
        # Force layout update after adding widgets
        layout = icon_container.layout()
        layout.update()
        icon_container.update()
        icon_container.updateGeometry()
    
    def _add_icons_chunk(self, items_chunk, is_final, thumbnail_size, icons_wide, main_window):
        """Add a chunk of icons to the view (for virtual loading)"""
        icon_container = self.get_icon_container_safely()
        if not icon_container:
            return  # Cannot add icons without icon_container
            
        for item in items_chunk:
            self._create_and_add_icon(item, thumbnail_size, icons_wide, main_window)
        
        if is_final:
            # Force layout update after adding final chunk
            layout = icon_container.layout()
            layout.update()
            icon_container.update()
            icon_container.updateGeometry()
    
    def _create_and_add_icon(self, item, thumbnail_size, icons_wide, main_window):
        """Create and add a single icon widget"""
        icon_container = self.get_icon_container_safely()
        if not icon_container:
            return  # Cannot add icons without icon_container
            
        item_path = os.path.join(self.current_folder, item)
        is_dir = os.path.isdir(item_path)
        
        # Decide effective icon-only mode for this item. This combines:
        # - per-tab runtime flag (self.icon_view_active)
        # - main window view mode (ViewModeManager.ICON_VIEW)
        # - persisted user preference (main_window.icon_view_use_icons_only)
        effective_icon_only = False
        detected_mode = None
        try:
            if main_window and hasattr(main_window, 'view_mode_manager'):
                detected_mode = main_window.view_mode_manager.get_mode()

            # Are we in an icon view (either per-tab or main window mode)?
            in_icon_mode = False
            if hasattr(self, 'icon_view_active') and getattr(self, 'icon_view_active', False):
                in_icon_mode = True
            elif detected_mode == ViewModeManager.ICON_VIEW:
                in_icon_mode = True

            if in_icon_mode:
                # Respect persisted preference on the main window (default: True)
                pref = True
                if main_window and hasattr(main_window, 'icon_view_use_icons_only'):
                    pref = bool(main_window.icon_view_use_icons_only)
                effective_icon_only = bool(pref)
        except Exception:
            effective_icon_only = False

        # If we're not in effective icon-only mode and a thumbnail cache exists, provide it.
        if not effective_icon_only and main_window and hasattr(main_window, 'thumbnail_cache') and main_window.thumbnail_cache:
            icon_widget = IconWidget(item, item_path, is_dir, thumbnail_size, main_window.thumbnail_cache, use_icon_only=False)
        else:
            # If in icon-only mode, don't provide a thumbnail cache so IconWidget won't load thumbnails
            icon_widget = IconWidget(item, item_path, is_dir, thumbnail_size, None, use_icon_only=effective_icon_only)
            
        icon_widget.doubleClicked.connect(self.handle_double_click)
        
        # Connect to main window handlers through tab manager
        if self.tab_manager and self.tab_manager.main_window:
            main_window = self.tab_manager.main_window
            icon_widget.clicked.connect(main_window.icon_clicked)
            icon_widget.rightClicked.connect(main_window.icon_right_clicked)
        
        # Use the optimized layout from main window
        icon_container.add_widget_optimized(icon_widget, thumbnail_size, icons_wide)

    def refresh_list_view(self):
        """Refresh list view"""
        # If this tab shows drives, use the model root to enumerate drives rather than a folder path
        if getattr(self, 'is_drive_list', False):
            try:
                self.list_model.setRootPath("")
                self.list_view.setModel(self.list_model)
                self.list_view.setRootIndex(self.list_model.index(""))
            except Exception:
                self.list_model.setRootPath(QDir.rootPath())
                self.list_view.setRootIndex(self.list_model.index(QDir.rootPath()))
            return

        self.list_model.setRootPath(self.current_folder)
        self.list_view.setRootIndex(self.list_model.index(self.current_folder))
    
    def refresh_detail_view(self):
        """Refresh detail view"""
        # If this tab shows drives, set the detail model root to enumerate drives
        if getattr(self, 'is_drive_list', False):
            try:
                self.detail_model.setRootPath("")
                self.detail_view.setModel(self.detail_model)
                self.detail_view.setRootIndex(self.detail_model.index(""))
            except Exception:
                self.detail_model.setRootPath(QDir.rootPath())
                self.detail_view.setRootIndex(self.detail_model.index(QDir.rootPath()))
            return

        self.detail_model.setRootPath(self.current_folder)
        self.detail_view.setRootIndex(self.detail_model.index(self.current_folder))
    
    def resizeEvent(self, event):
        """Handle tab resize events to trigger auto-width recalculation"""
        super().resizeEvent(event)
        
        # If we're in auto-width mode, trigger a relayout of the icon container
        main_window = self.tab_manager.main_window if self.tab_manager else None
        if main_window and getattr(main_window, 'icons_wide', 0) == 0:
            # Get the current view's icon container safely
            icon_container = self.get_icon_container_safely()
            if icon_container:
                # Use a timer to prevent excessive relayout calls during resize
                if not hasattr(self, '_tab_resize_timer'):
                    from PyQt5.QtCore import QTimer
                    self._tab_resize_timer = QTimer()
                    self._tab_resize_timer.setSingleShot(True)
                    self._tab_resize_timer.timeout.connect(lambda: self.get_icon_container_safely() and self.get_icon_container_safely().relayout_icons())
                
                self._tab_resize_timer.stop()
                self._tab_resize_timer.start(150)  # Delay 150ms before relayout
    
    def eventFilter(self, obj, event):
        """Handle events from child widgets, specifically scroll area viewport resizes"""
        if (obj == getattr(self, 'scroll_area', None) or 
            obj == getattr(getattr(self, 'scroll_area', None), 'viewport', lambda: None)()):
            if event.type() == QEvent.Resize:
                # Viewport was resized, trigger auto-width recalculation if needed
                main_window = self.tab_manager.main_window if self.tab_manager else None
                if main_window and getattr(main_window, 'icons_wide', 0) == 0:
                    icon_container = self.get_icon_container_safely()
                    if icon_container:
                        # Use a shorter delay for viewport resize events
                        if not hasattr(self, '_viewport_resize_timer'):
                            from PyQt5.QtCore import QTimer
                            self._viewport_resize_timer = QTimer()
                            self._viewport_resize_timer.setSingleShot(True)
                            self._viewport_resize_timer.timeout.connect(lambda: self.get_icon_container_safely() and self.get_icon_container_safely().relayout_icons())
                        
                        self._viewport_resize_timer.stop()
                        self._viewport_resize_timer.start(50)  # Quick response for viewport changes
        
        return super().eventFilter(obj, event)
    
    def get_icon_container_safely(self):
        """Safely get icon_container reference, returns None if not available"""
        if hasattr(self, 'icon_container') and self.icon_container:
            return self.icon_container
        return None
    
    def handle_double_click(self, path):
        """Handle double click on file/folder"""
        if os.path.isdir(path):
            self.navigate_to(path)
        elif ArchiveManager.is_archive(path):
            # For archive files, always show browse dialog instead of opening externally
            if hasattr(self.parent(), 'browse_archive_contents'):
                self.parent().browse_archive_contents(path)
            else:
                # Try to find the main window with browse method
                main_window = self.parent()
                while main_window and not hasattr(main_window, 'browse_archive_contents'):
                    main_window = main_window.parent()
                if main_window:
                    main_window.browse_archive_contents(path)
                # If we still can't find the method, don't open with system default
                # Archive files should only be handled by built-in browser
        else:
            # Open non-archive file with default application
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class SmbBrowserTab(QWidget):
    """A tab for browsing an SMB (Samba) network share."""
    def __init__(self, server, share, username, password, domain='', start_path='/', parent=None):
        super().__init__(parent)
        self.smb = SMBNetworkUtils(server, share, username, password, domain)
        self.current_path = start_path
        self.layout = QVBoxLayout(self)
        self.path_label = QLabel()
        self.layout.addWidget(self.path_label)
        # Add download/upload buttons
        btn_layout = QHBoxLayout()
        self.download_btn = QPushButton("⬇ Download")
        self.download_btn.clicked.connect(self.download_selected_file)
        btn_layout.addWidget(self.download_btn)
        self.upload_btn = QPushButton("⬆ Upload")
        self.upload_btn.clicked.connect(self.upload_file)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.refresh()

    def download_selected_file(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        items = self.list_widget.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Select a file to download.")
            return
        name = items[0].text()
        remote_path = self.current_path.rstrip("/") + "/" + name
        # Ask user where to save
        save_path, _ = QFileDialog.getSaveFileName(self, "Save File As", name)
        if not save_path:
            return
        try:
            data = self.smb.read_file(remote_path)
            with open(save_path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Download Complete", f"Downloaded to {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Download Failed", str(e))

    def upload_file(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload")
        if not file_path:
            return
        name = os.path.basename(file_path)
        remote_path = self.current_path.rstrip("/") + "/" + name
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            self.smb.write_file(remote_path, data)
            QMessageBox.information(self, "Upload Complete", f"Uploaded {name}")
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Upload Failed", str(e))

    def refresh(self):
        self.path_label.setText(f"smb://{self.smb.server}/{self.smb.share}{self.current_path}")
        self.list_widget.clear()
        try:
            entries = self.smb.listdir(self.current_path)
            for entry in entries:
                self.list_widget.addItem(entry)
        except Exception as e:
            self.list_widget.addItem(f"[ERROR] {e}")

    def on_item_double_clicked(self, item):
        name = item.text()
        if name.startswith("[ERROR]"):
            return
        # Try to enter directory
        new_path = self.current_path.rstrip("/") + "/" + name
        try:
            entries = self.smb.listdir(new_path)
            self.current_path = new_path
            self.refresh()
        except Exception:
            pass  # Not a directory or error

class TabManager(QWidget):
    def add_smb_tab(self, server, share, username, password, domain='', start_path='/'):
        tab = SmbBrowserTab(server, share, username, password, domain, start_path, parent=self)
        tab_title = f"smb://{server}/{share}{start_path}"
        tab_index = self.tab_bar.addTab(tab_title)
        self.tab_stack.addWidget(tab)
        self.tabs.append(tab)
        self.tab_bar.setCurrentIndex(tab_index)
        self.tab_stack.setCurrentWidget(tab)
        if self.tab_changed_callback:
            self.tab_changed_callback()
        return tab
    """Manages multiple file manager tabs"""
    
    def __init__(self, parent=None, create_initial_tab=True):
        super().__init__(parent)
        self.main_window = parent  # Store direct reference to main window
        self.tabs = []  # Initialize before setup_ui
        self.tab_changed_callback = None  # Callback for when tabs change
        self.setup_ui()
        
        # Create initial tab only if requested
        if create_initial_tab:
            self.new_tab(os.path.expanduser("~"))
    
    def set_tab_changed_callback(self, callback):
        """Set callback to be called when tabs change"""
        self.tab_changed_callback = callback
        
    def setup_ui(self):
        """Setup the tab manager UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # Remove spacing between tab controls and content
        
        # Tab bar and controls
        tab_controls = QHBoxLayout()
        tab_controls.setContentsMargins(0, 0, 0, 0)  # Remove margins from tab controls
        tab_controls.setSpacing(2)  # Minimal spacing between tab bar and buttons
        
        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.currentChanged.connect(self.tab_changed)
        self.tab_bar.tabMoved.connect(self.tab_moved)
        tab_controls.addWidget(self.tab_bar)
        
        # New tab button
        self.new_tab_btn = QPushButton("+")
        self.new_tab_btn.setFixedSize(30, 25)
        self.new_tab_btn.setToolTip("New Tab")

        def _new_tab_clicked():
            try:
                # placeholder
                _ = None
            except Exception:
                pass
            try:
                # Open a new tab at the user's home directory when New Tab is clicked
                self.new_tab(os.path.expanduser("~"))
            except Exception:
                try:
                    self.new_tab(os.path.expanduser("~"))
                except Exception:
                    pass

        try:
            self.new_tab_btn.clicked.connect(_new_tab_clicked)
        except Exception:
            self.new_tab_btn.clicked.connect(self.new_tab)
        tab_controls.addWidget(self.new_tab_btn)
        
        tab_controls.addStretch()
        
        layout.addLayout(tab_controls)
        
        # Tab content area
        self.tab_stack = QStackedWidget()
        layout.addWidget(self.tab_stack)
        
        self.setLayout(layout)
        
        # Initial tab creation is handled by parent class now
    
    def new_tab(self, initial_path=None):
        """Create a new tab"""
    # TabManager.new_tab called
        # If no initial_path specified and running on Windows, open My Computer (drive list)
        if initial_path is None:
            try:
                if PlatformUtils.is_windows():
                    # Use sentinel so FileManagerTab can initialize a drive-list view
                    initial_path = "__MY_COMPUTER__"
                else:
                    initial_path = os.path.expanduser("~")
            except Exception:
                initial_path = os.path.expanduser("~")
        # Accept ftp:// and sftp:// addresses as-is
        is_remote = False
        if isinstance(initial_path, str) and (initial_path.startswith('ftp://') or initial_path.startswith('sftp://')):
            is_remote = True
        # If initial_path is the My Computer sentinel, treat it as a special drive-list view
        is_drive_list = (initial_path == "__MY_COMPUTER__")
        # For local paths, ensure the path exists
        if not is_remote and not is_drive_list:
            if not isinstance(initial_path, str):
                initial_path = os.path.expanduser("~")
            if not os.path.exists(initial_path) or not os.path.isdir(initial_path):
                initial_path = os.path.expanduser("~")
        tab = FileManagerTab(initial_path, self)
        self.tabs.append(tab)
        # Install event filter for right-click handling on this tab's scroll area
        if hasattr(self, 'main_window') and self.main_window:
            tab.scroll_area.viewport().installEventFilter(self.main_window)
        # Tab title for remote: show address, for local: show folder name
        if is_remote:
            tab_title = initial_path
        elif is_drive_list:
            tab_title = "My Computer"
        else:
            tab_title = os.path.basename(initial_path) or "Home"
        tab_index = self.tab_bar.addTab(tab_title)
        self.tab_stack.addWidget(tab)
        # Switch to new tab
        self.tab_bar.setCurrentIndex(tab_index)
        self.tab_stack.setCurrentWidget(tab)
        # Notify about tab change
        if self.tab_changed_callback:
            self.tab_changed_callback()
        return tab
    
    def close_tab(self, index):
        """Close a tab"""
        if len(self.tabs) <= 1:
            return  # Don't close the last tab
        
        if not (0 <= index < len(self.tabs)):
            return  # Invalid index
        
        tab = self.tabs[index]
        
        # Save sort settings before closing the tab
        if hasattr(self.main_window, 'save_tab_sort_settings'):
            self.main_window.save_tab_sort_settings(tab)
        
        # Remove from our list first
        # Unregister monitored directory for this tab if present
        try:
            if hasattr(tab, '_monitored_directory') and tab._monitored_directory:
                try:
                    if hasattr(self, 'main_window') and getattr(self, 'main_window') and hasattr(self.main_window, 'background_monitor'):
                        self.main_window.background_monitor.remove_directory(tab._monitored_directory)
                except Exception:
                    pass
        except Exception:
            pass

        self.tabs.remove(tab)
        
        # Remove from UI components
        self.tab_bar.removeTab(index)
        self.tab_stack.removeWidget(tab)
        
        # Clean up the widget
        tab.deleteLater()
        
        # If the current tab was closed, switch to a valid tab
        current_index = self.tab_bar.currentIndex()
        if current_index >= len(self.tabs) and len(self.tabs) > 0:
            new_index = len(self.tabs) - 1
            self.tab_bar.setCurrentIndex(new_index)
            self.tab_stack.setCurrentWidget(self.tabs[new_index])
        
        # Notify about tab change
        if self.tab_changed_callback:
            self.tab_changed_callback()
    
    def tab_changed(self, index):
        """Handle tab change"""
        if 0 <= index < len(self.tabs):
            target_tab = self.tabs[index]
            # Verify the widget is in the stack before setting it
            stack_widget_index = self.tab_stack.indexOf(target_tab)
            if stack_widget_index >= 0:
                self.tab_stack.setCurrentWidget(target_tab)
            else:
                print(f"Warning: Tab widget at index {index} not found in stack")
                # Fallback: use stack index instead
                if index < self.tab_stack.count():
                    self.tab_stack.setCurrentIndex(index)
            
            # Notify about tab change
            if self.tab_changed_callback:
                self.tab_changed_callback()
    
    def tab_moved(self, from_index, to_index):
        """Handle tab reordering"""
        if 0 <= from_index < len(self.tabs) and 0 <= to_index < len(self.tabs):
            # Move the tab widget in the tabs list to match the new order
            tab_widget = self.tabs.pop(from_index)
            self.tabs.insert(to_index, tab_widget)
            
            # Update the stacked widget order to match
            # Remove the widget from its current position
            self.tab_stack.removeWidget(tab_widget)
            # Insert it at the new position
            self.tab_stack.insertWidget(to_index, tab_widget)
            
            # Ensure the current tab view is still correct after reordering
            current_index = self.tab_bar.currentIndex()
            if 0 <= current_index < len(self.tabs):
                self.tab_stack.setCurrentWidget(self.tabs[current_index])
    
    def update_tab_title(self, tab, title):
        """Update tab title"""
        try:
            index = self.tabs.index(tab)
            self.tab_bar.setTabText(index, title)
        except ValueError:
            pass  # Tab not found
    
    def get_current_tab(self):
        """Get the currently active tab"""
        current_index = self.tab_bar.currentIndex()
        if 0 <= current_index < len(self.tabs):
            return self.tabs[current_index]
        return None
    
    def get_current_path(self):
        """Get current path from active tab"""
        current_tab = self.get_current_tab()
        return current_tab.current_folder if current_tab else os.path.expanduser("~")

class SimpleFileManager(QMainWindow):
    def load_view_mode(self):
        settings = QSettings("garysfm", "garysfm")
        mode = settings.value("view_mode", None)
        if mode is not None:
            self.set_view_mode(mode)

    def save_view_mode(self, mode):
        settings = QSettings("garysfm", "garysfm")
        settings.setValue("view_mode", str(mode))
    SETTINGS_FILE = "filemanager_settings.json"

    def __init__(self):
        super().__init__()
        self.clipboard_data = None
        self.thumbnail_size = 64  # Default thumbnail size

        # Control verbose thumbnail logging during development and tests.
        # Set to False in production to avoid huge console output.
        THUMBNAIL_VERBOSE = False

        def thumbnail_debug(msg, *args):
            try:
                if THUMBNAIL_VERBOSE:
                    print(f"[THUMBNAIL-DEBUG] {msg.format(*args)}")
            except Exception:
                pass

        def thumbnail_info(msg, *args):
            try:
                if THUMBNAIL_VERBOSE:
                    print(f"[THUMBNAIL-INFO] {msg.format(*args)}")
            except Exception:
                pass

        def thumbnail_error(msg, *args):
            try:
                # Always show errors so failures are visible even when verbose is off
                print(f"[THUMBNAIL-ERROR] {msg.format(*args)}")
            except Exception:
                pass

        
        # Initialize dark mode as default on all platforms
        # Only use system detection on macOS if user prefers, otherwise default to dark
        self.dark_mode = True  # Default to dark mode on all platforms
            
        self.icons_wide = 0  # 0 means auto-calculate, >0 means fixed width

        # Color themes mapping (light palettes). Dark mode remains an override.
        # Each theme is a dict of basic colors used by apply_theme
        self.COLOR_THEMES = {
            'Default Light': {
                'window_bg': '#ffffff', 'panel_bg': '#f5f5f5', 'text': '#000000', 'accent': '#0078d7'
            },
            'Soft Blue': {
                'window_bg': '#f3f8ff', 'panel_bg': '#e9f0ff', 'text': '#07273b', 'accent': '#1e90ff'
            },
            'Warm Sand': {
                'window_bg': '#fffaf0', 'panel_bg': '#fff3e0', 'text': '#3b2f2f', 'accent': '#d87a3a'
            },
            'Mint': {
                'window_bg': '#f6fff8', 'panel_bg': '#ecfff1', 'text': '#11332b', 'accent': '#2bb673'
            },
            'Gum': {
                'window_bg': '#fff5f6',
                'panel_bg': '#ffecec',
                'text': '#330000',
                'accent': '#d9534f'
            },
            'Grape': {
                'window_bg': '#fbf7ff',
                'panel_bg': '#f3eefe',
                'text': '#2b0236',
                'accent': '#6f2dbd'
            },
            'Orange': {
                'window_bg': '#fffaf2',
                'panel_bg': '#fff1e0',
                'text': '#3a1f00',
                'accent': '#ff5a2a'
            },
            # Lower-contrast, gamma-blended themes
            'Foggy Grey': {
                'window_bg': '#f6f7fa',
                'panel_bg': '#eceef1',
                'text': '#44474a',
                'accent': '#8a9ba8'
            },
            'Pastel Green': {
                'window_bg': '#f7fbf7',
                'panel_bg': '#eaf6ea',
                'text': '#4a564a',
                'accent': '#8fc49b'
            },
            'Lavender Mist': {
                'window_bg': '#f8f7fa',
                'panel_bg': '#f0eef6',
                'text': '#4d4a56',
                'accent': '#b6a4d6'
            },
            'Peach Cream': {
                'window_bg': '#fdf7f4',
                'panel_bg': '#faede7',
                'text': '#5a4a44',
                'accent': '#e7bfa7'
            },
            'Sunny Yellow': {
                'window_bg': '#fffef0',
                'panel_bg': '#fffae0',
                'text': '#3b3500',
                'accent': '#f1c40f'
            },
        }

        # Dark-mode variants for the named color themes. When dark_mode is enabled
        # we prefer these palettes so the selected theme feels consistent in dark.
        # Keys mirror those in COLOR_THEMES.
        self.DARK_COLOR_THEMES = {
            'Default Light': {
                'window_bg': '#2b2b2b', 'panel_bg': '#363636', 'text': '#ffffff', 'accent': '#3daee9'
            },
            'Soft Blue': {
                'window_bg': '#161b22', 'panel_bg': '#1f2732', 'text': '#dbeeff', 'accent': '#5aa8ff'
            },
            'Warm Sand': {
                'window_bg': '#201714', 'panel_bg': '#2b1f1a', 'text': '#f3e8e0', 'accent': '#ff9f6b'
            },
            'Mint': {
                'window_bg': '#071614', 'panel_bg': '#0d2620', 'text': '#d9f6ec', 'accent': '#5ee3a1'
            },
            'Gum': {
                'window_bg': '#2a1f20', 'panel_bg': '#361a1b', 'text': '#ffdede', 'accent': '#ff6b68'
            },
            'Grape': {
                'window_bg': '#141018', 'panel_bg': '#1b1322', 'text': '#efe6ff', 'accent': '#a96bff'
            },
            'Orange': {
                'window_bg': '#1a0f0a', 'panel_bg': '#271710', 'text': '#ffeedb', 'accent': '#ff7a50'
            },
            # Lower-contrast, gamma-blended dark themes
            'Foggy Grey': {
                'window_bg': '#232427',
                'panel_bg': '#2c2d30',
                'text': '#bfc3c7',
                'accent': '#7c8a99'
            },
            'Pastel Green': {
                'window_bg': '#1d2320',
                'panel_bg': '#232a25',
                'text': '#b7c9b7',
                'accent': '#7fae8a'
            },
            'Lavender Mist': {
                'window_bg': '#232227',
                'panel_bg': '#2a2830',
                'text': '#c7c3d7',
                'accent': '#a89bc9'
            },
            'Peach Cream': {
                'window_bg': '#282321',
                'panel_bg': '#322a27',
                'text': '#e7d7cf',
                'accent': '#c9a88a'
            },
        }

        # Strong-mode palettes: vibrant, high-contrast accents for dramatic UI
        self.STRONG_COLOR_THEMES = {
            'Vivid Sunset': {
                # Deep warm background with a very bright orange accent
                'window_bg': '#1b0b00', 'panel_bg': '#2b0f00', 'text': '#ffdcb8', 'accent': '#ff5a00'
            },
            'Electric Lime': {
                # Dark green/black canvas with neon lime accent
                'window_bg': '#071104', 'panel_bg': '#0b1606', 'text': "#fcfffa", 'accent': '#66ff00'
            },
            'Neon Violet': {
                # Deep purple/indigo background with vivid magenta accent
                'window_bg': "#120018", 'panel_bg': "#1e002f", 'text': "#ffee00", 'accent': '#c400ff'
            },
            'Royal Indigo': {
                # Deep blue/indigo background with electric blue accent
                'window_bg': "#001122", 'panel_bg': "#002040", 'text': "#e0f0ff", 'accent': '#0088ff'
            },
            'Crimson Royale': {
                # Deep red/burgundy background with bright red accent
                'window_bg': "#220011", 'panel_bg': "#400020", 'text': "#ffe0f0", 'accent': '#ff0044'
            },
            'Deep Violet': {
                # Deep purple background with bright violet accent
                'window_bg': "#110022", 'panel_bg': "#200040", 'text': "#f0e0ff", 'accent': '#8800ff'
            },
            'Forest Emerald': {
                # Deep green/forest background with bright emerald accent
                'window_bg': "#001100", 'panel_bg': "#002200", 'text': "#e0ffe0", 'accent': '#00ff44'
            },
            'Sunset Blaze': {
                # Deep orange/amber background with bright orange accent
                'window_bg': "#221100", 'panel_bg': "#442200", 'text': "#fff0e0", 'accent': '#ff6600'
            },
            'Hot Magenta': {
                # Deep magenta background with bright hot pink accent
                'window_bg': "#220011", 'panel_bg': "#440022", 'text': "#ffe0ff", 'accent': '#ff0088'
            },
            'Mocha Elite': {
                # Deep brown/chocolate background with warm amber accent
                'window_bg': "#221811", 'panel_bg': "#443022", 'text': "#f0e8d0", 'accent': '#cc8844'
            },
            'Golden Thunder': {
                # Deep black/dark brown background with electric yellow accent
                'window_bg': "#1b1800", 'panel_bg': "#332d00", 'text': "#fffee0", 'accent': '#ffdd00'
            }
        }

        # Subdued-mode palettes: more understated themes (now empty)
        self.SUBDUED_COLOR_THEMES = {
            'Muted Gold': {
                # Soft, understated yellow theme with low contrast
                'window_bg': '#f9f8f4',
                'panel_bg': '#f4f2ea',
                'text': '#5a5748',
                'accent': '#b8a558'
            }
        }

        # Strong theme mapping from regular themes to strong variants
        self.STRONG_THEME_MAP = {
            'Default Light': 'Vivid Sunset',
            'Soft Blue': 'Royal Indigo',
            'Warm Sand': 'Mocha Elite',
            'Mint': 'Electric Lime',
            'Gum': 'Hot Magenta',
            'Grape': 'Neon Violet',
            'Orange': 'Sunset Blaze',
            'Foggy Grey': 'Deep Violet',
            'Pastel Green': 'Forest Emerald',
            'Lavender Mist': 'Deep Violet',
            'Peach Cream': 'Sunset Blaze'
        }

        # Subdued theme mapping (now empty since no subdued themes exist)
        self.SUBDUED_THEME_MAP = {
        }

        # Generate stronger, darker subdued variants from the existing
        # named light themes so Subdued Themes don't look pastel.
        try:
            from PyQt5.QtGui import QColor

            def _darker(hexcol, factor=140):
                try:
                    q = QColor(hexcol)
                    # QColor.darker expects an int percentage (100 = same)
                    return q.darker(factor).name()
                except Exception:
                    return hexcol

            # For each named theme, create a "<Name> Subdued" entry unless one exists
            for base_name, base_theme in list(self.COLOR_THEMES.items()):
                subdued_key = f"{base_name} Subdued"
                if subdued_key in self.SUBDUED_COLOR_THEMES:
                    continue

                win = base_theme.get('window_bg') or base_theme.get('panel_bg') or '#111111'
                panel = base_theme.get('panel_bg') or win
                accent = base_theme.get('accent') or '#ff4d00'

                # Make backgrounds significantly stronger/darker than the light theme
                win_v = _darker(win, 160)   # stronger/darker window background
                panel_v = _darker(panel, 140)  # slightly lighter than window_v

                # Ensure accent is vivid: if it's too pale, darken it OR boost contrast
                try:
                    aq = QColor(accent)
                    # If accent is very light, darken it; otherwise keep it
                    if aq.lightness() > 200:
                        acc_v = aq.darker(140).name()
                    else:
                        acc_v = aq.name()
                except Exception:
                    acc_v = accent

                # Prefer white text for dark subdued backgrounds
                txt_v = '#ffffff'

                self.SUBDUED_COLOR_THEMES[subdued_key] = {
                    'window_bg': win_v,
                    'panel_bg': panel_v,
                    'text': txt_v,
                    'accent': acc_v
                }

                # If no explicit mapping existed, map the base theme to this subdued variant
                try:
                    self.SUBDUED_THEME_MAP.setdefault(base_name, subdued_key)
                except Exception:
                    pass
        except Exception:
            # If QColor isn't available, skip auto-generation silently
            pass

        # Subdued mode flag (persisted separately)
        try:
            settings = QSettings('garysfm', 'garysfm')
            stored_subdued = settings.value('subdued_mode', None)
            if stored_subdued is not None:
                self.subdued_mode = True if str(stored_subdued).lower() in ('1', 'true', 'yes') else False
                # If subdued mode is enabled, restore the saved subdued theme
                if self.subdued_mode:
                    stored_subdued_theme = settings.value('subdued_theme', None)
                    if stored_subdued_theme:
                        self.color_theme = stored_subdued_theme
            else:
                self.subdued_mode = False
        except Exception:
            self.subdued_mode = False

        # Strong mode flag (persisted separately)
        try:
            settings = QSettings('garysfm', 'garysfm')
            stored_strong = settings.value('strong_mode', None)
            if stored_strong is not None:
                self.strong_mode = True if str(stored_strong).lower() in ('1', 'true', 'yes') else False
                # If strong mode is enabled, restore the saved strong theme
                if self.strong_mode:
                    stored_strong_theme = settings.value('strong_theme', None)
                    if stored_strong_theme and stored_strong_theme in self.STRONG_COLOR_THEMES:
                        self.color_theme = stored_strong_theme
                    else:
                        # If no valid strong theme is saved, use the first available strong theme
                        try:
                            self.color_theme = next(iter(self.STRONG_COLOR_THEMES.keys()))
                        except StopIteration:
                            self.color_theme = 'Vivid Sunset'  # fallback
            else:
                self.strong_mode = False
        except Exception:
            self.strong_mode = False

        # Load persisted color theme and dark mode preference
        # Compute recommended text color for themes based on contrast ratio (black or white)
        try:
            from PyQt5.QtGui import QColor

            def _rel_luminance(qc):
                r, g, b, _ = qc.getRgb()
                rs = r / 255.0
                gs = g / 255.0
                bs = b / 255.0
                def _adj(c):
                    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                return 0.2126 * _adj(rs) + 0.7152 * _adj(gs) + 0.0722 * _adj(bs)

            def _contrast_ratio(l1, l2):
                a = max(l1, l2)
                b = min(l1, l2)
                return (a + 0.05) / (b + 0.05)

            def _pick_text_for_bg(bg_hex, current_text_hex=None):
                try:
                    bg = QColor(bg_hex)
                    l_bg = _rel_luminance(bg)
                    # contrast with black
                    l_black = 0.0
                    l_white = 1.0
                    contrast_black = _contrast_ratio(l_bg, l_black)
                    contrast_white = _contrast_ratio(l_bg, l_white)
                    # If current_text provided, prefer it when adequate
                    if current_text_hex:
                        cur = QColor(current_text_hex)
                        l_cur = _rel_luminance(cur)
                        if _contrast_ratio(l_bg, l_cur) >= 4.5:
                            return current_text_hex
                    return '#000000' if contrast_black >= contrast_white else '#ffffff'
                except Exception:
                    return current_text_hex or '#000000'

            # Annotate light themes
            for k, v in self.COLOR_THEMES.items():
                try:
                    win_bg = v.get('window_bg') or v.get('panel_bg')
                    cur_text = v.get('text')
                    v['recommended_text'] = _pick_text_for_bg(win_bg, cur_text)
                except Exception:
                    v['recommended_text'] = v.get('text', '#000000')

            # Annotate dark themes similarly
            for k, v in self.DARK_COLOR_THEMES.items():
                try:
                    win_bg = v.get('window_bg') or v.get('panel_bg')
                    cur_text = v.get('text')
                    v['recommended_text'] = _pick_text_for_bg(win_bg, cur_text)
                except Exception:
                    v['recommended_text'] = v.get('text', '#ffffff')
        except Exception:
            # If QColor isn't available at this phase, skip recommendations silently
            pass
        try:
            settings = QSettings('garysfm', 'garysfm')
            stored_theme = settings.value('color_theme', None)
            # Only load regular theme if not in subdued mode or strong mode
            if not getattr(self, 'subdued_mode', False) and not getattr(self, 'strong_mode', False):
                if stored_theme and stored_theme in self.COLOR_THEMES:
                    self.color_theme = stored_theme
                else:
                    self.color_theme = 'Default Light'
            stored_dark = settings.value('dark_mode', None)
            if stored_dark is not None:
                # QSettings may return 'true'/'false' or bool
                self.dark_mode = True if str(stored_dark).lower() in ('1', 'true', 'yes') else False
        except Exception:
            if not getattr(self, 'subdued_mode', False) and not getattr(self, 'strong_mode', False):
                self.color_theme = 'Default Light'
        
        # View panel states (default hidden for cleaner interface)
        self.show_tree_view = False
        self.show_preview_pane = False
        self.search_visible = False
        
        # Define cleanup methods before they're used
        def _cleanup_thumbnails():
            """Clean up thumbnail cache memory"""
            try:
                if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                    self.thumbnail_cache.clear_memory_cache()
                    # Break circular references
                    if hasattr(self.thumbnail_cache, 'memory_cache'):
                        del self.thumbnail_cache.memory_cache
                        self.thumbnail_cache.memory_cache = OrderedDict()
            except Exception as e:
                # ...removed cache debug message...
                pass

        def _cleanup_virtual_loader():
            """Clean up virtual file loader resources"""
            try:
                if hasattr(self, 'virtual_file_loader') and self.virtual_file_loader:
                    self.virtual_file_loader.cleanup()
                    # Clear references to prevent memory leaks
                    if hasattr(self.virtual_file_loader, 'loaded_chunks'):
                        self.virtual_file_loader.loaded_chunks.clear()
                    if hasattr(self.virtual_file_loader, 'directory_cache'):
                        self.virtual_file_loader.directory_cache.clear()
            except Exception as e:
                print(f"Error in virtual loader cleanup: {e}")
        
        # Bind cleanup methods to self
        self._cleanup_thumbnails = _cleanup_thumbnails
        self._cleanup_virtual_loader = _cleanup_virtual_loader
        
        # Initialize performance optimization components (FIXED CLEANUP)
        self.thumbnail_cache = ThumbnailCache()
        self.virtual_file_loader = VirtualFileLoader()
        self.memory_manager = MemoryManager()
        self.background_monitor = BackgroundFileMonitor()
        
        # Initialize advanced search engine
        self.search_engine = SearchEngine()
        
        # Register cleanup callbacks for memory management
        if self.memory_manager:
            self.memory_manager.add_cleanup_callback(self._cleanup_thumbnails)
            self.memory_manager.add_cleanup_callback(self._cleanup_virtual_loader)
            self.memory_manager.add_cleanup_callback(lambda: self.search_engine.cleanup())
        
        # Initialize managers first (needed for settings loading)
        self.clipboard_manager = ClipboardHistoryManager()
        self.view_mode_manager = ViewModeManager()
        # Register drive change callback to update My Computer tabs/tree
        try:
            def _on_drives_changed(drives):
                try:
                    # Update left tree view if showing My Computer
                    try:
                        if hasattr(self, 'tree_view') and self.path_label and self.path_label.text() == 'My Computer':
                            try:
                                root_index = self.model.index("")
                                self.tree_view.setRootIndex(root_index)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Refresh any open My Computer tabs
                    try:
                        if hasattr(self, 'tab_manager') and self.tab_manager:
                            for t in list(self.tab_manager.tabs):
                                try:
                                    if getattr(t, 'is_drive_list', False):
                                        try:
                                            t.refresh_current_view()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    pass
            self.background_monitor.add_drive_callback(_on_drives_changed)
        except Exception:
            pass
    # ...existing code for UI setup, actions, toolbar, etc...
    # ...existing code for status bar, shortcuts, restoring session, etc...
    # Now load persistent view mode as the last step
    # ...existing code...
    # Restore tab session from previous launch
    # ...existing code...
        # Load persistent user settings from JSON (simple flat structure)
        try:
            self.icon_view_use_icons_only = True
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings_json = json.load(f)
                # backward-compatible keys
                self.icon_view_use_icons_only = bool(settings_json.get('icon_view_use_icons_only', settings_json.get('user_prefs', {}).get('icon_view_use_icons_only', True)))
        except Exception:
            # Default if anything goes wrong
            self.icon_view_use_icons_only = True
        
        self.last_dir = self.load_last_dir() or QDir.rootPath()
        self.selected_icon = None  # Track selected icon
        self.selected_items = []  # Track multiple selected items
        self.error_count = 0  # Track errors for improved error handling
        self.current_search_results = []
        
        # Main layout with splitter for resizable panes
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        # Minimize spacing between toolbar and content
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)

        # Toolbar for quick access
        self.create_toolbar()

        # Add breadcrumb navigation at the top
        self.breadcrumb = BreadcrumbWidget()
        self.breadcrumb.pathClicked.connect(self.navigate_to_path)
        self.main_layout.addWidget(self.breadcrumb)

        # Search and filter widget (enhanced version with advanced capabilities)
        self.search_filter = SearchFilterWidget()
        # Connect search results to display handler
        self.search_filter.searchRequested.connect(self.handle_advanced_search_results)
        # Note: The new SearchFilterWidget is self-contained and doesn't need a searchRequested connection
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
        # Remove vertical spacing between toolbar and tabs
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(0)
        self.center_pane.setLayout(self.center_layout)
        self.content_splitter.addWidget(self.center_pane)

        # Multiple view widgets
        self.setup_multiple_views()

        # View mode controls (My Computer button etc.) — created after tab manager exists
        self.setup_view_mode_controls()

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

        # Setup macOS-specific window behavior
        PlatformUtils.setup_macos_window_behavior(self)

        # Initialize file system model
        self.setup_file_system_model()

        # Setup menus with enhanced options
        self.setup_enhanced_menus()

        # Load persisted event-filter verbose setting (controls debug prints from eventFilter helpers)
        try:
            settings = QSettings('garysfm', 'garysfm')
            val = settings.value('event_filter_verbose', False)
            # normalize possible string values
            global EVENT_FILTER_VERBOSE
            if isinstance(val, str):
                EVENT_FILTER_VERBOSE = True if val.lower() in ('true', '1') else False
            else:
                EVENT_FILTER_VERBOSE = bool(val)
        except Exception:
            pass

        # For right-click context menu
        self.current_right_clicked_path = None

        # Add status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Setup keyboard shortcuts
        self.setup_enhanced_keyboard_shortcuts()

        # Migrate old sort settings to new deterministic format
        self.migrate_tab_sort_settings()

        # Restore tab session from previous launch
        self.restore_tab_session()
        # Load persistent view mode only after tab manager and tabs are restored
        self.load_view_mode()

        # Connect signals from current active tab
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            self.connect_tab_signals(current_tab)

        self.selected_items = []

        # Restore view states from settings
        self.restore_view_states()

        # Apply dark mode if it was saved
        self.apply_dark_mode()
        
        # Ensure theme is applied after all initialization
        self.apply_theme()

        # Enable drag and drop
        self.setAcceptDrops(True)
        self.update_dark_mode_checkmark()
        QTimer.singleShot(100, self.refresh_all_themes)

        # Initialize status bar after everything is set up
        QTimer.singleShot(0, self.safe_update_status_bar)

    def dragEnterEvent(self, event):
        """Accept drag event if it contains URLs (files/folders)."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle drop event for files/folders."""
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            # You can customize what to do with the dropped files/folders here
            # For example, open them, copy, or display in the UI
            self.handle_dropped_files(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def handle_dropped_files(self, paths):
        """Custom handler for dropped files/folders. Override as needed."""
        # If files are dropped, open the SourceForge upload dialog
        # pre-filled with all dropped paths and optionally auto-start.
        if not paths:
            return
        try:
            self.show_sourceforge_upload_dialog(prefill_paths=paths, auto_start=True)
        except Exception:
            # Fallback: just print the dropped paths
            print("Dropped files/folders:", paths)

    def create_toolbar(self):
        """Create the main toolbar"""
        self.toolbar = QToolBar()
        # Make toolbar more compact to reduce vertical space
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toolbar.setIconSize(QSize(16, 16))  # Smaller icons
        self.toolbar.setContentsMargins(0, 0, 0, 0)  # Remove toolbar margins
        self.toolbar.setStyleSheet("QToolBar { border: 0px; padding: 0px; margin: 0px; }")
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

        # View mode buttons (thumbnail replaces icon view)
        self.thumbnail_view_action = QAction("# Thumbnails", self, checkable=True, checked=True)
        self.icon_view_action = QAction("○ Icons", self, checkable=True)
        self.list_view_action = QAction("= List", self, checkable=True)
        self.detail_view_action = QAction("+ Details", self, checkable=True)

        self.thumbnail_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.THUMBNAIL_VIEW))
        self.icon_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.ICON_VIEW))
        self.list_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.LIST_VIEW))
        self.detail_view_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.DETAIL_VIEW))

        self.toolbar.addAction(self.thumbnail_view_action)
        self.toolbar.addAction(self.icon_view_action)
        self.toolbar.addAction(self.list_view_action)
        self.toolbar.addAction(self.detail_view_action)
        self.toolbar.addSeparator()

        # Search toggle with advanced search indicator
        self.search_toggle_action = QAction("🔍 Search", self, checkable=True)
        self.search_toggle_action.triggered.connect(self.toggle_search_pane)
        self.search_toggle_action.setToolTip("Toggle Advanced Search Panel (Ctrl+F)")
        self.toolbar.addAction(self.search_toggle_action)

        # Clipboard history
        self.clipboard_history_action = QAction("[] Clipboard", self)
        self.clipboard_history_action.triggered.connect(self.show_clipboard_history)
        self.toolbar.addAction(self.clipboard_history_action)



    def open_network_folder_dialog(self):
        """Show a dialog to connect to a network (SMB) folder and open it in a new tab."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Connect to Network Share (SMB)")
        layout = QFormLayout(dlg)
        server_edit = QLineEdit()
        share_edit = QLineEdit()
        user_edit = QLineEdit()
        pass_edit = QLineEdit()
        pass_edit.setEchoMode(QLineEdit.Password)
        domain_edit = QLineEdit()
        path_edit = QLineEdit()
        layout.addRow("Server:", server_edit)
        layout.addRow("Share:", share_edit)
        layout.addRow("Username:", user_edit)
        layout.addRow("Password:", pass_edit)
        layout.addRow("Domain (optional):", domain_edit)
        layout.addRow("Path (e.g. / or /folder):", path_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        def on_connect():
            from PyQt5.QtWidgets import QMessageBox
            server = server_edit.text().strip()
            share = share_edit.text().strip()
            user = user_edit.text().strip()
            passwd = pass_edit.text()
            domain = domain_edit.text().strip()
            path = path_edit.text().strip() or "/"
            if not (server and share and user and passwd):
                QMessageBox.warning(dlg, "Missing Info", "Please fill in all required fields.")
                return
            try:
                self.tab_manager.add_smb_tab(server, share, user, passwd, domain, path)
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Connection Error", str(e))
        buttons.accepted.connect(on_connect)
        buttons.rejected.connect(dlg.reject)
        dlg.exec_()

    def setup_tree_view(self):
        """Setup the tree view for folder navigation"""
        self.model = QFileSystemModel()

        # Always show filesystem root (drive list) in the tree view
        # Use empty rootPath so QFileSystemModel exposes all drives on Windows
        self.model.setRootPath("")

        # Only show directories (and drives) in the tree view — no files
        # Include NoDotAndDotDot and Drives to ensure root drives are visible on Windows
        self.model.setFilter(QDir.Drives | QDir.Dirs | QDir.NoDotAndDotDot)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)

        # Always show drives/root in the tree for navigation (use empty root to list drives)
        try:
            root_index = self.model.index("")
            self.tree_view.setRootIndex(root_index)
        except Exception:
            # Fallback to home dir if root can't be used for some reason
            home_dir = PlatformUtils.get_home_directory()
            self.tree_view.setRootIndex(self.model.index(home_dir))
            self.last_dir = home_dir
            self.current_folder = home_dir

        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.doubleClicked.connect(self.on_double_click)
        self.left_layout.addWidget(self.tree_view)

    def show_my_computer_main(self):
        """Show connected drives in the main tree (My Computer)."""
        try:
            # QFileSystemModel with rootPath set to QDir.rootPath() exposes drives on most platforms
            root_index = self.model.index("")
            self.tree_view.setRootIndex(root_index)
            # Update state so we can restore previous view later
            try:
                self._previous_tree_root = self.last_dir
            except Exception:
                self._previous_tree_root = None
            self.path_label.setText("My Computer")
        except Exception:
            try:
                self.tree_view.setRootIndex(self.model.index(QDir.rootPath()))
                self.path_label.setText("My Computer")
            except Exception:
                pass

    def restore_filesystem_root(self):
        """Restore previous tree root (if any) or home directory."""
        try:
            if getattr(self, '_previous_tree_root', None):
                idx = self.model.index(self._previous_tree_root)
                self.tree_view.setRootIndex(idx)
                self.path_label.setText(self._previous_tree_root)
            else:
                home = PlatformUtils.get_home_directory()
                self.tree_view.setRootIndex(self.model.index(home))
                self.path_label.setText(home)
        except Exception:
            pass

    def setup_view_mode_controls(self):
        """Setup view mode control buttons"""
        controls_layout = QHBoxLayout()

        # View mode buttons group
        self.view_group = QButtonGroup()

        # My Computer button: open a new tab that shows drives
        mycomp_btn = QPushButton("🖥️ My Computer")
        mycomp_btn.setToolTip("Open My Computer in a new tab (shows drives)")
        # Help ensure the button is visible by giving it a minimum width
        mycomp_btn.setMinimumWidth(140)
        def _open_my_computer_tab():
            try:
                # placeholder
                _ = None
            except Exception:
                pass
            try:
                if PlatformUtils.is_windows():
                    self.tab_manager.new_tab("__MY_COMPUTER__")
                else:
                    self.tab_manager.new_tab(QDir.rootPath())
            except Exception:
                # If tab_manager isn't available yet, attempt to create a tab later
                try:
                    self.tab_manager.new_tab(QDir.rootPath())
                except Exception:
                    pass

        mycomp_btn.clicked.connect(_open_my_computer_tab)

        # Add a small label to the left to make the control visually clearer
        try:
            from PyQt5.QtWidgets import QLabel
            lbl = QLabel("Open:")
            lbl.setMinimumWidth(40)
            controls_layout.addWidget(lbl)
        except Exception:
            pass

        controls_layout.addWidget(mycomp_btn)
        controls_layout.addStretch()

        # Insert controls at the top so they remain visible above the tab manager
        try:
            self.center_layout.insertLayout(0, controls_layout)
        except Exception:
            # Fallback to append if insertLayout fails for any reason
            self.center_layout.addLayout(controls_layout)

    def setup_multiple_views(self):
        """Setup tabbed interface for file management"""
        # Replace the simple view stack with tab manager (don't create initial tab yet)
        self.tab_manager = TabManager(parent=self, create_initial_tab=False)
        
        # Set up callback to save tab session and update sort menu on changes
        self.tab_manager.set_tab_changed_callback(self.on_tab_changed)
        
        self.center_layout.addWidget(self.tab_manager)
        
        # Setup background operations manager
        self.active_operations = []
        self.operation_progress_dialogs = []
    
    def connect_tab_signals(self, tab):
        """Connect signals from a tab to main window handlers"""
        if tab:
            icon_container = getattr(tab, 'icon_container', None) if hasattr(tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(tab, 'get_icon_container_safely'):
                icon_container = tab.get_icon_container_safely()
            
            if icon_container:
                try:
                    icon_container.emptySpaceClicked.connect(self.deselect_icons)
                    icon_container.emptySpaceRightClicked.connect(self.empty_space_right_clicked)
                    icon_container.selectionChanged.connect(self.on_selection_changed)
                except AttributeError:
                    # Handle case where icon_container exists but doesn't have expected signals
                    pass
    
    def start_background_operation(self, operation_type, source_paths, destination_path=None):
        """Start a background file operation with progress dialog"""
        operation = AsyncFileOperation(source_paths, destination_path, operation_type)
        self.active_operations.append(operation)
        
        # Create enhanced progress dialog
        operation_name = operation_type.title()
        progress_dialog = EnhancedProgressDialog(operation_name, len(source_paths), self)
        self.operation_progress_dialogs.append(progress_dialog)
        
        # Start operation
        progress_dialog.start_operation(operation)
        progress_dialog.show()
        
        # Clean up when finished
        progress_dialog.finished.connect(lambda: self.cleanup_operation(operation, progress_dialog))
        
        return operation
    
    def cleanup_operation(self, operation, progress_dialog):
        """Clean up completed operation"""
        if operation in self.active_operations:
            self.active_operations.remove(operation)
        if progress_dialog in self.operation_progress_dialogs:
            self.operation_progress_dialogs.remove(progress_dialog)
        
        # Refresh current view
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.refresh_current_view()
    
    def close_current_tab(self):
        """Close the currently active tab"""
        current_index = self.tab_manager.tab_bar.currentIndex()
        if current_index >= 0:
            self.tab_manager.close_tab(current_index)

    def setup_menu_bar(self):
        """Setup enhanced menu system"""
        menu_bar = self.menuBar()
        
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
        # ensure thumbnail view is current if present
        try:
            self.view_stack.setCurrentWidget(self.thumbnail_view_widget)
        except Exception:
            pass

    def setup_file_system_model(self):
        """Initialize the file system model"""
        pass  # Models are set up in individual view setup methods

    def setup_enhanced_menus(self):
        """Setup enhanced menu system (clean, consistent implementation)."""
        menu_bar = self.menuBar()

        # macOS native menu bar support
        if PlatformUtils.is_macos():
            menu_bar.setNativeMenuBar(True)

        main_modifier = PlatformUtils.get_modifier_key()

        # File menu
        file_menu = menu_bar.addMenu("File")
        self.new_tab_action = QAction("New Tab", self)
        self.new_tab_action.setShortcut(f"{main_modifier}+T")
        self.new_tab_action.triggered.connect(lambda: self.tab_manager.new_tab())
        file_menu.addAction(self.new_tab_action)

        self.close_tab_action = QAction("Close Tab", self)
        self.close_tab_action.setShortcut(f"{main_modifier}+W")
        self.close_tab_action.triggered.connect(self.close_current_tab)
        file_menu.addAction(self.close_tab_action)

        file_menu.addSeparator()

        self.network_shares_action = QAction("Network Shares...", self)
        self.network_shares_action.setShortcut(f"{main_modifier}+K")
        self.network_shares_action.triggered.connect(self.open_network_folder_dialog)
        file_menu.addAction(self.network_shares_action)

        file_menu.addSeparator()

        self.new_folder_action = QAction("New Folder", self)
        self.new_folder_action.setShortcut(f"{main_modifier}+Shift+N")
        self.new_folder_action.triggered.connect(self.create_new_folder)
        file_menu.addAction(self.new_folder_action)

        file_menu.addSeparator()

        self.properties_action = QAction("Properties", self)
        self.properties_action.setShortcut("Alt+Return")
        self.properties_action.triggered.connect(self.show_properties_selected_item)
        file_menu.addAction(self.properties_action)

        file_menu.addSeparator()
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(f"{main_modifier}+Q")
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        file_menu.addSeparator()
        self.upload_github_action = QAction("Upload to GitHub Release...", self)
        self.upload_github_action.triggered.connect(self.show_github_upload_dialog)
        file_menu.addAction(self.upload_github_action)

        self.upload_sourceforge_action = QAction("Upload to SourceForge...", self)
        self.upload_sourceforge_action.triggered.connect(self.show_sourceforge_upload_dialog)
        file_menu.addAction(self.upload_sourceforge_action)

        # Edit menu
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

        # View menu
        view_menu = menu_bar.addMenu("View")
        view_mode_menu = view_menu.addMenu("View Mode")
        self.thumbnail_mode_action = QAction("Thumbnail View", self, checkable=True, checked=True)
        self.icon_mode_action = QAction("Icon View", self, checkable=True)
        self.list_mode_action = QAction("List View", self, checkable=True)
        self.detail_mode_action = QAction("Detail View", self, checkable=True)
        self.thumbnail_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.THUMBNAIL_VIEW))
        self.icon_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.ICON_VIEW))
        self.list_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.LIST_VIEW))
        self.detail_mode_action.triggered.connect(lambda: self.set_view_mode(ViewModeManager.DETAIL_VIEW))
        view_mode_menu.addAction(self.thumbnail_mode_action)
        view_mode_menu.addAction(self.icon_mode_action)
        view_mode_menu.addAction(self.list_mode_action)
        view_mode_menu.addAction(self.detail_mode_action)

    # (Removed menu entry for 'Icon View: Use simple icons')

        # Thumbnail size submenu
        thumbnail_menu = view_menu.addMenu("Thumbnail Size")
        self.thumb_24_action = QAction("24px", self, checkable=True)
        self.thumb_32_action = QAction("32px", self, checkable=True)
        self.small_thumb_action = QAction("Small (48px)", self, checkable=True)
        self.medium_thumb_action = QAction("Medium (64px)", self, checkable=True)
        self.large_thumb_action = QAction("Large (96px)", self, checkable=True)
        self.xlarge_thumb_action = QAction("Extra Large (128px)", self, checkable=True)
        # Additional sizes
        self.thumb_80_action = QAction("80px", self, checkable=True)
        self.thumb_160_action = QAction("160px", self, checkable=True)
        self.thumb_192_action = QAction("192px", self, checkable=True)
        self.thumb_224_action = QAction("224px", self, checkable=True)
        self.thumb_256_action = QAction("256px", self, checkable=True)
        self.thumb_384_action = QAction("384px", self, checkable=True)
        self.thumb_512_action = QAction("512px", self, checkable=True)
        # Large photo-style thumbnails
        self.thumb_640_action = QAction("640px", self, checkable=True)
        self.thumb_768_action = QAction("768px", self, checkable=True)

        # Default selection
        self.medium_thumb_action.setChecked(True)

        # Connect size actions
        self.thumb_24_action.triggered.connect(lambda: self.set_thumbnail_size(24))
        self.thumb_32_action.triggered.connect(lambda: self.set_thumbnail_size(32))
        self.small_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(48))
        self.medium_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(64))
        self.large_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(96))
        self.xlarge_thumb_action.triggered.connect(lambda: self.set_thumbnail_size(128))
        self.thumb_80_action.triggered.connect(lambda: self.set_thumbnail_size(80))
        self.thumb_160_action.triggered.connect(lambda: self.set_thumbnail_size(160))
        self.thumb_192_action.triggered.connect(lambda: self.set_thumbnail_size(192))
        self.thumb_224_action.triggered.connect(lambda: self.set_thumbnail_size(224))
        self.thumb_256_action.triggered.connect(lambda: self.set_thumbnail_size(256))
        self.thumb_384_action.triggered.connect(lambda: self.set_thumbnail_size(384))
        self.thumb_512_action.triggered.connect(lambda: self.set_thumbnail_size(512))
        self.thumb_640_action.triggered.connect(lambda: self.set_thumbnail_size(640))
        self.thumb_768_action.triggered.connect(lambda: self.set_thumbnail_size(768))

        # Add size actions to menu
        thumbnail_menu.addAction(self.thumb_24_action)
        thumbnail_menu.addAction(self.thumb_32_action)
        thumbnail_menu.addAction(self.small_thumb_action)
        thumbnail_menu.addAction(self.medium_thumb_action)
        thumbnail_menu.addAction(self.thumb_80_action)
        thumbnail_menu.addAction(self.large_thumb_action)
        thumbnail_menu.addAction(self.xlarge_thumb_action)
        thumbnail_menu.addAction(self.thumb_160_action)
        thumbnail_menu.addAction(self.thumb_192_action)
        thumbnail_menu.addAction(self.thumb_224_action)
        thumbnail_menu.addAction(self.thumb_256_action)
        thumbnail_menu.addAction(self.thumb_384_action)
        thumbnail_menu.addAction(self.thumb_512_action)
        thumbnail_menu.addAction(self.thumb_640_action)
        thumbnail_menu.addAction(self.thumb_768_action)

        # Icon layout submenu
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

        # Sort submenu
        sort_menu = view_menu.addMenu("Sort")
        sort_by_menu = sort_menu.addMenu("Sort By")
        self.sort_by_name_action = QAction("Name", self, checkable=True, checked=True)
        self.sort_by_size_action = QAction("Size", self, checkable=True)
        self.sort_by_date_action = QAction("Date Modified", self, checkable=True)
        self.sort_by_type_action = QAction("Type", self, checkable=True)
        self.sort_by_extension_action = QAction("Extension", self, checkable=True)
        self.sort_by_name_action.triggered.connect(lambda: self.set_sort_by("name"))
        self.sort_by_size_action.triggered.connect(lambda: self.set_sort_by("size"))
        self.sort_by_date_action.triggered.connect(lambda: self.set_sort_by("date"))
        self.sort_by_type_action.triggered.connect(lambda: self.set_sort_by("type"))
        self.sort_by_extension_action.triggered.connect(lambda: self.set_sort_by("extension"))
        sort_by_menu.addAction(self.sort_by_name_action)
        sort_by_menu.addAction(self.sort_by_size_action)
        sort_by_menu.addAction(self.sort_by_date_action)
        sort_by_menu.addAction(self.sort_by_type_action)
        sort_by_menu.addAction(self.sort_by_extension_action)

        # Sort order submenu
        sort_order_menu = sort_menu.addMenu("Sort Order")
        self.sort_ascending_action = QAction("Ascending", self, checkable=True, checked=True)
        self.sort_descending_action = QAction("Descending", self, checkable=True)
        self.sort_ascending_action.triggered.connect(lambda: self.set_sort_order("ascending"))
        self.sort_descending_action.triggered.connect(lambda: self.set_sort_order("descending"))
        sort_order_menu.addAction(self.sort_ascending_action)
        sort_order_menu.addAction(self.sort_descending_action)
        sort_menu.addSeparator()

        # Sort options
        self.directories_first_action = QAction("Directories First", self, checkable=True, checked=True)
        self.case_sensitive_action = QAction("Case Sensitive", self, checkable=True)
        self.group_by_type_action = QAction("Group by Type", self, checkable=True)
        self.natural_sort_action = QAction("Natural Sort (Numbers)", self, checkable=True, checked=True)
        self.directories_first_action.triggered.connect(self.toggle_directories_first)
        self.case_sensitive_action.triggered.connect(self.toggle_case_sensitive)
        self.group_by_type_action.triggered.connect(self.toggle_group_by_type)
        self.natural_sort_action.triggered.connect(self.toggle_natural_sort)
        sort_menu.addAction(self.directories_first_action)
        sort_menu.addAction(self.case_sensitive_action)
        sort_menu.addAction(self.group_by_type_action)
        sort_menu.addAction(self.natural_sort_action)

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
        # Verbose event-filter messages toggle (persisted)
        try:
            self.event_filter_verbose_action = QAction("Verbose Event Filter Messages", self, checkable=True)
            # Initialize checked state from global variable
            try:
                self.event_filter_verbose_action.setChecked(bool(EVENT_FILTER_VERBOSE))
            except Exception:
                pass
            def _toggle_event_filter_verbose(checked):
                try:
                    global EVENT_FILTER_VERBOSE
                    EVENT_FILTER_VERBOSE = bool(checked)
                    settings = QSettings('garysfm', 'garysfm')
                    settings.setValue('event_filter_verbose', bool(checked))
                except Exception:
                    pass
            self.event_filter_verbose_action.toggled.connect(_toggle_event_filter_verbose)
            view_menu.addAction(self.event_filter_verbose_action)
        except Exception:
            pass
        view_menu.addSeparator()
        if not hasattr(self, '_dark_mode_action_added'):
            self.dark_mode_action = QAction("Dark Mode", self, checkable=True)
            self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
            view_menu.addAction(self.dark_mode_action)
            self._dark_mode_action_added = True
        # Theme submenu with regular themes and subdued submenu
        if not hasattr(self, '_theme_menu_added'):
            theme_menu = view_menu.addMenu('Theme')
            self._theme_actions = {}
            
            # First add regular themes
            regular_names = sorted(self.COLOR_THEMES.keys())
            
            # Create actions for regular themes
            for name in regular_names:
                a = QAction(name, self, checkable=True)
                
                theme = self.COLOR_THEMES.get(name, {})
                
                # Create a small swatch icon for the theme using its accent color
                try:
                    accent = theme.get('accent') or theme.get('panel_bg') or '#888888'
                    from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush
                    from PyQt5.QtCore import QRectF
                    sw = QPixmap(16, 16)
                    # Start with transparent background so rounded corners look clean
                    sw.fill(QColor(0, 0, 0, 0))
                    p = QPainter(sw)
                    try:
                        p.setRenderHint(QPainter.Antialiasing)
                        
                        # For regular themes, use rounded rect style
                        rect = QRectF(1.0, 1.0, 14.0, 14.0)
                        fill_col = QColor(accent)
                        # Compute border color based on perceived luminance for contrast
                        try:
                            # QColor.getRgb() returns (r,g,b,a)
                            r, g, b, _ = fill_col.getRgb()
                            # Relative luminance (standard formula)
                            lum = (0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0))
                            if lum > 0.7:
                                # light fill -> soft semi-transparent black border
                                border_col = QColor(0, 0, 0, 120)
                            elif lum < 0.3:
                                # dark fill -> soft semi-transparent white border
                                border_col = QColor(255, 255, 255, 130)
                            else:
                                # mid-tone -> slightly darker version
                                border_col = fill_col.darker(115)
                        except Exception:
                            border_col = QColor('#000000')
                        brush = QBrush(fill_col)
                        pen = QPen(border_col)
                        pen.setWidthF(1.0)
                        p.setBrush(brush)
                        p.setPen(pen)
                        p.drawRoundedRect(rect, 3.0, 3.0)
                    finally:
                        p.end()
                    a.setIcon(QIcon(sw))
                except Exception:
                    pass
                
                # Set up the action trigger for regular themes
                def _set_regular_theme(checked, name=name):
                    try:
                        if checked:
                            # Disable subdued mode and strong mode, set regular theme
                            self.subdued_mode = False
                            self.strong_mode = False
                            try:
                                settings = QSettings('garysfm', 'garysfm')
                                settings.setValue('subdued_mode', False)
                                settings.setValue('strong_mode', False)
                                # Save the regular theme name
                                settings.setValue('color_theme', name)
                            except Exception:
                                pass
                            self.set_color_theme(name)
                    except Exception:
                        pass
                a.triggered.connect(_set_regular_theme)
                theme_menu.addAction(a)
                self._theme_actions[name] = a
            
            # Add separator before submenus
            theme_menu.addSeparator()
            
            # Create subdued themes submenu only if there are subdued themes
            subdued_names = sorted(self.SUBDUED_COLOR_THEMES.keys())
            if subdued_names:
                subdued_menu = theme_menu.addMenu('Subdued Themes')
                
                # Create actions for subdued themes
                for name in subdued_names:
                    a = QAction(name, self, checkable=True)
                    
                    theme = self.SUBDUED_COLOR_THEMES.get(name, {})
                    
                    # Create a small swatch icon for the subdued theme
                    try:
                        accent = theme.get('accent') or theme.get('panel_bg') or '#888888'
                        from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush
                        from PyQt5.QtCore import QRectF
                        sw = QPixmap(16, 16)
                        # Start with transparent background so rounded corners look clean
                        sw.fill(QColor(0, 0, 0, 0))
                        p = QPainter(sw)
                        try:
                            p.setRenderHint(QPainter.Antialiasing)
                            
                            # For subdued themes, use rounded rectangles with subtle styling
                            # Background rounded rectangle
                            bg_rect = QRectF(0, 0, 16, 16)
                            p.setBrush(QBrush(QColor(theme.get('window_bg', '#111111'))))
                            p.setPen(QPen(QColor(0, 0, 0, 0)))  # No border
                            p.drawRoundedRect(bg_rect, 2, 2)
                            
                            # Accent colored rounded rectangle (smaller, more subtle than strong themes)
                            accent_rect = QRectF(3, 3, 10, 10)
                            p.setBrush(QBrush(QColor(accent)))
                            p.drawRoundedRect(accent_rect, 1, 1)
                        finally:
                            p.end()
                        a.setIcon(QIcon(sw))
                    except Exception:
                        pass
                    
                    # Set up the action trigger for subdued themes
                    def _set_subdued_theme(checked, name=name):
                        try:
                            if checked:
                                # Enable subdued mode and set this theme
                                self.subdued_mode = True
                                self.strong_mode = False  # Disable strong mode
                                try:
                                    settings = QSettings('garysfm', 'garysfm')
                                    settings.setValue('subdued_mode', True)
                                    settings.setValue('strong_mode', False)
                                    # Save the subdued theme name
                                    settings.setValue('subdued_theme', name)
                                except Exception:
                                    pass
                                self.color_theme = name
                                self.apply_theme()
                                self.refresh_all_themes()
                        except Exception:
                            pass
                    a.triggered.connect(_set_subdued_theme)
                    subdued_menu.addAction(a)
                    self._theme_actions[name] = a
            
            # Create strong themes submenu
            strong_menu = theme_menu.addMenu('Strong Themes')
            strong_names = sorted(self.STRONG_COLOR_THEMES.keys())
            
            # Create actions for strong themes
            for name in strong_names:
                a = QAction(name, self, checkable=True)
                
                theme = self.STRONG_COLOR_THEMES.get(name, {})
                
                # Create a small swatch icon for the strong theme
                try:
                    accent = theme.get('accent') or theme.get('panel_bg') or '#888888'
                    from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush
                    from PyQt5.QtCore import QRectF
                    sw = QPixmap(16, 16)
                    # Start with transparent background so rounded corners look clean
                    sw.fill(QColor(0, 0, 0, 0))
                    p = QPainter(sw)
                    try:
                        p.setRenderHint(QPainter.Antialiasing)
                        
                        # For strong themes, use rounded rectangle with accent color
                        # Background rounded rectangle
                        bg_rect = QRectF(0, 0, 16, 16)
                        p.setBrush(QBrush(QColor(theme.get('window_bg', '#111111'))))
                        p.setPen(QPen(QColor(0, 0, 0, 0)))  # No border
                        p.drawRoundedRect(bg_rect, 3, 3)
                        
                        # Accent colored rounded rectangle (slightly smaller)
                        accent_rect = QRectF(2, 2, 12, 12)
                        p.setBrush(QBrush(QColor(accent)))
                        p.drawRoundedRect(accent_rect, 2, 2)
                    finally:
                        p.end()
                    a.setIcon(QIcon(sw))
                except Exception:
                    pass
                
                # Set up the action trigger for strong themes
                def _set_strong_theme(checked, name=name):
                    try:
                        if checked:
                            # Enable strong mode and set this theme
                            self.strong_mode = True
                            self.subdued_mode = False  # Disable subdued mode
                            try:
                                settings = QSettings('garysfm', 'garysfm')
                                settings.setValue('strong_mode', True)
                                settings.setValue('subdued_mode', False)
                                # Save the strong theme name
                                settings.setValue('strong_theme', name)
                            except Exception:
                                pass
                            self.color_theme = name
                            self.apply_theme()
                            self.refresh_all_themes()
                    except Exception:
                        pass
                a.triggered.connect(_set_strong_theme)
                strong_menu.addAction(a)
                self._theme_actions[name] = a
                
            self._theme_menu_added = True
            # Ensure currently selected theme is checked
            try:
                sel = getattr(self, 'color_theme', None)
                if sel and sel in self._theme_actions:
                    self._theme_actions[sel].setChecked(True)
            except Exception:
                pass
        # Update menu checkmarks and theme
        self.update_thumbnail_menu_checkmarks()
        self.update_layout_menu_checkmarks()
        self.update_sort_menu_checkmarks()
        self.update_dark_mode_checkmark()
        self.apply_theme()

        # Tools menu
        tools_menu = menu_bar.addMenu("Tools")
        # Windows-only Control Panel action
        try:
            if sys.platform.startswith('win'):
                self.control_panel_action = QAction("Control Panel", self)
                def _open_control_panel():
                    import subprocess
                    try:
                        subprocess.Popen(["control"])
                    except Exception:
                        # fallback to rundll32 if control fails
                        try:
                            subprocess.Popen(["rundll32.exe", "shell32.dll,Control_RunDLL"])
                        except Exception:
                            pass
                self.control_panel_action.triggered.connect(_open_control_panel)
                tools_menu.addSeparator()
                tools_menu.addAction(self.control_panel_action)
        except Exception:
            pass
        self.clipboard_history_menu_action = QAction("Clipboard History...", self)
        self.clipboard_history_menu_action.triggered.connect(self.show_clipboard_history)
        tools_menu.addAction(self.clipboard_history_menu_action)
        tools_menu.addSeparator()
        archive_menu = tools_menu.addMenu("Archive Tools")
        self.create_archive_action = QAction("Create Archive...", self)
        self.create_archive_action.triggered.connect(lambda: self.create_archive_from_selection())
        archive_menu.addAction(self.create_archive_action)
        self.extract_archive_action = QAction("Extract Archive...", self)
        self.extract_archive_action.triggered.connect(lambda: self.extract_archive_from_selection())
        archive_menu.addAction(self.extract_archive_action)
        self.browse_archive_action = QAction("Browse Archive...", self)
        self.browse_archive_action.triggered.connect(lambda: self.browse_archive_from_selection())
        archive_menu.addAction(self.browse_archive_action)
        tools_menu.addSeparator()

        # Enhanced search submenu
        search_menu = tools_menu.addMenu("Search")
        self.search_files_action = QAction("Search Files && Folders...", self)
        self.search_files_action.setShortcut("Ctrl+F")
        self.search_files_action.triggered.connect(self.focus_search)
        search_menu.addAction(self.search_files_action)
        self.search_content_action = QAction("Search File Contents...", self)
        self.search_content_action.setShortcut("Ctrl+Shift+F")
        self.search_content_action.triggered.connect(self.focus_content_search)
        search_menu.addAction(self.search_content_action)
        search_menu.addSeparator()
        self.find_duplicates_action = QAction("Find Duplicate Files...", self)
        self.find_duplicates_action.triggered.connect(self.show_duplicate_finder)
        search_menu.addAction(self.find_duplicates_action)
        self.find_large_files_action = QAction("Find Large Files...", self)
        self.find_large_files_action.triggered.connect(self.show_large_file_finder)
        search_menu.addAction(self.find_large_files_action)

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
        # Recursive precache tool: cache all missing thumbnails in a directory tree
        self.recursive_precache_action = QAction("Recursive Precache Thumbnails...", self)
        def _run_recursive_precache():
            try:
                print('[RECURSIVE-PRECACHE] _run_recursive_precache started')
                from PyQt5.QtWidgets import QFileDialog, QInputDialog, QMessageBox
                # Ask user for directory
                dlg = QFileDialog(self, 'Select directory to precache')
                dlg.setFileMode(QFileDialog.Directory)
                dlg.setOption(QFileDialog.ShowDirsOnly, True)
                if dlg.exec_() != QFileDialog.Accepted:
                    print('[RECURSIVE-PRECACHE] Directory selection canceled or dialog closed')
                    return
                selected = dlg.selectedFiles()
                if not selected:
                    print('[RECURSIVE-PRECACHE] No directory selected')
                    return
                directory = selected[0]
                print(f'[RECURSIVE-PRECACHE] Selected directory: {directory}')
                # Ask for sizes: present a checkbox dialog listing all sizes the app supports
                from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QCheckBox, QLabel

                class SizeSelectionDialog(QDialog):
                    def __init__(self, parent, available_sizes, current_size):
                        super().__init__(parent)
                        self.setWindowTitle('Select thumbnail sizes')
                        self.selected = []
                        self.available_sizes = available_sizes
                        layout = QVBoxLayout()
                        label = QLabel('Choose which thumbnail sizes to generate:')
                        layout.addWidget(label)

                        scroll = QScrollArea(self)
                        scroll.setWidgetResizable(True)
                        content = QWidget()
                        content_layout = QVBoxLayout()
                        content.setLayout(content_layout)

                        self.checkboxes = []
                        for s in available_sizes:
                            cb = QCheckBox(f"{s}px")
                            if s == current_size:
                                cb.setChecked(True)
                            content_layout.addWidget(cb)
                            self.checkboxes.append((s, cb))

                        scroll.setWidget(content)
                        layout.addWidget(scroll)

                        btn_layout = QHBoxLayout()
                        select_all = QPushButton('Select All')
                        clear_all = QPushButton('Clear All')
                        btn_layout.addWidget(select_all)
                        btn_layout.addWidget(clear_all)
                        layout.addLayout(btn_layout)

                        ok_cancel = QHBoxLayout()
                        ok_btn = QPushButton('OK')
                        cancel_btn = QPushButton('Cancel')
                        ok_cancel.addWidget(ok_btn)
                        ok_cancel.addWidget(cancel_btn)
                        layout.addLayout(ok_cancel)

                        select_all.clicked.connect(self._select_all)
                        clear_all.clicked.connect(self._clear_all)
                        ok_btn.clicked.connect(self.accept)
                        cancel_btn.clicked.connect(self.reject)

                        self.setLayout(layout)

                    def _select_all(self):
                        for _, cb in self.checkboxes:
                            cb.setChecked(True)

                    def _clear_all(self):
                        for _, cb in self.checkboxes:
                            cb.setChecked(False)

                    def get_selected(self):
                        return [s for s, cb in self.checkboxes if cb.isChecked()]

                # Build list of available sizes from the app (read thumbnail QAction attributes)
                available_sizes = []
                try:
                    # Common attribute name pattern set when the menu was created
                    candidate_attrs = [
                        'thumb_24_action','thumb_32_action','small_thumb_action','medium_thumb_action',
                        'large_thumb_action','xlarge_thumb_action','thumb_80_action','thumb_160_action',
                        'thumb_192_action','thumb_224_action','thumb_256_action','thumb_384_action',
                        'thumb_512_action','thumb_640_action','thumb_768_action'
                    ]
                    seen = set()
                    for attr in candidate_attrs:
                        act = getattr(self, attr, None)
                        if act is None:
                            continue
                        # Try to parse numeric size from the action text
                        text = act.text() if hasattr(act, 'text') else None
                        if text:
                            import re
                            m = re.search(r'(\d{2,4})', text)
                            if m:
                                val = int(m.group(1))
                                if val not in seen:
                                    available_sizes.append(val)
                                    seen.add(val)
                    # Fallback to a sensible default set if nothing found
                    if not available_sizes:
                        available_sizes = [24, 32, 48, 64, 80, 96, 128, 160, 192, 224, 256, 384, 512, 640, 768]
                except Exception:
                    available_sizes = [24, 32, 48, 64, 80, 96, 128, 160, 192, 224, 256, 384, 512, 640, 768]
                # Keep order predictable
                available_sizes = sorted(available_sizes)
                current = getattr(self, 'thumbnail_size', 64)
                dlg = SizeSelectionDialog(self, available_sizes, current)
                print('[RECURSIVE-PRECACHE] Showing size selection dialog')
                if dlg.exec_() != QDialog.Accepted:
                    print('[RECURSIVE-PRECACHE] Size selection canceled')
                    return
                sizes = dlg.get_selected()
                print(f'[RECURSIVE-PRECACHE] Sizes selected: {sizes}')
                if not sizes:
                    QMessageBox.information(self, 'Precache', 'No sizes selected')
                    return
                # Walk tree and collect files to precache
                import os
                import glob
                files = []
                for root, dirs, filenames in os.walk(directory):
                    for fn in filenames:
                        files.append(os.path.join(root, fn))
                # Deduplicate files while preserving order (some file trees can yield duplicates)
                seen_files = set()
                unique_files = []
                for f in files:
                    if f not in seen_files:
                        seen_files.add(f)
                        unique_files.append(f)
                files = unique_files
                if not files:
                    QMessageBox.information(self, 'Precache', 'No files found under selected directory')
                    return

                # Worker: run caching in a background thread and show a progress dialog
                from PyQt5.QtCore import QThread, pyqtSignal, QObject

                class RecursivePrecacheWorker(QObject):
                    finished = pyqtSignal()
                    progress = pyqtSignal(int, int)  # completed, total
                    def __init__(self, files, thumbnail_cache, sizes, parent):
                        super().__init__()
                        self.files = files
                        self.thumbnail_cache = thumbnail_cache
                        self.sizes = list(sizes)
                        self.parent = parent
                        self._stop = False

                    def run(self):
                        total = len(self.files) * max(1, len(self.sizes))
                        completed = 0
                        # Track directories already processed for a given size to avoid duplicate work
                        processed_dirs = set()  # set of (dirpath, size)

                        print(f"[RECURSIVE-PRECACHE-WORKER] starting run: {len(self.files)} files, sizes={self.sizes}, total_steps={total}")

                        for idx, fp in enumerate(self.files):
                            if getattr(self, '_stop', False):
                                print('[RECURSIVE-PRECACHE-WORKER] stop flag set, breaking')
                                break
                            try:
                                ext = os.path.splitext(fp)[1].lower()
                                dirpath = os.path.dirname(fp) or '.'
                                for s in self.sizes:
                                    if getattr(self, '_stop', False):
                                        break
                                    try:
                                        # If this exact file+size is already cached, skip
                                        try:
                                            cached = self.thumbnail_cache.get(fp, s)
                                            if cached is not None:
                                                completed += 1
                                                print(f"[RECURSIVE-PRECACHE-WORKER] cached skip: {fp} size={s} (completed {completed}/{total})")
                                                self.progress.emit(completed, total)
                                                continue
                                        except Exception as e:
                                            print(f"[RECURSIVE-PRECACHE-WORKER] cache lookup error for {fp} size={s}: {e}")

                                        # Only run the expensive per-directory precache once per directory+size
                                        key = (dirpath, s)
                                        if key in processed_dirs:
                                            completed += 1
                                            print(f"[RECURSIVE-PRECACHE-WORKER] dir already processed: {dirpath} size={s} (completed {completed}/{total})")
                                            self.progress.emit(completed, total)
                                            continue

                                        print(f"[RECURSIVE-PRECACHE-WORKER] processing dir={dirpath} size={s} for file {fp}")
                                        # Choose helper based on extension
                                        try:
                                            if ext in ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'):
                                                precache_video_thumbnails_in_directory(dirpath, self.thumbnail_cache, size=s, parent=self.parent, show_progress=False)
                                            else:
                                                precache_text_pdf_thumbnails_in_directory(dirpath, self.thumbnail_cache, size=s, parent=self.parent, show_progress=False)
                                        except Exception as e:
                                            print(f"[RECURSIVE-PRECACHE-WORKER] helper error for dir={dirpath} size={s}: {e}")

                                        # Mark directory+size as processed to avoid repeating work
                                        processed_dirs.add(key)

                                        # After helper runs, increment progress (the helper may have cached multiple files)
                                        completed += 1
                                        print(f"[RECURSIVE-PRECACHE-WORKER] emit progress {completed}/{total}")
                                        self.progress.emit(completed, total)
                                    except Exception as e:
                                        print(f"[RECURSIVE-PRECACHE-WORKER] inner loop exception for {fp} size={s}: {e}")
                                        pass
                            except Exception as e:
                                print(f"[RECURSIVE-PRECACHE-WORKER] outer loop exception for {fp}: {e}")
                                # Continue on errors for directories/files
                                pass
                        print('[RECURSIVE-PRECACHE-WORKER] run finished, emitting finished')
                        self.finished.emit()

                print('[RECURSIVE-PRECACHE] Preparing progress dialog and worker')
                # Set up dialog and thread
                from PyQt5.QtWidgets import QProgressDialog
                from PyQt5.QtCore import Qt
                # Compute a more accurate total: unique directories x sizes
                try:
                    unique_dirs = {os.path.dirname(fp) or '.' for fp in files}
                    total_steps = max(1, len(unique_dirs) * max(1, len(sizes)))
                except Exception:
                    total_steps = max(1, len(files) * max(1, len(sizes)))

                # Create a non-cancelable progress dialog for the recursive precache operation
                progress_dialog = QProgressDialog('Recursively caching thumbnails...', '', 0, total_steps, self)
                try:
                    progress_dialog.setCancelButton(None)
                except Exception:
                    try:
                        progress_dialog.setCancelButtonText('')
                    except Exception:
                        pass
                progress_dialog.setWindowTitle('Recursive precache')
                progress_dialog.setMinimumDuration(200)
                # Make dialog window-modal so it reliably appears above the main window
                try:
                    progress_dialog.setWindowModality(Qt.WindowModal)
                except Exception:
                    try:
                        progress_dialog.setWindowModality(1)
                    except Exception:
                        pass

                worker_thread = QThread()
                worker = RecursivePrecacheWorker(files, getattr(self, 'thumbnail_cache', None), sizes, self)
                worker.moveToThread(worker_thread)
                worker.finished.connect(worker_thread.quit)
                worker.finished.connect(progress_dialog.close)
                # Ensure worker is deleted on the main thread when finished
                worker.finished.connect(worker.deleteLater)
                worker_thread.started.connect(worker.run)

                # Keep the thread/worker alive by parenting them to the dialog and storing strong refs
                try:
                    worker_thread.setParent(progress_dialog)
                except Exception:
                    pass
                progress_dialog._worker_thread = worker_thread
                progress_dialog._worker = worker

                # Define cleanup to clear stored references when thread finishes
                def _cleanup_worker_refs():
                    try:
                        if hasattr(progress_dialog, '_worker_thread'):
                            try:
                                progress_dialog._worker_thread.deleteLater()
                            except Exception:
                                pass
                            try:
                                delattr(progress_dialog, '_worker_thread')
                            except Exception:
                                try:
                                    del progress_dialog._worker_thread
                                except Exception:
                                    pass
                        if hasattr(progress_dialog, '_worker'):
                            try:
                                progress_dialog._worker.deleteLater()
                            except Exception:
                                pass
                            try:
                                delattr(progress_dialog, '_worker')
                            except Exception:
                                try:
                                    del progress_dialog._worker
                                except Exception:
                                    pass
                    except Exception:
                        pass
                try:
                    worker_thread.finished.connect(_cleanup_worker_refs)
                except Exception:
                    pass

                # Make progress dialog cancelable and wire cancellation to the worker's stop flag
                try:
                    progress_dialog.setCancelButtonText('Cancel')
                    # Connect dialog cancel to cooperative stop
                    def _on_cancel():
                        try:
                            print('[RECURSIVE-PRECACHE] User requested cancel')
                            setattr(worker, '_stop', True)
                        except Exception:
                            pass
                    try:
                        progress_dialog.canceled.connect(_on_cancel)
                    except Exception:
                        try:
                            progress_dialog.canceled.connect(lambda: setattr(worker, '_stop', True))
                        except Exception:
                            pass
                except Exception:
                    pass

                # ETA tracking and progress handler (runs on main thread)
                from PyQt5.QtWidgets import QApplication
                import time as _time
                def _format_eta(seconds):
                    if seconds <= 0:
                        return '0s'
                    m, s = divmod(int(seconds), 60)
                    h, m = divmod(m, 60)
                    if h:
                        return f"{h}h {m}m"
                    if m:
                        return f"{m}m {s}s"
                    return f"{s}s"

                def _on_progress(completed, total):
                    try:
                        # Initialize start time on first progress
                        if not hasattr(progress_dialog, '_start_time'):
                            progress_dialog._start_time = _time.time()
                        elapsed = _time.time() - getattr(progress_dialog, '_start_time', _time.time())
                        if completed > 0:
                            rate = elapsed / completed
                            remaining = max(0, total - completed)
                            eta = remaining * rate
                        else:
                            eta = 0
                        eta_str = _format_eta(eta)
                        # Update dialog value and label to include ETA
                        try:
                            progress_dialog.setMaximum(total)
                            progress_dialog.setValue(completed)
                            progress_dialog.setLabelText(f"Recursively caching thumbnails... ({completed}/{total}) ETA: {eta_str}")
                        except Exception:
                            pass
                        try:
                            QApplication.processEvents()
                        except Exception:
                            pass
                    except Exception:
                        pass

                worker.progress.connect(_on_progress)

                # Show the progress dialog and start worker
                try:
                    progress_dialog.setValue(0)
                    print('[RECURSIVE-PRECACHE] Showing progress dialog')
                    progress_dialog.show()
                except Exception as e:
                    print(f'[RECURSIVE-PRECACHE] Failed to show progress dialog: {e}')
                    pass

                # Cancellation via dialog button removed to make this a non-interruptible progress dialog.
                # Worker cooperative stop is still available via code changes if desired.
                worker_thread.finished.connect(worker_thread.deleteLater)
                worker_thread.start()
                print('[RECURSIVE-PRECACHE] Worker thread started')
                # Run modal exec to keep UI responsive until finished
                try:
                    progress_dialog.exec_()
                except Exception:
                    # Fallback: if exec_ fails, just show non-modal dialog
                    try:
                        progress_dialog.show()
                    except Exception:
                        pass
            except Exception as e:
                import traceback
                print(f"[TOOLS-PRECACHE-ERROR] {e}\n{traceback.format_exc()}")

        self.recursive_precache_action.triggered.connect(_run_recursive_precache)
        tools_menu.addAction(self.recursive_precache_action)

        # Remove thumbnails tool: delete cached thumbnails for selected sizes from this app's cache dir
        self.remove_thumbnails_action = QAction("Remove Thumbnails...", self)
        def _run_remove_thumbnails():
            try:
                logging.debug('[REMOVE-THUMBNAILS] _run_remove_thumbnails started')
                from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget, QCheckBox, QLabel
                from PyQt5.QtCore import Qt
                from PyQt5.QtWidgets import QProgressDialog

                # Use the application's thumbnail cache directory (do not prompt for directory)
                tc = getattr(self, 'thumbnail_cache', None)
                if not tc:
                    QMessageBox.information(self, 'Remove Thumbnails', 'No thumbnail cache is configured for this application.')
                    return
                directory = getattr(tc, 'cache_dir', None)
                if not directory:
                    QMessageBox.information(self, 'Remove Thumbnails', 'Thumbnail cache directory is not set for this application.')
                    return

                # Size selection dialog with dry-run option
                class SizeSelectionDialog(QDialog):
                    def __init__(self, parent, available_sizes, current_size):
                        super().__init__(parent)
                        self.setWindowTitle('Select thumbnail sizes')
                        self.available_sizes = available_sizes
                        layout = QVBoxLayout()
                        label = QLabel('Choose which thumbnail sizes to remove:')
                        layout.addWidget(label)

                        scroll = QScrollArea(self)
                        scroll.setWidgetResizable(True)
                        content = QWidget()
                        content_layout = QVBoxLayout()
                        content.setLayout(content_layout)

                        self.checkboxes = []
                        for s in available_sizes:
                            cb = QCheckBox(f"{s}px")
                            if s == current_size:
                                cb.setChecked(True)
                            content_layout.addWidget(cb)
                            self.checkboxes.append((s, cb))

                        scroll.setWidget(content)
                        layout.addWidget(scroll)

                        btn_layout = QHBoxLayout()
                        select_all = QPushButton('Select All')
                        clear_all = QPushButton('Clear All')
                        btn_layout.addWidget(select_all)
                        btn_layout.addWidget(clear_all)
                        layout.addLayout(btn_layout)

                        # Dry-run option: do not actually delete files
                        self.dry_run_cb = QCheckBox('Dry run (do not delete files)')
                        layout.addWidget(self.dry_run_cb)

                        ok_cancel = QHBoxLayout()
                        ok_btn = QPushButton('OK')
                        cancel_btn = QPushButton('Cancel')
                        ok_cancel.addWidget(ok_btn)
                        ok_cancel.addWidget(cancel_btn)
                        layout.addLayout(ok_cancel)

                        select_all.clicked.connect(self._select_all)
                        clear_all.clicked.connect(self._clear_all)
                        ok_btn.clicked.connect(self.accept)
                        cancel_btn.clicked.connect(self.reject)

                        self.setLayout(layout)

                    def _select_all(self):
                        for _, cb in self.checkboxes:
                            cb.setChecked(True)

                    def _clear_all(self):
                        for _, cb in self.checkboxes:
                            cb.setChecked(False)

                    def get_selected(self):
                        return [s for s, cb in self.checkboxes if cb.isChecked()]

                    def is_dry_run(self):
                        return bool(self.dry_run_cb.isChecked())

                # Build list of available sizes
                try:
                    candidate_attrs = [
                        'thumb_24_action','thumb_32_action','small_thumb_action','medium_thumb_action',
                        'large_thumb_action','xlarge_thumb_action','thumb_80_action','thumb_160_action',
                        'thumb_192_action','thumb_224_action','thumb_256_action','thumb_384_action',
                        'thumb_512_action','thumb_640_action','thumb_768_action'
                    ]
                    available_sizes = []
                    seen = set()
                    for attr in candidate_attrs:
                        act = getattr(self, attr, None)
                        if act is None:
                            continue
                        text = act.text() if hasattr(act, 'text') else None
                        if text:
                            import re
                            m = re.search(r'(\d{2,4})', text)
                            if m:
                                val = int(m.group(1))
                                if val not in seen:
                                    available_sizes.append(val)
                                    seen.add(val)
                    if not available_sizes:
                        available_sizes = [24,32,48,64,80,96,128,160,192,224,256,384,512,640,768]
                except Exception:
                    available_sizes = [24,32,48,64,80,96,128,160,192,224,256,384,512,640,768]

                available_sizes = sorted(available_sizes)
                current = getattr(self, 'thumbnail_size', 64)
                sdlg = SizeSelectionDialog(self, available_sizes, current)
                if sdlg.exec_() != QDialog.Accepted:
                    logging.debug('[REMOVE-THUMBNAILS] Size selection canceled')
                    return
                sizes = sdlg.get_selected()
                dry_run = sdlg.is_dry_run()
                logging.debug('[REMOVE-THUMBNAILS] Sizes selected: %s dry_run=%s', sizes, dry_run)
                if not sizes:
                    QMessageBox.information(self, 'Remove Thumbnails', 'No sizes selected')
                    return

                # Confirm with the user
                if QMessageBox.question(self, 'Confirm Remove Thumbnails', f"Remove thumbnails for sizes {sizes} in cache {directory}? This cannot be undone.", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    logging.debug('[REMOVE-THUMBNAILS] User canceled remove')
                    return

                # Gather target files in cache dir matching selected sizes
                import os
                removed = 0
                errors = 0
                targets = []  # list of (fpath, fn, size)
                try:
                    for fn in os.listdir(directory):
                        fpath = os.path.join(directory, fn)
                        if not os.path.isfile(fpath):
                            continue
                        for s in sizes:
                            suffix_thumb = f"_{s}.thumb"
                            suffix_png = f"_{s}.png"
                            if fn.endswith(suffix_thumb) or fn.endswith(suffix_png):
                                targets.append((fpath, fn, s))
                except Exception:
                    logging.exception('Error listing thumbnail cache directory %s', directory)

                # Progress dialog for deletion
                total = len(targets)
                progress = QProgressDialog('Removing thumbnails...', 'Cancel', 0, max(1, total), self)
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(200)
                progress.setValue(0)

                for idx, (fpath, fn, s) in enumerate(targets, start=1):
                    if progress.wasCanceled():
                        logging.info('Thumbnail removal canceled by user at %d/%d', idx - 1, total)
                        break
                    try:
                        if not dry_run:
                            try:
                                os.remove(fpath)
                                removed += 1
                                # Also remove metadata and memory cache entries if present
                                cache_key = fn.rsplit('.', 1)[0]
                                try:
                                    with tc._lock:
                                        if cache_key in tc.metadata:
                                            del tc.metadata[cache_key]
                                        if cache_key in tc.memory_cache:
                                            del tc.memory_cache[cache_key]
                                except Exception:
                                    pass
                            except Exception:
                                errors += 1
                        else:
                            # Dry run - count but do not delete
                            removed += 1
                    except Exception:
                        errors += 1
                    progress.setValue(idx)
                progress.close()

                logging.info('Removed %d thumbnail files. Errors: %d', removed, errors)
                QMessageBox.information(self, 'Remove Thumbnails', f'Removed {removed} thumbnail files. Errors: {errors}')
            except Exception as e:
                import traceback
                try:
                    QMessageBox.critical(self, 'Error', f'Error removing thumbnails: {e}\n{traceback.format_exc()}')
                except Exception:
                    logging.error('[REMOVE-THUMBNAILS-ERROR] %s\n%s', e, traceback.format_exc())

        self.remove_thumbnails_action.triggered.connect(_run_remove_thumbnails)
        tools_menu.addAction(self.remove_thumbnails_action)

    def setup_enhanced_keyboard_shortcuts(self):
        """Setup enhanced keyboard shortcuts with platform-specific modifiers"""
        main_modifier = PlatformUtils.get_modifier_key()
        alt_modifier = PlatformUtils.get_alt_modifier_key()
        nav_modifier = PlatformUtils.get_navigation_modifier()

        # Platform-specific shortcuts (macOS uses Cmd, others use Ctrl)
        if PlatformUtils.is_macos():
            QShortcut(QKeySequence("Cmd+W"), self, self.close)
            QShortcut(QKeySequence("Cmd+Q"), self, self.close)
            QShortcut(QKeySequence("Cmd+,"), self, self.show_preferences)
            QShortcut(QKeySequence("Cmd+Shift+."), self, self.toggle_show_hidden_files)
            QShortcut(QKeySequence("Cmd+T"), self, self.open_new_tab)
            QShortcut(QKeySequence("Cmd+Delete"), self, self.move_to_trash)
        else:
            QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
            if PlatformUtils.is_windows():
                QShortcut(QKeySequence("Alt+F4"), self, self.close)
            QShortcut(QKeySequence("Ctrl+H"), self, self.toggle_show_hidden_files)
            QShortcut(QKeySequence("Ctrl+T"), self, self.open_new_tab)
            QShortcut(QKeySequence("Shift+Delete"), self, self.move_to_trash)

        # Cross-platform shortcuts
        QShortcut(QKeySequence("F11"), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(f"{main_modifier}+Plus"), self, self.increase_thumbnail_size)
        QShortcut(QKeySequence(f"{main_modifier}+Minus"), self, self.decrease_thumbnail_size)
        QShortcut(QKeySequence(f"{main_modifier}+0"), self, lambda: self.set_thumbnail_size(64))

        # Additional cross-platform shortcuts
        QShortcut(QKeySequence(f"{main_modifier}+L"), self, self.focus_location_bar)
        QShortcut(QKeySequence(f"{main_modifier}+D"), self, self.go_to_desktop)
        QShortcut(QKeySequence(f"{main_modifier}+Shift+D"), self, self.go_to_downloads)
        QShortcut(QKeySequence(f"{main_modifier}+Shift+H"), self, self.go_to_home)

    # Enhanced Methods for New Features

    def set_view_mode(self, mode):
        """Switch between different view modes and persist it"""
        self.view_mode_manager.set_mode(mode)
        self.save_view_mode(mode)

        # Update toolbar buttons
        # toolbar/button check for thumbnail view
        try:
            self.thumbnail_view_action.setChecked(mode == ViewModeManager.THUMBNAIL_VIEW)
        except AttributeError:
            pass
        try:
            self.icon_view_action.setChecked(mode == ViewModeManager.ICON_VIEW)
        except AttributeError:
            pass
        try:
            self.list_view_action.setChecked(mode == ViewModeManager.LIST_VIEW)
        except AttributeError:
            pass
        try:
            self.detail_view_action.setChecked(mode == ViewModeManager.DETAIL_VIEW)
        except AttributeError:
            pass

        # Update menu items
        try:
            self.thumbnail_mode_action.setChecked(mode == ViewModeManager.THUMBNAIL_VIEW)
        except AttributeError:
            pass
        try:
            self.icon_mode_action.setChecked(mode == ViewModeManager.ICON_VIEW)
        except AttributeError:
            pass
        try:
            self.list_mode_action.setChecked(mode == ViewModeManager.LIST_VIEW)
        except AttributeError:
            pass
        try:
            self.detail_mode_action.setChecked(mode == ViewModeManager.DETAIL_VIEW)
        except AttributeError:
            pass

        # Switch the actual view for current tab
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            if mode == ViewModeManager.THUMBNAIL_VIEW:
                # Mark main window state
                try:
                    if hasattr(self, 'view_mode_manager'):
                        self.icon_view_active = False
                except Exception:
                    pass
                # Switch every tab's visible widget to the thumbnail view widget
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        if hasattr(tab, 'view_stack') and hasattr(tab, 'thumbnail_view_widget') and tab.view_stack and tab.thumbnail_view_widget:
                            tab.view_stack.setCurrentWidget(tab.thumbnail_view_widget)
                        # Clear per-tab icon flag where present
                        try:
                            setattr(tab, 'icon_view_active', False)
                        except Exception:
                            pass
                    except Exception:
                        pass
                # Run thumbnail refresh logic for all tabs
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        tab.refresh_thumbnail_view()
                    except Exception:
                        pass
                # Also ensure current_tab flag
                try:
                    current_tab.icon_view_active = False
                except Exception:
                    pass
                # Auto-refresh removed: do not schedule a delayed refresh 1 second after switching to thumbnail view
            elif mode == ViewModeManager.ICON_VIEW:
                # Mark main window state
                try:
                    if hasattr(self, 'view_mode_manager'):
                        self.icon_view_active = True
                except Exception:
                    pass
                # Icon view uses the same widget as thumbnail view; switch every tab to that widget and mark icon mode per-tab
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        if hasattr(tab, 'view_stack') and hasattr(tab, 'thumbnail_view_widget') and tab.view_stack and tab.thumbnail_view_widget:
                            tab.view_stack.setCurrentWidget(tab.thumbnail_view_widget)
                        # Mark per-tab icon flag where supported
                        try:
                            setattr(tab, 'icon_view_active', True)
                        except Exception:
                            pass
                    except Exception:
                        pass
                # Refresh all tabs immediately
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        tab.refresh_current_view()
                    except Exception:
                        pass
                try:
                    current_tab.icon_view_active = True
                except Exception:
                    pass
                # Auto-refresh removed: do not schedule a delayed refresh 1 second after switching to icon view
            elif mode == ViewModeManager.LIST_VIEW:
                try:
                    if hasattr(self, 'view_mode_manager'):
                        self.icon_view_active = False
                except Exception:
                    pass
                # Set list view widget and refresh it for all tabs
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        if hasattr(tab, 'view_stack') and hasattr(tab, 'list_view') and tab.view_stack and tab.list_view:
                            tab.view_stack.setCurrentWidget(tab.list_view)
                    except Exception:
                        pass
                # Refresh list view for all tabs to keep them in sync
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        getattr(tab, 'refresh_list_view', lambda: None)()
                    except Exception:
                        pass
            elif mode == ViewModeManager.DETAIL_VIEW:
                try:
                    if hasattr(self, 'view_mode_manager'):
                        self.icon_view_active = False
                except Exception:
                    pass
                # Set detail view widget and refresh it for all tabs
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        if hasattr(tab, 'view_stack') and hasattr(tab, 'detail_view') and tab.view_stack and tab.detail_view:
                            tab.view_stack.setCurrentWidget(tab.detail_view)
                        # Set detail view header text color to green for this tab
                        try:
                            # Horizontal header (column titles)
                            header = getattr(tab.detail_view, 'horizontalHeader', None)
                            if callable(header):
                                hdr = header()
                                try:
                                    hdr.setStyleSheet('QHeaderView::section { color: green; }')
                                except Exception:
                                    pass
                            else:
                                # detail_view may expose header directly
                                try:
                                    hdr = getattr(tab.detail_view, 'horizontalHeader')
                                    hdr.setStyleSheet('QHeaderView::section { color: green; }')
                                except Exception:
                                    pass

                            # Vertical header (line numbers)
                            vheader = getattr(tab.detail_view, 'verticalHeader', None)
                            if callable(vheader):
                                vh = vheader()
                                try:
                                    vh.setStyleSheet('QHeaderView::section { color: green; }')
                                except Exception:
                                    pass
                            else:
                                try:
                                    vh = getattr(tab.detail_view, 'verticalHeader')
                                    vh.setStyleSheet('QHeaderView::section { color: green; }')
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        pass
                # Refresh detail view for all tabs (not just current) to keep them in sync
                for tab in getattr(self.tab_manager, 'tabs', []):
                    try:
                        getattr(tab, 'refresh_detail_view', lambda: None)()
                    except Exception:
                        pass

    # Cross-platform navigation methods
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
        if hasattr(self, 'update_thumbnail_view'):
            self.update_thumbnail_view(folder_path)
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
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        try:
            PlatformUtils.reveal_in_file_manager(file_path)
            self.statusBar().showMessage(f"Revealed {os.path.basename(file_path)} in file manager", 2000)
        except Exception as e:
            self.show_error_message("Error", f"Cannot reveal file in file manager: {str(e)}")
            current_tab.navigate_to_path(current_tab.current_folder)
        
        # Save the view mode setting
        self.save_last_dir(current_tab.current_folder)
    
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
            self.update_thumbnail_view(file_path)
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
            # Navigate to directory in the current tab
            current_tab = self.tab_manager.get_current_tab()
            if current_tab:
                current_tab.navigate_to_path(file_path)
        else:
            self.open_file(file_path)
    
    def perform_search(self, search_text, filter_options):
        """Perform search with filters"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        if not search_text.strip() and filter_options['type'] == 'All':
            # If no search term and no filters, refresh current tab
            current_tab.navigate_to_path(current_tab.current_folder)
            return
        
        self.current_search_results = []
        search_folder = current_tab.current_folder
        
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
            mod_date = datetime.fromtimestamp(mod_time)
            now = datetime.now()
            
            if date_filter == 'Today':
                return mod_date.date() == now.date()
            elif date_filter == 'This Week':
                week_start = now - timedelta(days=now.weekday())
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
                
                # Determine if main window is in icon-only mode and avoid passing thumbnail cache when in that mode
                use_icon_only = bool(hasattr(self, 'view_mode_manager') and self.view_mode_manager.get_mode() == ViewModeManager.ICON_VIEW)
                in_icon_view = bool(use_icon_only)
                if not in_icon_view and hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                    icon_widget = IconWidget(file_name, file_path, is_dir, self.thumbnail_size, self.thumbnail_cache, use_icon_only)
                else:
                    icon_widget = IconWidget(file_name, file_path, is_dir, self.thumbnail_size, None, use_icon_only)
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

    def handle_advanced_search_results(self, query, filters):
        """Handle search results from the advanced search widget"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
        
        # Get current directory
        current_dir = current_tab.current_folder
        
        # Start async search using the advanced search engine
        def search_callback(callback_type, data):
            if callback_type == 'complete':
                # Update UI with search results
                self.current_search_results = [item['path'] for item in data['results']]
                self.display_search_results()
                self.status_bar.showMessage(f"Found {len(data['results'])} results")
            elif callback_type == 'error':
                self.status_bar.showMessage(f"Search error: {data['message']}")
        
        # Start the search
        future = self.search_engine.search_files_async(current_dir, query, filters, search_callback)
        
    def find_files_with_advanced_criteria(self, directory, criteria):
        """Enhanced file finding with multiple criteria"""
        results = []
        
        try:
            for root, dirs, files in os.walk(directory):
                # Check directories if requested
                if criteria.get('include_directories', False):
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        if self.matches_advanced_criteria(dir_path, dir_name, criteria, is_dir=True):
                            results.append(dir_path)
                
                # Check files
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    if self.matches_advanced_criteria(file_path, file_name, criteria, is_dir=False):
                        results.append(file_path)
                        
        except Exception as e:
            print(f"Error in advanced file search: {e}")
            
        return results
    
    def matches_advanced_criteria(self, file_path, file_name, criteria, is_dir=False):
        """Check if file matches advanced search criteria"""
        try:
            # Get file info
            stat_info = os.stat(file_path)
            file_size = stat_info.st_size
            file_mtime = stat_info.st_mtime
            file_ext = os.path.splitext(file_name)[1].lower()
            
            # Name pattern matching
            name_pattern = criteria.get('name_pattern', '')
            if name_pattern:
                import fnmatch
                if not fnmatch.fnmatch(file_name.lower(), name_pattern.lower()):
                    return False
            
            # Size criteria
            size_criteria = criteria.get('size', {})
            if size_criteria:
                if 'min' in size_criteria and file_size < size_criteria['min']:
                    return False
                if 'max' in size_criteria and file_size > size_criteria['max']:
                    return False
            
            # Date criteria
            date_criteria = criteria.get('date', {})
            if date_criteria:
                if 'after' in date_criteria and file_mtime < date_criteria['after']:
                    return False
                if 'before' in date_criteria and file_mtime > date_criteria['before']:
                    return False
            
            # File type criteria
            file_type = criteria.get('file_type')
            if file_type and file_type != 'all':
                type_extensions = {
                    'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'],
                    'video': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'],
                    'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
                    'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx'],
                    'code': ['.py', '.js', '.html', '.css', '.cpp', '.c', '.java', '.php', '.rb', '.go'],
                    'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
                    'executable': ['.exe', '.msi', '.app', '.deb', '.rpm', '.dmg']
                }
                
                if file_type in type_extensions and file_ext not in type_extensions[file_type]:
                    return False
            
            # Content search (for text files)
            content_search = criteria.get('content_search', '')
            if content_search and not is_dir:
                text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml', 
                                 '.md', '.rst', '.ini', '.cfg', '.conf', '.log', '.sql', '.csv'}
                if file_ext in text_extensions:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(1024 * 1024)  # Read first 1MB
                            if content_search.lower() not in content.lower():
                                return False
                    except:
                        return False
            
            return True
            
        except (OSError, PermissionError):
            return False
    
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
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            self.save_last_dir(current_tab.current_folder)
    
    def focus_search(self):
        """Focus the search input"""
        if not self.search_filter.isVisible():
            self.toggle_search_pane()
        self.search_filter.search_input.setFocus()
        self.search_filter.search_input.selectAll()
    
    def focus_content_search(self):
        """Focus the search field and enable content search mode"""
        if not self.search_filter.isVisible():
            self.toggle_search_pane()
        
        # Enable advanced filters and set content search
        if hasattr(self.search_filter, 'filters_group'):
            self.search_filter.filters_group.setChecked(True)
        
        # Focus content search field
        if hasattr(self.search_filter, 'content_search'):
            self.search_filter.content_search.setFocus()
            self.search_filter.content_search.selectAll()
        else:
            # Fallback to main search input
            self.search_filter.search_input.setFocus()
            self.search_filter.search_input.selectAll()
    
    def show_duplicate_finder(self):
        """Show duplicate file finder in a new tab as a table, with progress dialog (thread-safe)"""
        import hashlib
        import threading
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QProgressDialog
        from PyQt5.QtCore import Qt, QTimer

        class Worker:
            def __init__(self, folder):
                self.folder = folder
                self.progress = 0
                self.duplicates = None
                self.rows = None
                self.headers = None
                self.done = False
                self._progress_callback = None

            def set_progress_callback(self, cb):
                self._progress_callback = cb

            def run(self):
                hashes = {}
                total_files = 0
                for root, _, files in os.walk(self.folder):
                    total_files += len(files)
                scanned = 0
                for root, _, files in os.walk(self.folder):
                    for name in files:
                        path = os.path.join(root, name)
                        try:
                            with open(path, 'rb') as f:
                                h = hashlib.md5()
                                while True:
                                    chunk = f.read(8192)
                                    if not chunk:
                                        break
                                    h.update(chunk)
                                digest = h.hexdigest()
                            hashes.setdefault(digest, []).append(path)
                        except Exception:
                            continue
                        scanned += 1
                        if self._progress_callback and total_files > 0:
                            self._progress_callback(int(scanned * 100 / total_files))
                self.duplicates = {k: v for k, v in hashes.items() if len(v) > 1}
                self.rows = []
                for group_id, files in enumerate(self.duplicates.values(), 1):
                    for f in files:
                        self.rows.append((group_id, f))
                self.headers = ["Group", "File Path"]
                self.done = True

        def start_worker():
            current_tab = self.tab_manager.get_current_tab()
            folder = current_tab.current_folder if current_tab else os.getcwd()
            self.statusBar().showMessage("Scanning for duplicates...")
            worker = Worker(folder)
            def progress_cb(val):
                worker.progress = val
            worker.set_progress_callback(progress_cb)
            t = threading.Thread(target=worker.run, daemon=True)
            t.start()
            return worker, t

        progress_dialog = QProgressDialog("Scanning for duplicate files...", None, 0, 100, self)
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setWindowTitle("Please Wait")
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        worker, thread = start_worker()

        def poll():
            progress_dialog.setValue(worker.progress)
            if worker.done:
                progress_dialog.close()
                self.statusBar().showMessage(f"Found {sum(len(v) for v in (worker.duplicates or {}).values())} duplicate files" if worker.duplicates else "No duplicates found", 5000)
                self.open_results_tab("Duplicate Files", worker.headers, worker.rows)
                return
            QTimer.singleShot(100, poll)

        poll()

    def show_large_file_finder(self):
        """Show large file finder in a new tab as a table, with progress dialog (thread-safe)"""
        import threading
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout, QProgressDialog
        from PyQt5.QtCore import Qt, QTimer

        class Worker:
            def __init__(self, folder, limit=20):
                self.folder = folder
                self.limit = limit
                self.progress = 0
                self.files = None
                self.rows = None
                self.headers = None
                self.done = False
                self._progress_callback = None

            def set_progress_callback(self, cb):
                self._progress_callback = cb

            def run(self):
                file_sizes = []
                total_files = 0
                for root, _, files in os.walk(self.folder):
                    total_files += len(files)
                scanned = 0
                for root, _, files in os.walk(self.folder):
                    for name in files:
                        path = os.path.join(root, name)
                        try:
                            size = os.path.getsize(path)
                            file_sizes.append((path, size))
                        except Exception:
                            continue
                        scanned += 1
                        if self._progress_callback and total_files > 0:
                            self._progress_callback(int(scanned * 100 / total_files))
                file_sizes.sort(key=lambda x: x[1], reverse=True)
                self.files = file_sizes[:self.limit]
                self.rows = [(path, f"{size/1024/1024:.2f} MB") for path, size in self.files]
                self.headers = ["File Path", "Size"]
                self.done = True

        def start_worker():
            current_tab = self.tab_manager.get_current_tab()
            folder = current_tab.current_folder if current_tab else os.getcwd()
            self.statusBar().showMessage("Scanning for large files...")
            worker = Worker(folder)
            def progress_cb(val):
                worker.progress = val
            worker.set_progress_callback(progress_cb)
            t = threading.Thread(target=worker.run, daemon=True)
            t.start()
            return worker, t

        progress_dialog = QProgressDialog("Scanning for large files...", None, 0, 100, self)
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setWindowTitle("Please Wait")
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        worker, thread = start_worker()

        def poll():
            progress_dialog.setValue(worker.progress)
            if worker.done:
                progress_dialog.close()
                self.statusBar().showMessage(f"Found {len(worker.files) if worker.files else 0} large files", 5000)
                self.open_results_tab("Large Files", worker.headers, worker.rows)
                return
            QTimer.singleShot(100, poll)

        poll()

    def open_results_tab(self, title, headers, rows):
        """Open a new tab with a table of results (for search, large, duplicate, etc)"""
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(table)
        widget.setLayout(layout)
        self.tab_manager.tabs.append(widget)
        tab_index = self.tab_manager.tab_bar.addTab(title)
        self.tab_manager.tab_stack.addWidget(widget)
        self.tab_manager.tab_bar.setCurrentIndex(tab_index)
        self.tab_manager.tab_stack.setCurrentWidget(widget)
    
    def restore_view_states(self):
        """Restore view panel states from settings"""
        # Restore tree view state
        if not self.show_tree_view:
            self.left_pane.hide()
            try:
                self.toggle_tree_action.setChecked(False)
            except AttributeError:
                pass
        else:
            self.left_pane.show()
            try:
                self.toggle_tree_action.setChecked(True)
            except AttributeError:
                pass
        
        # Restore preview pane state
        if not self.show_preview_pane:
            self.preview_pane.hide()
            try:
                self.toggle_preview_action.setChecked(False)
            except AttributeError:
                pass
        else:
            self.preview_pane.show()
            try:
                self.toggle_preview_action.setChecked(True)
            except AttributeError:
                pass
        
        # Restore search panel state
        if self.search_visible:
            self.search_filter.show()
            try:
                self.search_toggle_action.setChecked(True)
            except AttributeError:
                pass
            try:
                self.toggle_search_action.setChecked(True)
            except AttributeError:
                pass
        else:
            self.search_filter.hide()
            try:
                self.search_toggle_action.setChecked(False)
            except AttributeError:
                pass
            try:
                self.toggle_search_action.setChecked(False)
            except AttributeError:
                pass
    
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
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            self.save_last_dir(current_tab.current_folder)
    
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
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            self.save_last_dir(current_tab.current_folder)

    def toggle_icon_view_icons_only(self, checked):
        """Toggle whether Icon View uses simple icons (no previews) and persist the choice"""
        try:
            self.icon_view_use_icons_only = bool(checked)
            # Persist to settings file (merge with existing settings)
            settings = {}
            if os.path.exists(self.SETTINGS_FILE):
                try:
                    with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                except Exception:
                    settings = {}
            settings['icon_view_use_icons_only'] = self.icon_view_use_icons_only
            try:
                with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
            except Exception as e:
                print(f"Error saving settings: {e}")
        except Exception:
            pass
    
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
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        folder_name, ok = QInputDialog.getText(
            self, 'New Folder', 'Enter folder name:', 
            text='New Folder'
        )
        if ok and folder_name.strip():
            new_folder_path = os.path.join(current_tab.current_folder, folder_name.strip())
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
        try:
            current_tab = self.tab_manager.get_current_tab()
            if not current_tab:
                return
            dialog = AdvancedOperationsDialog(self.selected_items, current_tab.current_folder, self)
            dialog.setAttribute(Qt.WA_DeleteOnClose)  # Ensure proper cleanup
            dialog.exec_()
        except Exception as e:
            print(f"Error showing advanced operations dialog: {e}")
            import traceback
            traceback.print_exc()
    
    def go_back(self):
        """Navigate back in history"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab and current_tab.can_go_back():
            current_tab.go_back()
        # If can't go back, fall back to going up one directory
        elif current_tab:
            self.go_up()
    
    def go_forward(self):
        """Navigate forward in history"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab and current_tab.can_go_forward():
            current_tab.go_forward()
            # Refresh view and address bar after navigation
            if hasattr(current_tab, 'refresh_current_view'):
                current_tab.refresh_current_view()
            if hasattr(self, 'address_bar'):
                self.address_bar.setText(current_tab.current_folder)
    
    def increase_thumbnail_size(self):
        """Increase thumbnail size"""
        # Allow expanding up to 768 to support large photo-style thumbnails
        new_size = min(768, self.thumbnail_size + 16)
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
        """Open a file with the default application or built-in archive browser"""
        try:
            # Check if it's an archive file and use built-in browser
            if ArchiveManager.is_archive(file_path):
                self.browse_archive_contents(file_path)
            else:
                if not PlatformUtils.open_file_with_default_app(file_path):
                    self.show_error_message("Error", f"Cannot open file: {file_path}")
        except Exception as e:
            self.show_error_message("Error", f"Cannot open file: {str(e)}")
    
    def show_info_message(self, title, message):
        """Show an information message"""
        QMessageBox.information(self, title, message)
    
    # Enhanced clipboard methods
    # ...existing code...
    
    def paste_action_triggered(self):
        """Enhanced paste action with async progress"""
        operation, paths = self.clipboard_manager.get_current_operation()
        if not operation or not paths:
            return

        # Normalize 'cut' to 'move' for AsyncFileOperation
        op = 'move' if operation == 'cut' else operation

        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return

        # If exactly one folder is selected in the UI, use that folder as the paste destination
        selection = getattr(self, 'selected_items', []) or []
        selected_folders = [p for p in selection if os.path.isdir(p)]
        if len(selected_folders) == 1:
            destination = selected_folders[0]
        else:
            destination = current_tab.current_folder

        # Use the async paste operation for better progress tracking
        self.paste_multiple_items(paths, destination, op)

        # Clear clipboard if this was a cut operation
        if operation == 'cut':
            self.clipboard_manager.clear_current()

    def navigate_to_path(self, path):
        """Navigate to a specific path (called from breadcrumb)"""
        try:
            if os.path.exists(path) and os.path.isdir(path):
                # Update current tab
                current_tab = self.tab_manager.get_current_tab()
                if current_tab:
                    current_tab.navigate_to(path)
                
                # Update tree view
                index = self.model.index(path)
                self.tree_view.setCurrentIndex(index)
                self.tree_view.expand(index)
                
                # Update current folder reference
                self.current_folder = path

                # Automatically pre-cache video thumbnails in the background using QThread
                if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                    try:
                        from PyQt5.QtCore import QThread, pyqtSignal, QObject

                        class ThumbnailPrecacheWorker(QObject):
                            finished = pyqtSignal()
                            def __init__(self, directory, thumbnail_cache, size):
                                super().__init__()
                                self.directory = directory
                                self.thumbnail_cache = thumbnail_cache
                                self.size = size
                            def run(self):
                                try:
                                    precache_video_thumbnails_in_directory(self.directory, self.thumbnail_cache, size=self.size, parent=None, show_progress=True)
                                except Exception as e:
                                    pass
                                self.finished.emit()

                        self._thumb_thread = QThread()
                        self._thumb_worker = ThumbnailPrecacheWorker(path, self.thumbnail_cache, getattr(self, 'thumbnail_size', 128))
                        self._thumb_worker.moveToThread(self._thumb_thread)
                        self._thumb_thread.started.connect(self._thumb_worker.run)
                        self._thumb_worker.finished.connect(self._thumb_thread.quit)
                        self._thumb_worker.finished.connect(self._thumb_worker.deleteLater)
                        self._thumb_thread.finished.connect(self._thumb_thread.deleteLater)
                        self._thumb_thread.start()
                    except Exception as e:
                        pass
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

    def eventFilter(self, obj, event):
        """Handle events on the scroll area viewport to catch clicks in blank areas"""
        # Get current tab
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return super().eventFilter(obj, event)
        if (hasattr(current_tab, 'scroll_area') and hasattr(current_tab.scroll_area, 'viewport') and
            obj == current_tab.scroll_area.viewport() and 
            hasattr(current_tab, 'get_icon_container_safely') and
            current_tab.get_icon_container_safely() and
            self.view_mode_manager.get_mode() == 'thumbnail'):

            # Handle mouse presses, releases and platform context-menu events so
            # right-click on empty space works reliably on different platforms.
            # Diagnostic: print event info when installed on viewport so we can
            # trace why right-clicks may not be reaching the empty-space handler.
            try:
                evt_name = str(event.type())
            except Exception:
                evt_name = '<unknown>'
            # Quiet by default: use the event_filter_debug toggle so output appears only when enabled
            event_filter_debug('Received event type={} obj={}', event.type(), repr(obj))
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    # Map viewport coordinates to icon container coordinates
                    icon_container = current_tab.get_icon_container_safely()
                    if not icon_container:
                        return super().eventFilter(obj, event)

                    viewport_pos = event.pos()
                    container_global_pos = current_tab.scroll_area.viewport().mapToGlobal(viewport_pos)
                    container_pos = icon_container.mapFromGlobal(container_global_pos)

                    # Check if there's a widget at this position in the container
                    child_widget = icon_container.childAt(container_pos)

                    # If no child widget, click is outside container bounds, or not an icon widget
                    is_empty_space = (child_widget is None or 
                                      child_widget == icon_container or
                                      isinstance(child_widget, QLayout) or
                                      not hasattr(child_widget, 'full_path') or
                                      not icon_container.rect().contains(container_pos))

                    if is_empty_space:
                        # Deselect visually but allow the event to propagate so
                        # the IconContainer can start a rubber-band (drag) selection.
                        # Consuming the press event here prevents the container from
                        # receiving mousePressEvent and starting the selection rect.
                        self.deselect_icons()
                        # Return False so the event is not treated as handled and
                        # proceeds to the container widget.
                        return False

                # For MouseButtonPress right-button we'll handle here, but some
                # platforms or input methods generate MouseButtonRelease or
                # ContextMenu events instead — those are handled below.
                elif event.button() == Qt.RightButton:
                    icon_container = current_tab.get_icon_container_safely()
                    if not icon_container:
                        return super().eventFilter(obj, event)

                    viewport_pos = event.pos()
                    container_global_pos = current_tab.scroll_area.viewport().mapToGlobal(viewport_pos)
                    container_pos = icon_container.mapFromGlobal(container_global_pos)
                    child_widget = icon_container.childAt(container_pos)

                    is_empty_space = (child_widget is None or 
                                    child_widget == icon_container or
                                    isinstance(child_widget, QLayout) or
                                    not hasattr(child_widget, 'full_path') or
                                    not icon_container.rect().contains(container_pos))

                    if is_empty_space:
                        print(f"[EVENT-FILTER] RightButton Press on empty space at viewport_pos={viewport_pos} global={event.globalPos()}")
                        self.empty_space_right_clicked(event.globalPos())
                        return True  # Event handled

            elif event.type() == QEvent.MouseButtonRelease:
                # Some systems deliver context clicks on release instead of press
                if hasattr(event, 'button') and event.button() == Qt.RightButton:
                    icon_container = current_tab.get_icon_container_safely()
                    if not icon_container:
                        return super().eventFilter(obj, event)

                    viewport_pos = event.pos()
                    container_global_pos = current_tab.scroll_area.viewport().mapToGlobal(viewport_pos)
                    container_pos = icon_container.mapFromGlobal(container_global_pos)
                    child_widget = icon_container.childAt(container_pos)

                    is_empty_space = (child_widget is None or 
                                    child_widget == icon_container or
                                    isinstance(child_widget, QLayout) or
                                    not hasattr(child_widget, 'full_path') or
                                    not icon_container.rect().contains(container_pos))

                    if is_empty_space:
                        print(f"[EVENT-FILTER] RightButton Release on empty space at viewport_pos={viewport_pos} global={event.globalPos()}")
                        self.empty_space_right_clicked(event.globalPos())
                        return True

            elif event.type() == QEvent.ContextMenu:
                # QContextMenuEvent: use its globalPos() to detect empty area
                try:
                    global_pos = event.globalPos()
                except Exception:
                    return super().eventFilter(obj, event)

                icon_container = current_tab.get_icon_container_safely()
                if not icon_container:
                    return super().eventFilter(obj, event)

                # Map the global position into container coordinates
                container_pos = icon_container.mapFromGlobal(global_pos)
                child_widget = icon_container.childAt(container_pos)

                is_empty_space = (child_widget is None or 
                                child_widget == icon_container or
                                isinstance(child_widget, QLayout) or
                                not hasattr(child_widget, 'full_path') or
                                not icon_container.rect().contains(container_pos))

                if is_empty_space:
                    print(f"[EVENT-FILTER] ContextMenu event on empty space global={global_pos}")
                    self.empty_space_right_clicked(global_pos)
                    return True
        
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Handle application close event with proper cleanup to prevent hanging"""
        try:
            print("Starting application shutdown...")
            
            # Step 1: Save application state quickly
            self.save_application_state()
            
            # Step 2: Stop background operations and threads
            self.stop_background_operations()
            
            # Step 3: Clean up resources
            self.cleanup_resources()
            
            # Step 4: Accept the close event
            event.accept()
            
            # Step 5: Force exit for problematic environments
            self.force_exit_if_needed()
            
        except Exception as e:
            print(f"Error during closeEvent: {e}")
            event.accept()  # Always accept to prevent hanging
            
    def save_application_state(self):
        """Save application state and settings"""
        try:
            # Save the last directory from the current active tab first
            current_tab = self.tab_manager.get_current_tab()
            if current_tab:
                self.save_last_dir(current_tab.current_folder)
                
            # Save sort settings for all tabs
            self.save_all_tab_sort_settings()
            
            # Save window geometry and state if settings exists
            if hasattr(self, 'settings') and self.settings:
                self.settings.setValue("geometry", self.saveGeometry())
                self.settings.setValue("windowState", self.saveState())
                
        except Exception as e:
            print(f"Error saving application state: {e}")
            
    def stop_background_operations(self):
        """Stop all background operations and timers with proper cleanup"""
        try:
            print("Stopping background operations...")
            
            # Clean up memory manager
            if hasattr(self, 'memory_manager') and self.memory_manager:
                print("Cleaning up memory manager...")
                try:
                    self.memory_manager.cleanup()
                except Exception as e:
                    print(f"Error cleaning up memory manager: {e}")
            
            # Clean up background monitor
            if hasattr(self, 'background_monitor') and self.background_monitor:
                print("Cleaning up background monitor...")
                try:
                    self.background_monitor.cleanup()
                except Exception as e:
                    print(f"Error cleaning up background monitor: {e}")
            
            # Clean up thumbnail cache
            if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                print("Cleaning up thumbnail cache...")
                try:
                    self.thumbnail_cache.cleanup()
                except Exception as e:
                    print(f"Error cleaning up thumbnail cache: {e}")
            
            # Clean up virtual file loader
            if hasattr(self, 'virtual_file_loader') and self.virtual_file_loader:
                print("Cleaning up virtual file loader...")
                try:
                    self.virtual_file_loader.cleanup()
                except Exception as e:
                    print(f"Error cleaning up virtual file loader: {e}")
            
            # Clean up search engine
            if hasattr(self, 'search_engine') and self.search_engine:
                print("Cleaning up search engine...")
                try:
                    self.search_engine.cleanup()
                except Exception as e:
                    print(f"Error cleaning up search engine: {e}")
            
            # Clean up search filter widget
            if hasattr(self, 'search_filter') and self.search_filter:
                print("Cleaning up search filter...")
                try:
                    self.search_filter.cleanup()
                except Exception as e:
                    print(f"Error cleaning up search filter: {e}")
            
            # Stop all active operations
            if hasattr(self, 'active_operations'):
                print(f"Stopping {len(self.active_operations)} active operations...")
                for operation in list(self.active_operations):
                    try:
                        if hasattr(operation, 'cancelled'):
                            operation.cancelled = True
                        if hasattr(operation, 'stop'):
                            operation.stop()
                    except Exception as e:
                        print(f"Error stopping operation: {e}")
                self.active_operations.clear()
            
            # Stop any other timers
            timers = self.findChildren(QTimer)
            if timers:
                print(f"Stopping {len(timers)} timers...")
                for timer in timers:
                    if timer.isActive():
                        try:
                            timer.stop()
                        except Exception as e:
                            print(f"Error stopping timer: {e}")
                            
        except Exception as e:
            print(f"Error stopping background operations: {e}")
            
    def cleanup_resources(self):
        """Clean up threads and other resources with memory leak prevention"""
        try:
            print("Cleaning up resources...")
            
            # Clean up memory management components first
            if hasattr(self, 'memory_manager') and self.memory_manager:
                try:
                    # Clear cleanup callbacks to break circular references
                    if hasattr(self.memory_manager, 'cleanup_callbacks'):
                        self.memory_manager.cleanup_callbacks.clear()
                    self.memory_manager = None
                except Exception as e:
                    print(f"Error cleaning memory manager: {e}")
            
            if hasattr(self, 'background_monitor') and self.background_monitor:
                try:
                    # Clear callbacks to break circular references
                    if hasattr(self.background_monitor, 'callbacks'):
                        self.background_monitor.callbacks.clear()
                    if hasattr(self.background_monitor, 'monitored_directories'):
                        self.background_monitor.monitored_directories.clear()
                    self.background_monitor = None
                except Exception as e:
                    print(f"Error cleaning background monitor: {e}")
            
            if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                try:
                    # Clear all cache data
                    if hasattr(self.thumbnail_cache, 'memory_cache'):
                        self.thumbnail_cache.memory_cache.clear()
                    if hasattr(self.thumbnail_cache, 'metadata'):
                        self.thumbnail_cache.metadata.clear()
                    self.thumbnail_cache = None
                except Exception as e:
                    print(f"Error cleaning thumbnail cache: {e}")
            
            if hasattr(self, 'virtual_file_loader') and self.virtual_file_loader:
                try:
                    # Clear all loaded data
                    if hasattr(self.virtual_file_loader, 'loaded_chunks'):
                        self.virtual_file_loader.loaded_chunks.clear()
                    if hasattr(self.virtual_file_loader, 'directory_cache'):
                        self.virtual_file_loader.directory_cache.clear()
                    self.virtual_file_loader = None
                except Exception as e:
                    print(f"Error cleaning virtual file loader: {e}")
            
            # Find and terminate all QThread children
            threads = self.findChildren(QThread)
            if threads:
                print(f"Cleaning up {len(threads)} threads...")
                for thread in threads:
                    if thread.isRunning():
                        print(f"Stopping thread: {thread.__class__.__name__}")
                        thread.requestInterruption()
                        if not thread.wait(1000):  # Wait 1 second
                            print(f"Force terminating thread: {thread.__class__.__name__}")
                            thread.terminate()
                            thread.wait(500)  # Wait another 0.5 seconds
            
            # Clear operation references to prevent memory leaks
            if hasattr(self, 'active_operations'):
                self.active_operations.clear()
            if hasattr(self, 'operation_progress_dialogs'):
                self.operation_progress_dialogs.clear()
                
            # Process any pending events
            QApplication.processEvents()
            
            # Force garbage collection
            import gc
            collected = gc.collect()
            print(f"Garbage collection freed {collected} objects")
            
            print("Resource cleanup complete")
            
        except Exception as e:
            print(f"Error cleaning up resources: {e}")
            
    def force_exit_if_needed(self):
        """Force exit for problematic environments like Windows"""
        try:
            if sys.platform.startswith('win'):
                print("Windows detected - using aggressive exit strategy")
                # Give Qt a moment to clean up
                QApplication.processEvents()
                
                # Start background force exit as fallback
                import threading
                import time
                
                def delayed_force_exit():
                    time.sleep(2.0)  # Wait 2 seconds
                    print("Force exiting process...")
                    import os
                    os._exit(0)
                    
                force_thread = threading.Thread(target=delayed_force_exit, daemon=True)
                force_thread.start()
                
        except Exception as e:
            print(f"Error in force exit: {e}")

            
    def get_current_tab_session(self):
        """Get current tab session information for saving"""
        try:
            if hasattr(self, 'tab_manager') and self.tab_manager:
                tab_session = {
                    "tabs": [],
                    "active_tab_index": self.tab_manager.tab_bar.currentIndex()
                }
                
                for i, tab in enumerate(self.tab_manager.tabs):
                    if hasattr(tab, 'current_folder') and tab.current_folder:
                        tab_info = {
                            "path": tab.current_folder,
                            "title": self.tab_manager.tab_bar.tabText(i)
                        }
                        tab_session["tabs"].append(tab_info)
                
                return tab_session
        except Exception as e:
            print(f"Error getting tab session: {e}")
        
        # Fallback: single tab with current directory
        return {
            "tabs": [{"path": os.path.expanduser("~"), "title": "Home"}],
            "active_tab_index": 0
        }

    def save_last_dir(self, path):
        try:
            # Get current tab session info
            tab_session = self.get_current_tab_session()
            
            # Load existing settings to preserve tab_sort_settings
            existing_data = {}
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    existing_data = json.load(f)
            
            data = {
                "last_dir": path,
                "thumbnail_size": self.thumbnail_size,
                "dark_mode": self.dark_mode,
                "icons_wide": self.icons_wide,
                "view_mode": self.view_mode_manager.get_mode(),
                "show_tree_view": self.show_tree_view,
                "show_preview_pane": self.show_preview_pane,
                "search_visible": self.search_visible,
                "tab_session": tab_session
            }
            
            # Preserve tab_sort_settings if they exist
            if "tab_sort_settings" in existing_data:
                data["tab_sort_settings"] = existing_data["tab_sort_settings"]
            
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
                    
                    # Load tab session if available
                    if "tab_session" in data:
                        self.saved_tab_session = data["tab_session"]
                    else:
                        self.saved_tab_session = None
                    
                    last_dir = data.get("last_dir", None)
                    
                    # Additional validation for macOS 11.0.5
                    if last_dir and sys.platform == 'darwin':
                        # Verify the directory still exists and is accessible
                        if os.path.exists(last_dir) and os.access(last_dir, os.R_OK):
                            return last_dir
                    elif last_dir and os.path.exists(last_dir):
                        return last_dir
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        # Default fallback for macOS 11.0.5
        if sys.platform == 'darwin':
            return os.path.expanduser('~')
        
        return None

    def on_tab_changed(self):
        """Handle tab changes - save session and update sort menu"""
        try:
            # Update sort menu checkmarks for new tab
            self.update_sort_menu_checkmarks()
            # Save tab session
            self.save_tab_session()
            # Ensure the newly active tab has its signals connected and
            # the viewport event filter installed so selection and
            # right-click handling continue to work after switching tabs.
            try:
                current_tab = None
                if hasattr(self, 'tab_manager') and self.tab_manager:
                    current_tab = self.tab_manager.get_current_tab()

                if current_tab:
                    # Install event filter on the viewport if available
                    try:
                        if hasattr(current_tab, 'scroll_area') and current_tab.scroll_area is not None:
                            viewport = current_tab.scroll_area.viewport()
                            if viewport is not None:
                                # Use self (the main window) as the event filter target
                                viewport.installEventFilter(self)
                    except Exception:
                        pass

                    # Reconnect icon container signals for the active tab
                    try:
                        self.connect_tab_signals(current_tab)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception as e:
            print(f"Error handling tab change: {e}")

    def save_tab_session(self):
        """Save current tab session automatically"""
        try:
            # Re-save all settings including current tab session
            current_path = getattr(self, 'current_folder', os.path.expanduser("~"))
            self.save_last_dir(current_path)
        except Exception as e:
            print(f"Error saving tab session: {e}")

    def restore_tab_session(self):
        """Restore saved tab session"""
        if hasattr(self, 'saved_tab_session') and self.saved_tab_session:
            try:
                tab_session = self.saved_tab_session
                
                # Clear the initial default tab
                if hasattr(self, 'tab_manager') and len(self.tab_manager.tabs) > 0:
                    self.tab_manager.close_tab(0)
                
                # Restore saved tabs
                restored_tabs = 0
                for tab_info in tab_session.get("tabs", []):
                    path = tab_info.get("path", "")
                    if path and os.path.exists(path) and os.path.isdir(path):
                        try:
                            new_tab = self.tab_manager.new_tab(path)
                            restored_tabs += 1
                        except Exception as e:
                            print(f"Error restoring tab {path}: {e}")
                
                # If no tabs were restored, create a default one
                if restored_tabs == 0:
                    self.tab_manager.new_tab(os.path.expanduser("~"))
                else:
                    # Set the active tab from saved session
                    active_index = tab_session.get("active_tab_index", 0)
                    if (0 <= active_index < len(self.tab_manager.tabs) and 
                        active_index < self.tab_manager.tab_stack.count()):
                        self.tab_manager.tab_bar.setCurrentIndex(active_index)
                        # Verify the widget is actually in the stack before setting it
                        target_tab = self.tab_manager.tabs[active_index]
                        stack_widget_index = self.tab_manager.tab_stack.indexOf(target_tab)
                        if stack_widget_index >= 0:
                            self.tab_manager.tab_stack.setCurrentWidget(target_tab)
                        else:
                            print(f"Warning: Tab widget not found in stack, using index 0")
                            if len(self.tab_manager.tabs) > 0:
                                self.tab_manager.tab_bar.setCurrentIndex(0)
                                self.tab_manager.tab_stack.setCurrentIndex(0)
                
                print(f"Restored {restored_tabs} tabs from previous session")
                
            except Exception as e:
                print(f"Error restoring tab session: {e}")
                # Fallback to default tab
                if hasattr(self, 'tab_manager') and len(self.tab_manager.tabs) == 0:
                    self.tab_manager.new_tab(os.path.expanduser("~"))
        else:
            # No saved session found (first launch or no settings file) - create a default tab
            if hasattr(self, 'tab_manager'):
                if len(self.tab_manager.tabs) == 0:
                    default_path = self.last_dir if hasattr(self, 'last_dir') and self.last_dir else os.path.expanduser("~")
                    self.tab_manager.new_tab(default_path)

    def open_website(self):
        """Open the website in the default browser"""
        webbrowser.open("https://turkokards.com")

    def show_bulk_rename_dialog(self):
        """Show bulk rename dialog for selected files or all files in current directory"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            QMessageBox.warning(self, "Error", "No active tab found")
            return
            
        # Determine which files to rename
        if self.selected_items:
            files_to_rename = [path for path in self.selected_items if os.path.isfile(path)]
            dialog_title = "Bulk Rename {} Selected Files".format(len(files_to_rename))
        else:
            # Get all files in current directory (excluding folders)
            try:
                all_items = os.listdir(current_tab.current_folder)
                files_to_rename = [os.path.join(current_tab.current_folder, item) 
                                 for item in all_items 
                                 if os.path.isfile(os.path.join(current_tab.current_folder, item)) 
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
        pattern_type = QComboBox()
        pattern_type.addItems([
            "Find and Replace",
            "Add Prefix", 
            "Add Suffix",
            "Number Files (1, 2, 3...)",
            "Custom Pattern"
        ])
        pattern_layout.addWidget(QLabel("Rename Type:"), 0, 0)
        pattern_layout.addWidget(pattern_type, 0, 1)
        
        # Find/Replace inputs (shown by default)
        pattern_layout.addWidget(QLabel("Find:"), 1, 0)
        find_text = QLineEdit()
        pattern_layout.addWidget(find_text, 1, 1)
        
        pattern_layout.addWidget(QLabel("Replace with:"), 2, 0)
        replace_text = QLineEdit()
        pattern_layout.addWidget(replace_text, 2, 1)
        
        # Custom pattern input (hidden by default)
        pattern_layout.addWidget(QLabel("Pattern:"), 3, 0)
        pattern_text = QLineEdit()
        pattern_text.setPlaceholderText("Use {name} for filename, {ext} for extension, {n} for number")
        pattern_layout.addWidget(pattern_text, 3, 1)
        
        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)
        
        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        
        preview_table = QTableWidget()
        preview_table.setColumnCount(2)
        preview_table.setHorizontalHeaderLabels(["Original Name", "New Name"])
        preview_table.horizontalHeader().setStretchLastSection(True)
        preview_table.setAlternatingRowColors(False)  # Use solid background color
        
        # Set solid background color based on theme mode
        if self.dark_mode:
            preview_table.setStyleSheet("QTableWidget { background-color: black; color: white; }")
        else:
            preview_table.setStyleSheet("QTableWidget { background-color: white; color: black; }")
            
        preview_layout.addWidget(preview_table)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        button_layout.addStretch()
        
        
        # Update preview function
        def update_preview():
            """Update the preview table with new file names"""
            pattern_type_text = pattern_type.currentText()
            
            preview_table.setRowCount(len(files_to_rename))
            
            for i, file_path in enumerate(files_to_rename):
                original_name = os.path.basename(file_path)
                
                # Generate new name based on pattern type
                try:
                    if pattern_type_text == "Find and Replace":
                        new_name = original_name.replace(find_text.text(), replace_text.text())
                    elif pattern_type_text == "Add Prefix":
                        new_name = find_text.text() + original_name
                    elif pattern_type_text == "Add Suffix":
                        name, ext = os.path.splitext(original_name)
                        new_name = name + find_text.text() + ext
                    elif pattern_type_text == "Number Files (1, 2, 3...)":
                        name, ext = os.path.splitext(original_name)
                        new_name = f"{i+1:03d}{ext}"
                    elif pattern_type_text == "Custom Pattern":
                        name, ext = os.path.splitext(original_name)
                        new_name = pattern_text.text().replace("{name}", name).replace("{ext}", ext).replace("{n}", str(i+1))
                    else:
                        new_name = original_name
                except Exception:
                    new_name = original_name
                
                # Set table items
                preview_table.setItem(i, 0, QTableWidgetItem(original_name))
                preview_table.setItem(i, 1, QTableWidgetItem(new_name))
                
                # Color invalid names red
                if not new_name or new_name == original_name:
                    preview_table.item(i, 1).setBackground(QColor(255, 200, 200))
        
        # Toggle visibility function
        def toggle_controls():
            """Show/hide controls based on selected pattern type"""
            pattern_type_text = pattern_type.currentText()
            
            # Hide/show find/replace controls
            if pattern_type_text == "Find and Replace":
                find_text.setVisible(True)
                replace_text.setVisible(True)
                pattern_text.setVisible(False)
            else:
                find_text.setVisible(False) 
                replace_text.setVisible(False)
                pattern_text.setVisible(pattern_type_text == "Custom Pattern")
        
        # Connect events
        pattern_type.currentTextChanged.connect(lambda: (toggle_controls(), update_preview()))
        find_text.textChanged.connect(update_preview)
        replace_text.textChanged.connect(update_preview)
        pattern_text.textChanged.connect(update_preview)
        
        # Rename button
        rename_button = QPushButton("Rename Files")
        rename_button.clicked.connect(lambda: self.execute_bulk_rename(files_to_rename, dialog, pattern_type, find_text, replace_text, pattern_text, preview_table))
        button_layout.addWidget(rename_button)
        
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Initialize controls and preview
        toggle_controls()
        update_preview()
        
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

    def execute_bulk_rename(self, files_to_rename, dialog, pattern_type_widget, find_text_widget, replace_text_widget, pattern_text_widget, preview_table_widget):
        """Execute the bulk rename operation"""
        pattern_type = pattern_type_widget.currentText()
        
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
                    new_name = self.generate_new_filename(old_name, find_text_widget.text(), replace_text_widget.text())
                elif pattern_type == "Add Prefix":
                    new_name = find_text_widget.text() + old_name
                elif pattern_type == "Add Suffix":
                    name, ext = os.path.splitext(old_name)
                    new_name = name + find_text_widget.text() + ext
                elif pattern_type == "Number Files (1, 2, 3...)":
                    name, ext = os.path.splitext(old_name)
                    new_name = f"{i+1:03d}{ext}"
                elif pattern_type == "Custom Pattern":
                    name, ext = os.path.splitext(old_name)
                    new_name = pattern_text_widget.text().replace("{name}", name).replace("{ext}", ext).replace("{n}", str(i+1))
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
        self.refresh_current_view()
        dialog.accept()

    def go_up(self):
        """Navigate to parent directory"""
        try:
            # Get current tab
            current_tab = self.tab_manager.get_current_tab()
            if not current_tab:
                return
            try:
                pass
            except Exception:
                pass
                
            current_path = current_tab.current_folder
            parent_path = os.path.dirname(current_path)

            # Use os.path.ismount to detect drive roots reliably
            try:
                is_drive_root = bool(current_path) and os.path.ismount(current_path)
            except Exception:
                is_drive_root = (current_path and os.path.normpath(current_path) == os.path.abspath(os.sep))

            if is_drive_root:
                try:
                    current_tab.navigate_to("__MY_COMPUTER__")
                except Exception:
                    try:
                        self.tab_manager.new_tab("__MY_COMPUTER__")
                    except Exception:
                        pass
                return

            # Check if we can go up (not at root)
            if parent_path and os.path.exists(parent_path) and parent_path != current_path:
                # Navigate to parent directory
                current_tab.navigate_to(parent_path)
        except Exception as e:
            self.show_error_message("Navigation Error", "Could not navigate to parent directory", str(e))

    def on_tree_item_clicked(self, index):
        try:
            file_path = self.model.filePath(index)

            # Additional validation for macOS 11.0.5
            if sys.platform == 'darwin':
                if not os.path.exists(file_path):
                    self.show_error_message("Path Error", f"Path no longer exists: {file_path}")
                    return
                if not os.access(file_path, os.R_OK):
                    self.show_error_message("Permission Error", f"Cannot access: {file_path}")
                    return

            # If it's a directory, navigate the active tab to it
            if QFileInfo(file_path).isDir():
                try:
                    # Ensure directory is listable
                    os.listdir(file_path)
                except (OSError, PermissionError) as e:
                    self.show_error_message("Access Error", f"Cannot access directory: {file_path}", str(e))
                    return

                current_tab = None
                try:
                    current_tab = self.tab_manager.get_current_tab()
                except Exception:
                    current_tab = None

                if current_tab:
                    # Navigate current tab to the selected folder and refresh
                    current_tab.navigate_to(file_path)
                else:
                    # No active tab: create a new one at this folder
                    self.tab_manager.new_tab(file_path)
            else:
                # If a file was clicked, optionally navigate to its parent in the active tab
                parent_dir = os.path.dirname(file_path)
                if parent_dir:
                    current_tab = self.tab_manager.get_current_tab()
                    if current_tab:
                        current_tab.navigate_to(parent_dir)
        except Exception as e:
            self.show_error_message("Tree Navigation Error", "Error accessing selected item", str(e))

    def update_thumbnail_view(self, folder_path):
        """Compatibility method - navigate current tab to folder_path"""
        try:
            current_tab = self.tab_manager.get_current_tab()
            if current_tab:
                current_tab.navigate_to(folder_path)
            else:
                # Fallback: create new tab if no current tab
                self.tab_manager.new_tab(folder_path)
        except Exception as e:
            print(f"Error in update_thumbnail_view: {e}")
            # If tab navigation fails, try to create a new tab
            try:
                self.tab_manager.new_tab(folder_path)
            except Exception as e2:
                print(f"Error creating new tab: {e2}")
        self.clear_thumbnail_view()
        
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
                
                # Create icon widget (respect icon-only view and thumbnail cache)
                use_icon_only = bool(self.view_mode_manager.get_mode() == ViewModeManager.ICON_VIEW)
                if hasattr(self, 'thumbnail_cache') and self.thumbnail_cache:
                    icon_widget = IconWidget(item_name, full_path, is_dir, self.thumbnail_size, self.thumbnail_cache, use_icon_only)
                else:
                    icon_widget = IconWidget(item_name, full_path, is_dir, self.thumbnail_size, None, use_icon_only)
                
                # Connect click signals
                icon_widget.clicked.connect(self.icon_clicked)
                icon_widget.doubleClicked.connect(self.icon_double_clicked)
                icon_widget.rightClicked.connect(self.icon_right_clicked)
                
                # Add to container based on current view mode
                if self.view_mode_manager.get_mode() == "icon":
                    # Icon view - use optimized grid layout
                    icon_container = getattr(self, 'icon_container', None)
                    if icon_container:
                        icon_container.add_widget_optimized(icon_widget, self.thumbnail_size, self.icons_wide)
                elif self.view_mode_manager.get_mode() == "list":
                    # List view - add to list view
                    formatted_name = format_filename_with_underscore_wrap(item_name)
                    item = QListWidgetItem(formatted_name)
                    item.setData(Qt.UserRole, full_path)  # Store full path
                    if is_dir:
                        item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
                    else:
                        item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
                    self.list_view.addItem(item)
                elif self.view_mode_manager.get_mode() == "detail":
                    # Detail view uses a model-view architecture, data comes from the file system model
                    # The FormattedFileSystemModel will automatically populate when we set the root path
                    # Individual files don't need to be added manually here
                    pass
                
            except Exception as e:
                print(f"Error creating icon widget for {item_name}: {e}")
                continue
                
        # After processing all items, ensure detail view is properly refreshed if we're in detail mode
        if self.view_mode_manager.get_mode() == "detail":
            current_tab = self.tab_manager.get_current_tab()
            if current_tab and hasattr(current_tab, 'refresh_detail_view'):
                current_tab.refresh_detail_view()

    def clear_thumbnail_view(self):
        """Clear all items from the current view"""
        # Get current tab and clear its thumbnail/icon view
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container:
                # Clear grid layout by removing all widgets
                layout = icon_container.layout()
                if layout:
                    while layout.count():
                        child = layout.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
        
        # Clear detail view rows (QTableView) - this would be in current tab if it exists
        if current_tab and hasattr(current_tab, 'detail_view') and hasattr(current_tab, 'detail_model'):
            # For QTableView with QFileSystemModel, we need to reset the model or set an empty root
            # Setting root to an empty/non-existent path effectively clears the view
            current_tab.detail_model.setRootPath("")

    def deselect_icons(self):
        """Deselect all icons in the current view"""
        self.selected_items = []
        
        # Get the current tab and clear its selection
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container and hasattr(icon_container, 'clear_selection'):
                icon_container.clear_selection()
        
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
        # Get the current tab and its icon container
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        if modifiers & Qt.ControlModifier:
            # Ctrl+click: toggle selection
            if full_path in self.selected_items:
                self.selected_items.remove(full_path)
                current_tab.icon_container.remove_from_selection_by_path(full_path)
            else:
                self.selected_items.append(full_path)
                current_tab.icon_container.add_to_selection_by_path(full_path)
        elif modifiers & Qt.ShiftModifier:
            # Shift+click: range selection (simplified)
            if full_path not in self.selected_items:
                self.selected_items.append(full_path)
                current_tab.icon_container.add_to_selection_by_path(full_path)
        else:
            # Regular click: select only this item — but if the user clicked
            # an item that is already part of a multi-selection, keep the
            # existing selection so a drag of the whole selection can start.
            if full_path in self.selected_items and len(self.selected_items) > 1:
                # Preserve existing multi-selection (likely a drag start)
                pass
            else:
                self.selected_items = [full_path]
                current_tab.icon_container.clear_selection()
                current_tab.icon_container.add_to_selection_by_path(full_path)
        
        # Notify main window of selection change
        self.on_selection_changed(self.selected_items)

    def icon_double_clicked(self, full_path):
        """Handle double-click on an icon"""
        if os.path.isdir(full_path):
            # Navigate to the folder in the current tab
            current_tab = self.tab_manager.get_current_tab()
            if current_tab:
                current_tab.navigate_to_path(full_path)
        elif ArchiveManager.is_archive(full_path):
            # For archive files, show browse dialog instead of opening externally
            self.browse_archive_contents(full_path)
        else:
            # Open file with default application using platform utilities
            try:
                if not PlatformUtils.open_file_with_default_app(full_path):
                    self.show_error_message("Open Error", f"Cannot open file: {full_path}", "No suitable application found")
            except Exception as e:
                self.show_error_message("Open Error", f"Cannot open file: {full_path}", str(e))

    def icon_right_clicked(self, full_path, global_pos):
        """Handle right-click on an icon"""
        # Get the current tab and its icon container
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        # Ensure the clicked item is selected (use main window's selected_items)
        if full_path not in self.selected_items:
            self.selected_items = [full_path]
            current_tab.icon_container.clear_selection()
            current_tab.icon_container.add_to_selection_by_path(full_path)
            # Notify main window of selection change
            self.on_selection_changed(self.selected_items)
        
        context_menu = QMenu(self)
        
        # Single item actions
        if len(self.selected_items) == 1:
            item_path = self.selected_items[0]
            is_dir = os.path.isdir(item_path)
            if is_dir:
                open_action = context_menu.addAction("Open")
                open_action.triggered.connect(lambda: current_tab.navigate_to(item_path))
                # Add 'Open in New Tab' for folders
                open_new_tab_action = context_menu.addAction("Open in New Tab")
                open_new_tab_action.triggered.connect(lambda: self.tab_manager.new_tab(item_path))
            else:
                open_action = context_menu.addAction("Open")
                open_action.triggered.connect(lambda: current_tab.handle_double_click(item_path))
                # Add 'Open with...' option for files
                open_with_action = context_menu.addAction("Open with...")
                open_with_action.triggered.connect(lambda: self.open_with_dialog(item_path))
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
            
            # Archive operations for single items
            if ArchiveManager.is_archive(self.selected_items[0]):
                context_menu.addSeparator()
                
                # Browse archive contents
                browse_action = context_menu.addAction("Browse Archive")
                browse_action.triggered.connect(lambda: self.browse_archive_contents(self.selected_items[0]))
                
                # Extract archive
                extract_action = context_menu.addAction("Extract Archive...")
                extract_action.triggered.connect(lambda: self.extract_archive_dialog(self.selected_items[0]))
        
        # Archive operations for multiple selections
        if len(self.selected_items) > 0:
            context_menu.addSeparator()
            create_archive_action = context_menu.addAction("Create Archive...")
            create_archive_action.triggered.connect(lambda: self.create_archive_dialog(self.selected_items))
        
        context_menu.addSeparator()
        
        delete_action = context_menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_multiple_files(self.selected_items))
        delete_action.setEnabled(len(self.selected_items) > 0)
        
        # Always add "Open Terminal Here" option
        context_menu.addSeparator()
        terminal_action = context_menu.addAction("Open Terminal Here")
        
        # Add Properties option
        if len(self.selected_items) == 1:
            properties_action = context_menu.addAction("Properties")
            properties_action.triggered.connect(lambda: self.show_properties(self.selected_items[0]))
        
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
            terminal_action.triggered.connect(lambda: self.open_terminal_here(current_tab.current_folder))

        # Use popup instead of exec_ so the menu is non-blocking and clicks outside
        # the application are still received while the menu is visible.
        context_menu.popup(global_pos)

    def open_with_dialog(self, file_path):
        """Show a custom dialog to select an application to open the file with, then launch it."""
        dlg = OpenWithDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            app_path = dlg.get_app_path()
            if app_path:
                try:
                    import subprocess
                    import sys
                    import os
                    ext = os.path.splitext(app_path)[1].lower()
                    if sys.platform.startswith('win'):
                        # Windows: pass exe and file path
                        subprocess.Popen([app_path, file_path], shell=False)
                    elif sys.platform == 'darwin':
                        # macOS: if .app bundle, use 'open -a', else run directly
                        if app_path.endswith('.app'):
                            subprocess.Popen(['open', '-a', app_path, file_path])
                        else:
                            subprocess.Popen([app_path, file_path])
                    else:
                        # Linux/Unix: handle .desktop files with gtk-launch if possible
                        if ext == '.desktop':
                            # Try to extract the desktop file name and use gtk-launch
                            desktop_file = os.path.basename(app_path)
                            try:
                                subprocess.Popen(['gtk-launch', desktop_file, file_path])
                            except Exception:
                                subprocess.Popen([app_path, file_path])
                        else:
                            subprocess.Popen([app_path, file_path])
                except Exception as e:
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Open with... Error", f"Could not open file with selected application:\n{str(e)}")

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
                # Refresh the current tab
                current_tab = self.tab_manager.get_current_tab()
                if current_tab:
                    current_tab.refresh_current_view()
                
            except Exception as e:
                self.show_error_message("Rename Error", f"Could not rename: {old_name}", str(e))

    def show_properties(self, file_path):
        """Show properties dialog for a file or folder"""
        try:
            properties_dialog = PropertiesDialog(file_path, self)
            properties_dialog.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Properties Error", f"Could not show properties: {str(e)}")

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
    
    def browse_archive_contents(self, archive_path):
        """Browse the contents of an archive file"""
        try:
            dialog = ArchiveBrowserDialog(archive_path, self)
            result = dialog.exec_()
            
            if result == QDialog.Accepted:
                selected_items = dialog.get_selected_items()
                if selected_items:
                    # Ask where to extract using built-in dialog
                    pass
                    dir_dialog = DirectorySelectionDialog(
                        "Select Extract Location",
                        os.path.dirname(archive_path),
                        self
                    )
                    if dir_dialog.exec_() == QDialog.Accepted:
                        extract_dir = dir_dialog.get_selected_directory()
                        if extract_dir:
                            self.extract_archive_items(archive_path, extract_dir, selected_items)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to browse archive: {str(e)}")
    
    def extract_archive_dialog(self, archive_path):
        """Show dialog to extract an archive"""
        try:
            # Ask where to extract using built-in dialog
            default_extract_dir = os.path.dirname(archive_path)
            pass
            dir_dialog = DirectorySelectionDialog(
                "Select Extract Location",
                default_extract_dir,
                self
            )
            
            if dir_dialog.exec_() == QDialog.Accepted:
                extract_dir = dir_dialog.get_selected_directory()
                if extract_dir:
                    self.extract_archive_with_progress(archive_path, extract_dir)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to extract archive: {str(e)}")
    
    def extract_archive_with_progress(self, archive_path, extract_dir):
        """Extract archive with progress dialog"""
        progress_dialog = QProgressDialog("Extracting archive...", "Cancel", 0, 100, self)
        progress_dialog.setWindowTitle("Extracting")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        def update_progress(current, total):
            if progress_dialog.wasCanceled():
                return False
            
            progress = int((current / total) * 100) if total > 0 else 0
            progress_dialog.setValue(progress)
            progress_dialog.setLabelText(f"Extracting... {current}/{total} files")
            QApplication.processEvents()
            return True
        
        try:
            res = ArchiveManager.extract_archive(
                archive_path,
                extract_dir,
                progress_callback=update_progress
            )

            progress_dialog.close()

            if res is None:
                QMessageBox.critical(self, "Error", "Extraction failed: internal error (no response from extractor)")
                return

            # Expect a (success:boolean, message:str) tuple
            if isinstance(res, tuple) and len(res) == 2:
                success, message = res
            else:
                QMessageBox.critical(self, "Error", f"Extraction failed: unexpected return from extractor: {res}")
                return

            if success:
                QMessageBox.information(self, "Success", message)
                # Refresh any open tab whose folder is the extract destination
                try:
                    norm_extract = os.path.normcase(os.path.abspath(extract_dir))
                    tm = getattr(self, 'tab_manager', None)
                    refreshed_any = False
                    if tm is not None:
                        # If the tab manager exposes a list of tabs, iterate it
                        tabs = getattr(tm, 'tabs', None)
                        if tabs:
                            for t in tabs:
                                try:
                                    tab_folder = getattr(t, 'current_folder', None)
                                    if not tab_folder:
                                        continue
                                    norm_tab = os.path.normcase(os.path.abspath(tab_folder))
                                    # If extract dir equals tab folder or is inside tab folder, refresh that tab
                                    if norm_extract == norm_tab or norm_extract.startswith(norm_tab + os.path.sep):
                                        try:
                                            if hasattr(t, 'refresh_current_view'):
                                                t.refresh_current_view()
                                            if hasattr(t, 'refresh_thumbnail_view'):
                                                t.refresh_thumbnail_view()
                                            refreshed_any = True
                                        except Exception:
                                            pass
                                except Exception:
                                    # Skip problematic tab entries rather than aborting the refresh loop
                                    pass
                        else:
                            # Fallback: only refresh current tab if it matches
                            try:
                                ct = tm.get_current_tab()
                                if ct:
                                    tab_folder = getattr(ct, 'current_folder', None)
                                    if tab_folder:
                                        norm_tab = os.path.normcase(os.path.abspath(tab_folder))
                                        if norm_extract == norm_tab or norm_extract.startswith(norm_tab + os.path.sep):
                                            try:
                                                ct.refresh_current_view()
                                            except Exception:
                                                pass
                                            refreshed_any = True
                            except Exception:
                                pass
                    # As a last resort, refresh the visible/current tab
                    if not refreshed_any:
                        try:
                            current_tab = getattr(self.tab_manager, 'get_current_tab') and self.tab_manager.get_current_tab()
                            if current_tab and hasattr(current_tab, 'refresh_current_view'):
                                current_tab.refresh_current_view()
                        except Exception:
                            pass
                except Exception:
                    # If any unexpected error occurs while deciding which tabs to refresh,
                    # swallow it to avoid crashing the extraction flow.
                    pass
            else:
                QMessageBox.warning(self, "Error", message)
        
        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self, "Error", f"Extraction failed: {str(e)}")
    
    def extract_archive_items(self, archive_path, extract_dir, selected_items):
        """Extract specific items from archive (placeholder for now)"""
        # For now, just extract the entire archive
        # TODO: Implement selective extraction
        self.extract_archive_with_progress(archive_path, extract_dir)
    
    def create_archive_dialog(self, source_paths):
        """Show dialog to create an archive from selected files/folders"""
        try:
            # Ask for output location and name
            suggested_name = "archive.zip"
            if len(source_paths) == 1:
                base_name = os.path.basename(source_paths[0])
                suggested_name = f"{base_name}.zip"
            
            current_tab = self.tab_manager.get_current_tab()
            default_dir = current_tab.current_folder if current_tab else os.path.expanduser("~")
            
            archive_path, _ = QFileDialog.getSaveFileName(
                self,
                "Create Archive",
                os.path.join(default_dir, suggested_name),
                "ZIP Archives (*.zip);;TAR Archives (*.tar);;Gzipped TAR (*.tar.gz)"
            )
            
            if archive_path:
                self.create_archive_with_progress(source_paths, archive_path)
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create archive: {str(e)}")
    
    def create_archive_with_progress(self, source_paths, archive_path):
        """Create archive with progress dialog"""
        progress_dialog = QProgressDialog("Creating archive...", "Cancel", 0, 100, self)
        progress_dialog.setWindowTitle("Creating Archive")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        def update_progress(current, total):
            if progress_dialog.wasCanceled():
                return False
            
            progress = int((current / total) * 100) if total > 0 else 0
            progress_dialog.setValue(progress)
            progress_dialog.setLabelText(f"Adding files... {current}/{total}")
            QApplication.processEvents()
            return True
        
        try:
            success, message = ArchiveManager.create_zip_archive(
                source_paths,
                archive_path,
                progress_callback=update_progress
            )
            
            progress_dialog.close()
            
            if success:
                QMessageBox.information(self, "Success", message)
                # Refresh current view to show the new archive
                current_tab = self.tab_manager.get_current_tab()
                if current_tab:
                    current_tab.refresh_current_view()
            else:
                QMessageBox.warning(self, "Error", message)
        
        except Exception as e:
            progress_dialog.close()
            QMessageBox.critical(self, "Error", f"Archive creation failed: {str(e)}")
    
    def create_archive_from_selection(self):
        """Create archive from current selection (menu action)"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            QMessageBox.warning(self, "Warning", "No active tab")
            return
            
        selected_items = getattr(self, 'selected_items', [])
        if not selected_items:
            QMessageBox.information(self, "Information", "No files or folders selected")
            return
            
        self.create_archive_dialog(selected_items)
    
    def extract_archive_from_selection(self):
        """Extract archive from current selection (menu action)"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            QMessageBox.warning(self, "Warning", "No active tab")
            return
            
        selected_items = getattr(self, 'selected_items', [])
        if len(selected_items) != 1:
            QMessageBox.information(self, "Information", "Please select exactly one archive file")
            return
            
        archive_path = selected_items[0]
        if not ArchiveManager.is_archive(archive_path):
            QMessageBox.warning(self, "Warning", "Selected file is not a supported archive")
            return
            
        self.extract_archive_dialog(archive_path)
    
    def browse_archive_from_selection(self):
        """Browse archive from current selection (menu action)"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            QMessageBox.warning(self, "Warning", "No active tab")
            return
            
        selected_items = getattr(self, 'selected_items', [])
        if len(selected_items) != 1:
            QMessageBox.information(self, "Information", "Please select exactly one archive file")
            return
            
        archive_path = selected_items[0]
        if not ArchiveManager.is_archive(archive_path):
            QMessageBox.warning(self, "Warning", "Selected file is not a supported archive")
            return
            
        self.browse_archive_contents(archive_path)

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
        try:
            if self.clipboard_manager.get_current_operation()[0]:  # Has something to paste
                paste_action = context_menu.addAction("Paste")
                paste_action.triggered.connect(self.paste_action_triggered)
        except Exception:
            pass

        context_menu.addSeparator()

        # Open Terminal Here action
        terminal_action = context_menu.addAction("Open Terminal Here")
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            terminal_action.triggered.connect(lambda: self.open_terminal_here(current_tab.current_folder))

        # Use popup instead of exec_ so the menu is non-blocking and clicks outside
        # the application are still received while the menu is visible.
        context_menu.popup(global_pos)

    def create_new_file(self):
        """Create a new file in current directory"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            try:
                file_path = os.path.join(current_tab.current_folder, name)
                if os.path.exists(file_path):
                    QMessageBox.warning(self, "Error", "A file with that name already exists.")
                    return
                    
                # Create empty file
                with open(file_path, 'w') as f:
                    pass
                    
                self.refresh_current_view()
            except Exception as e:
                self.show_error_message("Error", f"Could not create file: {str(e)}")

    def create_new_folder(self):
        """Create a new folder in current directory"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                folder_path = os.path.join(current_tab.current_folder, name)
                if os.path.exists(folder_path):
                    QMessageBox.warning(self, "Error", "A folder with that name already exists.")
                    return
                    
                os.makedirs(folder_path)
                self.refresh_current_view()
            except Exception as e:
                self.show_error_message("Error", f"Could not create folder: {str(e)}")

    def paste_to(self, dest_path):
        """Paste clipboard contents to destination"""
        operation, paths = self.clipboard_manager.get_current_operation()

        if not operation or not paths:
            return

        # Normalize 'cut' to 'move' for AsyncFileOperation
        op = 'move' if operation == 'cut' else operation

        # Always use the async operation for consistency
        self.paste_multiple_items(paths, dest_path, op)

        # Clear clipboard after move operation
        if operation == "cut":
            self.clipboard_manager.clear_current()

        # Refresh view - this will be done by the async operation callback

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
                fast_move(src_path, final_dest)
                self.statusBar().showMessage(f"Moved: {src_name}", 3000)
                
        except Exception as e:
            self.show_error_message("Paste Error", f"Could not paste: {src_name}", str(e))

    def paste_multiple_items(self, src_paths, dest_path, operation):
        """Paste multiple items with enhanced async progress"""
        try:
            # Use the new async file operation system for better performance
            operation_name = "Copy" if operation == "copy" else "Move"
            async_operation = AsyncFileOperation(src_paths, dest_path, operation)
            
            # Create enhanced progress dialog
            progress_dialog = EnhancedProgressDialog(f"{operation_name} Operation", len(src_paths), self)
            worker = AsyncFileOperationWorker(async_operation)
            
            # Connect the operation and worker to the progress dialog for pause/cancel functionality
            progress_dialog.operation = async_operation
            progress_dialog.operation_worker = worker
            
            # Connect all progress signals
            worker.progress.connect(progress_dialog.update_progress)
            worker.fileProgress.connect(progress_dialog.update_file_progress)
            worker.byteProgress.connect(progress_dialog.update_byte_progress)
            worker.speedUpdate.connect(progress_dialog.update_speed)
            worker.etaUpdate.connect(progress_dialog.update_eta)
            worker.statusChanged.connect(progress_dialog.update_status)
            
            # Handle completion and errors
            def on_finished(success, message, stats):
                try:
                    progress_dialog.close()  # Use close() instead of accept()
                    current_tab = self.tab_manager.get_current_tab()
                    if current_tab:
                        current_tab.refresh_current_view()
                    status_msg = f"{operation_name} operation completed" if success else f"{operation_name} operation failed"
                    self.statusBar().showMessage(status_msg, 3000)
                except Exception as e:
                    print(f"Error in on_finished: {e}")
            
            def on_error(error_message):
                try:
                    QMessageBox.warning(self, "Operation Error", f"{operation_name} operation failed:\n{error_message}")
                    progress_dialog.close()  # Use close() instead of accept()
                except Exception as e:
                    print(f"Error in on_error: {e}")
            
            worker.finished.connect(on_finished)
            worker.error.connect(on_error)
            
            # Start the operation and show non-modal dialog
            print(f"Starting {operation_name} operation with {len(src_paths)} items")
            worker.start()
            progress_dialog.show()  # Use show() instead of exec_() to avoid blocking
            
            # Ensure Qt events are processed to keep UI responsive
            QApplication.processEvents()
            print(f"Worker thread started: {worker.isRunning()}")
            
        except Exception as e:
            QMessageBox.critical(self, "Paste Error", f"Failed to start {operation_name.lower()} operation:\n{str(e)}")
            print(f"Exception in paste_multiple_items: {e}")
            import traceback
            traceback.print_exc()

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
                
                self.refresh_current_view()
                self.statusBar().showMessage(f"Deleted: {name}", 3000)
                
        except Exception as e:
            self.show_error_message("Delete Error", f"Could not delete: {os.path.basename(path)}", str(e))

    def delete_multiple_files(self, paths):
        """Delete multiple files/folders with confirmation and enhanced progress"""
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
        
        # Use async operation for better progress tracking on large operations
        if count > 10:  # Use async for larger operations
            async_operation = AsyncFileOperation(paths, None, "delete")
            progress_dialog = EnhancedProgressDialog("Delete Operation", count, self)
            worker = AsyncFileOperationWorker(async_operation)
            
            # Connect progress signals
            worker.progress.connect(progress_dialog.update_progress)
            worker.fileProgress.connect(progress_dialog.update_file_progress)
            worker.statusChanged.connect(progress_dialog.update_status)
            
            def on_finished(success, message, stats):
                progress_dialog.accept()
                self.refresh_current_view()
                status_msg = f"Deleted {count} items" if success else f"Delete operation failed"
                self.statusBar().showMessage(status_msg, 3000)
            
            def on_error(error_message):
                QMessageBox.warning(self, "Delete Error", f"Delete operation failed:\n{error_message}")
                progress_dialog.accept()
                self.refresh_current_view()
            
            worker.finished.connect(on_finished)
            worker.error.connect(on_error)
            
            worker.start()
            progress_dialog.exec_()
        else:
            # For small operations, use direct deletion
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
            self.refresh_current_view()
            
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
                    # Navigate to directory in current tab
                    current_tab = self.tab_manager.get_current_tab()
                    if current_tab:
                        current_tab.navigate_to_path(file_path)
                elif file_path and ArchiveManager.is_archive(file_path):
                    # For archive files, show browse dialog instead of opening externally
                    self.browse_archive_contents(file_path)
                elif file_path:
                    self.icon_double_clicked(file_path)
        except Exception as e:
            self.show_error_message("Navigation Error", "Could not navigate to selected item", str(e))

    def cut_action_triggered(self):
        """Handle cut action (deduplicated, robust version)"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation("cut", self.selected_items.copy())
            self.clipboard_manager.add_to_history("cut", self.selected_items.copy())
            self.statusBar().showMessage(f"Cut {len(self.selected_items)} items", 2000)

    def copy_action_triggered(self):
        """Handle copy action (deduplicated, robust version)"""
        if self.selected_items:
            self.clipboard_manager.set_current_operation("copy", self.selected_items.copy())
            self.clipboard_manager.add_to_history("copy", self.selected_items.copy())
            self.statusBar().showMessage(f"Copied {len(self.selected_items)} items", 2000)

    # These are duplicate methods from earlier - removing since they're already defined above
    # def on_double_click(self, index):
    #     """Handle double-click events from tree or other views"""
    #     try:
    #         if hasattr(index, 'data'):
    #             file_path = index.data(Qt.UserRole)
    #             if file_path and os.path.isdir(file_path):
    #                 self.update_thumbnail_view(file_path)
    #             elif file_path:
    #                 self.icon_double_clicked(file_path)
    #     except Exception as e:
    #         self.show_error_message("Navigation Error", "Could not navigate to selected item", str(e))

    def refresh_current_view(self):
        """Refresh the current view"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.refresh_current_view()

    def deselect_icons(self):
        """Deselect all icons"""
        self.selected_items = []
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container and hasattr(icon_container, 'clear_selection'):
                icon_container.clear_selection()
        self.on_selection_changed([])

    def select_all_items(self):
        """Select all items in current view"""
        try:
            current_tab = self.tab_manager.get_current_tab()
            if not current_tab:
                return
                
            all_items = []
            for item_name in os.listdir(current_tab.current_folder):
                if not item_name.startswith('.') or getattr(self, 'show_hidden', False):
                    all_items.append(os.path.join(current_tab.current_folder, item_name))
            
            self.selected_items = all_items
            # Update UI selection state
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container:
                if hasattr(icon_container, 'clear_selection'):
                    icon_container.clear_selection()
                if hasattr(icon_container, 'add_to_selection_by_path'):
                    for path in all_items:
                        icon_container.add_to_selection_by_path(path)
            
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

    def show_properties_selected_item(self):
        """Show properties for the selected item (only works with single selection)"""
        if len(self.selected_items) == 1:
            self.show_properties(self.selected_items[0])
        elif len(self.selected_items) > 1:
            QMessageBox.information(self, "Multiple Selection", "Properties can only be shown for a single item.")
        else:
            QMessageBox.information(self, "No Selection", "Please select an item to view properties.")

    def set_thumbnail_size(self, size):
        """Set the thumbnail size and refresh the view"""
        self.thumbnail_size = size
        
        # Update checkmarks
        self.update_thumbnail_menu_checkmarks()
        
        # Save the setting
        current_path = getattr(self, 'current_folder', os.path.expanduser("~"))
        self.save_last_dir(current_path)
        
        # Refresh all tabs with new thumbnail size
        for tab in self.tab_manager.tabs:
            tab.refresh_current_view()
            
        # If we're in auto-width mode, trigger relayout to recalculate with new thumbnail size
        if self.icons_wide == 0:  # Auto-width mode
            for tab in self.tab_manager.tabs:
                if hasattr(tab, 'icon_container') and tab.icon_container:
                    # Use a timer to ensure the refresh completes first
                    if not hasattr(tab, '_thumbnail_size_timer'):
                        from PyQt5.QtCore import QTimer
                        tab._thumbnail_size_timer = QTimer()
                        tab._thumbnail_size_timer.setSingleShot(True)
                        tab._thumbnail_size_timer.timeout.connect(lambda t=tab: t.get_icon_container_safely() and t.get_icon_container_safely().relayout_icons())
                    
                    tab._thumbnail_size_timer.stop()
                    tab._thumbnail_size_timer.start(200)  # Delay to let refresh complete first

    def update_thumbnail_menu_checkmarks(self):
        """Update menu checkmarks based on current thumbnail size"""
        self.small_thumb_action.setChecked(self.thumbnail_size == 48)
        self.medium_thumb_action.setChecked(self.thumbnail_size == 64)
        self.large_thumb_action.setChecked(self.thumbnail_size == 96)
        self.xlarge_thumb_action.setChecked(self.thumbnail_size == 128)
        # New sizes
        try:
            self.thumb_80_action.setChecked(self.thumbnail_size == 80)
            self.thumb_160_action.setChecked(self.thumbnail_size == 160)
            self.thumb_192_action.setChecked(self.thumbnail_size == 192)
            self.thumb_224_action.setChecked(self.thumbnail_size == 224)
            self.thumb_256_action.setChecked(self.thumbnail_size == 256)
            self.thumb_384_action.setChecked(self.thumbnail_size == 384)
            self.thumb_512_action.setChecked(self.thumbnail_size == 512)
            self.thumb_640_action.setChecked(self.thumbnail_size == 640)
            self.thumb_768_action.setChecked(self.thumbnail_size == 768)
        except AttributeError:
            # In case actions don't exist (older version), ignore
            pass

    def set_icons_wide(self, width):
        """Set the number of icons wide and refresh the view"""
        self.icons_wide = width
        
        # Update checkmarks
        self.update_layout_menu_checkmarks()
        
        # Save the setting
        current_path = getattr(self, 'current_folder', os.path.expanduser("~"))
        self.save_last_dir(current_path)
        
        # Refresh all tabs with new layout setting
        for tab in self.tab_manager.tabs:
            tab.refresh_current_view()

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
        # On macOS, try to detect system theme preference
        if PlatformUtils.is_macos():
            try:
                # Check if system is in dark mode
                result = subprocess.run([
                    'defaults', 'read', '-g', 'AppleInterfaceStyle'
                ], capture_output=True, text=True)
                
                if result.returncode == 0 and 'Dark' in result.stdout:
                    # System is in dark mode, user might want to override
                    pass  # Continue with manual toggle
                else:
                    # System is in light mode
                    pass  # Continue with manual toggle
            except Exception:
                # If detection fails, just continue with manual toggle
                pass
        
        # Toggle and preserve/restore last light color theme when switching modes
        prev_dark = bool(getattr(self, 'dark_mode', False))
        self.dark_mode = not prev_dark

        try:
            settings = QSettings('garysfm', 'garysfm')
            # If switching FROM light TO dark, save the current colored theme
            if not prev_dark and self.dark_mode:
                try:
                    last_theme = getattr(self, 'color_theme', None)
                    if last_theme:
                        settings.setValue('last_light_theme', str(last_theme))
                except Exception:
                    pass
            # If switching FROM dark TO light, restore previously saved colored theme
            if prev_dark and not self.dark_mode:
                try:
                    restored = settings.value('last_light_theme', None)
                    # Ensure we have a plain Python string and normalize it
                    try:
                        if restored is None:
                            restored_str = None
                        else:
                            restored_str = str(restored).strip()
                    except Exception:
                        restored_str = None

                    # If restored value looks valid and matches a known theme, apply it
                    if restored_str and hasattr(self, 'COLOR_THEMES') and restored_str in self.COLOR_THEMES:
                        try:
                            self.set_color_theme(restored_str)
                        except Exception:
                            # Fallback: set attribute and reapply
                            self.color_theme = restored_str
                            self.apply_theme()
                            self.refresh_all_themes()
                    else:
                        # Try a looser match: compare case-insensitively to known keys
                        if restored_str and hasattr(self, 'COLOR_THEMES'):
                            lowered = restored_str.lower()
                            for key in self.COLOR_THEMES.keys():
                                if key.lower() == lowered:
                                    try:
                                        self.set_color_theme(key)
                                    except Exception:
                                        self.color_theme = key
                                        self.apply_theme()
                                        self.refresh_all_themes()
                                    break
                except Exception:
                    pass
            # Persist dark mode choice
            settings.setValue('dark_mode', bool(self.dark_mode))
        except Exception:
            pass
        self.apply_dark_mode()
        self.update_dark_mode_checkmark()
        
        # Save the setting immediately - use current tab's folder if available
        try:
            current_tab = self.tab_manager.get_current_tab()
            if current_tab and hasattr(current_tab, 'current_folder'):
                folder_path = current_tab.current_folder
            else:
                # Fallback: use home directory
                folder_path = os.path.expanduser("~")
            
            self.save_last_dir(folder_path)
        except Exception as e:
            print(f"Error saving settings during theme switch: {e}")
            # Continue with theme update even if save fails
        
        # Update all UI components instantly
        self.refresh_all_themes()

    def apply_dark_mode(self):
        """Apply dark mode styling"""
        # Centralized theme application: call the unified applier which
        # handles both dark mode and named light themes. This prevents
        # inconsistent clearing of a light color theme when toggling modes.
        try:
            self.apply_theme()
        except Exception:
            try:
                self.setStyleSheet("")
            except Exception:
                pass
            
    def set_color_theme(self, name):
        """Set a named light color theme, persist it, and reapply UI styling."""
        try:
            if not hasattr(self, 'COLOR_THEMES') or name not in self.COLOR_THEMES:
                return
            self.color_theme = name
            # Persist selection
            try:
                settings = QSettings('garysfm', 'garysfm')
                settings.setValue('color_theme', str(name))
            except Exception:
                pass
            # Update theme menu checkmarks if present
            try:
                for n, act in getattr(self, '_theme_actions', {}).items():
                    try:
                        act.setChecked(n == name)
                    except Exception:
                        pass
            except Exception:
                pass

            # Reapply theme and refresh UI
            try:
                self.apply_theme()
                self.refresh_all_themes()
            except Exception:
                pass
        except Exception:
            pass

    def refresh_all_themes(self):
        """Update all UI components with current theme"""
        # Update preview pane background
        if hasattr(self, 'preview_pane') and self.preview_pane:
            self.update_preview_pane_theme()
            
        # Update icon container background
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container:
                self.update_icon_container_theme(icon_container)
            
        # Update tab manager theme
        if hasattr(self, 'tab_manager') and self.tab_manager:
            self.update_tab_manager_theme()
            
        # Update tree view theme
        if hasattr(self, 'tree_view') and self.tree_view:
            self.update_tree_view_theme()
            
        # Update breadcrumb theme
        if hasattr(self, 'breadcrumb') and self.breadcrumb:
            self.update_breadcrumb_theme()
            
        # Update all existing icons
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
            if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                icon_container = current_tab.get_icon_container_safely()
            
            if icon_container:
                for i in range(icon_container.layout().count()):
                    item = icon_container.layout().itemAt(i)
                    if item and item.widget():
                        widget = item.widget()
                        if hasattr(widget, 'update_style_for_theme'):
                            widget.update_style_for_theme(self.dark_mode)
                        
        # Force repaint
        self.repaint()
        
        # Update theme checkmarks to reflect current mode
        self.update_theme_checkmarks()
        
    def update_theme_checkmarks(self):
        """Update theme menu checkmarks based on current theme mode and selection"""
        try:
            current_theme = getattr(self, 'color_theme', None)
            strong_mode = getattr(self, 'strong_mode', False)
            subdued_mode = getattr(self, 'subdued_mode', False)
            
            # Clear all checkmarks first
            for name, action in getattr(self, '_theme_actions', {}).items():
                try:
                    action.setChecked(False)
                except Exception:
                    pass
            
            # Set checkmark for the current theme
            if current_theme and current_theme in getattr(self, '_theme_actions', {}):
                try:
                    self._theme_actions[current_theme].setChecked(True)
                except Exception:
                    pass
                    
        except Exception:
            pass
        
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
        
    # Sorting Methods
    def set_sort_by(self, sort_by):
        """Set sort criteria for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.sort_by = sort_by
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def set_sort_order(self, sort_order):
        """Set sort order for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.sort_order = sort_order
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def toggle_directories_first(self):
        """Toggle directories first sorting for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.directories_first = not current_tab.directories_first
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def toggle_case_sensitive(self):
        """Toggle case sensitive sorting for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.case_sensitive = not current_tab.case_sensitive
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def toggle_group_by_type(self):
        """Toggle group by type sorting for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.group_by_type = not current_tab.group_by_type
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def toggle_natural_sort(self):
        """Toggle natural sort for current tab"""
        current_tab = self.tab_manager.get_current_tab()
        if current_tab:
            current_tab.natural_sort = not current_tab.natural_sort
            self.update_sort_menu_checkmarks()
            self.save_tab_sort_settings(current_tab)
            current_tab.refresh_current_view()

    def update_sort_menu_checkmarks(self):
        """Update sort menu checkmarks based on current tab settings"""
        current_tab = self.tab_manager.get_current_tab()
        if not current_tab:
            return
            
        # Sort by checkmarks
        self.sort_by_name_action.setChecked(current_tab.sort_by == "name")
        self.sort_by_size_action.setChecked(current_tab.sort_by == "size")
        self.sort_by_date_action.setChecked(current_tab.sort_by == "date")
        self.sort_by_type_action.setChecked(current_tab.sort_by == "type")
        self.sort_by_extension_action.setChecked(current_tab.sort_by == "extension")
        
        # Sort order checkmarks
        self.sort_ascending_action.setChecked(current_tab.sort_order == "ascending")
        self.sort_descending_action.setChecked(current_tab.sort_order == "descending")
        
        # Sort options checkmarks
        self.directories_first_action.setChecked(current_tab.directories_first)
        self.case_sensitive_action.setChecked(current_tab.case_sensitive)
        self.group_by_type_action.setChecked(current_tab.group_by_type)
        self.natural_sort_action.setChecked(current_tab.natural_sort)

    def save_all_tab_sort_settings(self):
        """Save sorting settings for all open tabs"""
        if hasattr(self, 'tab_manager') and self.tab_manager:
            for tab in self.tab_manager.tabs:
                if tab:
                    self.save_tab_sort_settings(tab)

    def migrate_tab_sort_settings(self):
        """Migrate old hash-based keys to new deterministic MD5 keys"""
        try:
            if not os.path.exists(self.SETTINGS_FILE):
                return
                
            with open(self.SETTINGS_FILE, "r") as f:
                settings = json.load(f)
                
            if "tab_sort_settings" not in settings:
                return
                
            old_settings = settings["tab_sort_settings"]
            migrated_count = 0
            
            # Create new settings with deterministic keys
            # Iterate over a static list to avoid mutating the dict during iteration
            for old_key, sort_data in list(old_settings.items()):
                if old_key.startswith("tab_sort_") and "path" in sort_data:
                    path = sort_data["path"]
                    new_key = self.get_tab_key(path)
                    
                    # If the new key doesn't exist, migrate the old one
                    if new_key not in settings.get("tab_sort_settings", {}):
                        settings["tab_sort_settings"][new_key] = sort_data.copy()
                        migrated_count += 1
            
            if migrated_count > 0:
                # Save the updated settings
                with open(self.SETTINGS_FILE, "w") as f:
                    json.dump(settings, f, indent=2)
                
        except Exception as e:
            print(f"Error migrating tab sort settings: {e}")

    def get_tab_key(self, folder_path):
        """Generate a deterministic key for tab sort settings"""
        # Normalize the path to be consistent across platforms and runs
        import hashlib
        normalized_path = os.path.normpath(folder_path).replace('\\', '/')
        # Use MD5 hash for deterministic results across Python runs  
        path_hash = hashlib.md5(normalized_path.encode('utf-8')).hexdigest()
        return f"tab_sort_{path_hash}"

    def save_tab_sort_settings(self, tab):
        """Save sorting settings for a specific tab"""
        if not tab:
            return
            
        if not hasattr(tab, 'current_folder') or not tab.current_folder:
            return
            
        # Create tab-specific settings key based on path
        tab_key = self.get_tab_key(tab.current_folder)
        
        # Get current settings
        settings = {}
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
        except Exception as e:
            settings = {}
            
        # Add/update tab sort settings
        if "tab_sort_settings" not in settings:
            settings["tab_sort_settings"] = {}
            
        settings["tab_sort_settings"][tab_key] = {
            "sort_by": tab.sort_by,
            "sort_order": tab.sort_order,
            "directories_first": tab.directories_first,
            "case_sensitive": tab.case_sensitive,
            "group_by_type": tab.group_by_type,
            "natural_sort": tab.natural_sort,
            "path": tab.current_folder
        }
        
        # Save settings
        try:
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving tab sort settings: {e}")

    def load_tab_sort_settings(self, tab):
        """Load sorting settings for a specific tab"""
        if not tab:
            return
            
        tab_key = self.get_tab_key(tab.current_folder)
        settings_loaded = False
        
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
                    
                if "tab_sort_settings" in settings and tab_key in settings["tab_sort_settings"]:
                    sort_settings = settings["tab_sort_settings"][tab_key]
                    
                    tab.sort_by = sort_settings.get("sort_by", "name")
                    tab.sort_order = sort_settings.get("sort_order", "ascending")
                    tab.directories_first = sort_settings.get("directories_first", True)
                    tab.case_sensitive = sort_settings.get("case_sensitive", False)
                    tab.group_by_type = sort_settings.get("group_by_type", False)
                    tab.natural_sort = sort_settings.get("natural_sort", True)
                    
                    settings_loaded = True
                    
                    # Update menu checkmarks
                    self.update_sort_menu_checkmarks()
        except Exception as e:
            print(f"Error loading tab sort settings: {e}")
            
        # Refresh the view to apply the loaded settings
        if settings_loaded:
            # Only refresh if the view_stack exists (UI is set up)
            if hasattr(tab, 'view_stack'):
                tab.refresh_current_view()
        
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
        
    def update_tab_manager_theme(self):
        """Update tab manager theme for current mode"""
        if hasattr(self, 'tab_manager') and self.tab_manager:
            if self.dark_mode:
                tab_style = """
                    QTabWidget::pane {
                        background-color: #3c3c3c;
                        color: #ffffff;
                        border: 1px solid #555;
                    }
                    QTabBar {
                        background-color: #2b2b2b;
                    }
                    QTabBar::tab {
                        background-color: #404040;
                        color: #ffffff;
                        padding: 8px 16px;
                        margin-right: 2px;
                        margin-bottom: 2px;
                        border: 1px solid #555;
                        border-top-left-radius: 4px;
                        border-top-right-radius: 4px;
                        min-width: 80px;
                    }
                    QTabBar::tab:hover {
                        background-color: #4a4a4a;
                        color: #ffffff;
                    }
                    QTabBar::tab:selected {
                        background-color: #0078d4;
                        color: #ffffff;
                        border-bottom: none;
                        font-weight: bold;
                    }
                    QTabBar::close-button {
                        background-color: transparent;
                        border: none;
                        margin: 2px;
                    }
                    QTabBar::close-button:hover {
                        background-color: #ff4444;
                        border-radius: 2px;
                    }
                    QPushButton {
                        background-color: #404040;
                        color: #ffffff;
                        border: 1px solid #555;
                        border-radius: 3px;
                        padding: 4px 8px;
                    }
                    QPushButton:hover {
                        background-color: #4a4a4a;
                    }
                    QPushButton:pressed {
                        background-color: #0078d4;
                    }
                """
            else:
                # Light mode - use default styling
                tab_style = """
                    QTabBar::tab {
                        padding: 8px 16px;
                        margin-right: 2px;
                        min-width: 80px;
                    }
                """
            
            self.tab_manager.setStyleSheet(tab_style)
    
    def update_icon_container_theme(self, icon_container=None):
        """Update icon container background for current theme"""
        if not icon_container:
            # Fallback to getting current tab's icon container
            current_tab = self.tab_manager.get_current_tab()
            if current_tab:
                icon_container = getattr(current_tab, 'icon_container', None) if hasattr(current_tab, 'get_icon_container_safely') else None
                if not icon_container and hasattr(current_tab, 'get_icon_container_safely'):
                    icon_container = current_tab.get_icon_container_safely()
        
        if not icon_container:
            return  # No icon container to update
            
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
        
        icon_container.setStyleSheet(style)
        # Also update the scroll area if we can access it through the current tab
        current_tab = self.tab_manager.get_current_tab()
        if current_tab and hasattr(current_tab, 'scroll_area'):
            current_tab.scroll_area.setStyleSheet(style)

    def set_color_theme(self, name):
        """Set a named light color theme and persist selection"""
        try:
            if name not in self.COLOR_THEMES:
                return
            self.color_theme = name
            # Update menu checkmarks
            try:
                for n, a in getattr(self, '_theme_actions', {}).items():
                    a.setChecked(n == name)
            except Exception:
                pass
            # Persist
            try:
                settings = QSettings('garysfm', 'garysfm')
                settings.setValue('color_theme', name)
            except Exception:
                pass
            # Re-apply theme across UI
            self.apply_theme()
            self.refresh_all_themes()
        except Exception:
            pass

    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def apply_theme(self):
        """Apply the current theme (dark or light mode)"""
        # Strong mode takes highest precedence when enabled
        try:
            if getattr(self, 'strong_mode', False):
                # Resolve an appropriate strong palette. Prefer a direct
                # mapping from the selected named theme; otherwise fall back
                # to the mapped value or the first available strong palette.
                theme_name = getattr(self, 'color_theme', None)
                theme_key = None
                if theme_name:
                    # Directly mapped strong theme
                    theme_key = self.STRONG_THEME_MAP.get(theme_name)
                    # If the user mistakenly selected a strong key as color_theme,
                    # allow that too.
                    if not theme_key and theme_name in self.STRONG_COLOR_THEMES:
                        theme_key = theme_name

                if not theme_key:
                    # Choose the first strong theme as a safe fallback
                    try:
                        theme_key = next(iter(self.STRONG_COLOR_THEMES.keys()))
                    except Exception:
                        theme_key = None

                theme = self.STRONG_COLOR_THEMES.get(theme_key) if theme_key else None
                if theme:
                    # Apply the strong theme colors
                    win = theme.get('window_bg', '#111111')
                    panel = theme.get('panel_bg', '#222222')
                    text = theme.get('text', '#ffffff')
                    accent = theme.get('accent', '#ff6600')

                    # If dark mode is enabled, darken the colors further
                    if getattr(self, 'dark_mode', False):
                        # Make backgrounds darker for dark mode
                        from PyQt5.QtGui import QColor
                        win_color = QColor(win)
                        panel_color = QColor(panel)
                        # Darken the background colors by 30%
                        win = win_color.darker(130).name()
                        panel = panel_color.darker(130).name()

                    strong_style = f"""
QWidget, QDialog {{
    background-color: {win};
    color: {text};
}}
QFrame, QGroupBox {{
    background-color: {panel};
    color: {text};
}}
QLabel {{ color: {text}; background-color: transparent; }}
QTextEdit, QPlainTextEdit {{
    background-color: {panel};
    color: {text};
    border: 1px solid {accent};
}}
QLineEdit {{
    background-color: {panel};
    color: {text};
    border: 2px solid {accent};
    padding: 4px;
    border-radius: 3px;
}}
QPushButton {{
    background-color: {accent};
    color: {text};
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {accent};
}}
QMenuBar {{
    background-color: {panel};
    color: {text};
    border-bottom: 2px solid {accent};
}}
QMenuBar::item:selected {{
    background-color: {accent};
    color: {text};
}}
QMenu {{
    background-color: {panel};
    color: {text};
    border: 2px solid {accent};
}}
QMenu::item:selected {{
    background-color: {accent};
    color: {text};
}}
QTabWidget::pane {{
    background-color: {panel};
    color: {text};
    border: 2px solid {accent};
}}
QTabBar::tab {{
    background-color: {win};
    color: {text};
    padding: 8px 16px;
    margin-right: 2px;
    border: 1px solid {accent};
}}
QTabBar::tab:selected {{
    background-color: {accent};
    color: {text};
    font-weight: bold;
}}
QTableWidget, QTreeWidget, QListWidget {{
    background-color: {panel};
    color: {text};
    border: 1px solid {accent};
    alternate-background-color: {win};
}}
QHeaderView::section {{
    background-color: {accent};
    color: {text};
    padding: 4px;
    border: none;
    font-weight: bold;
}}
QScrollBar:vertical {{
    background-color: {panel};
    width: 12px;
    border: 1px solid {accent};
}}
QScrollBar::handle:vertical {{
    background-color: {accent};
    border-radius: 6px;
}}
QScrollBar:horizontal {{
    background-color: {panel};
    height: 12px;
    border: 1px solid {accent};
}}
QScrollBar::handle:horizontal {{
    background-color: {accent};
    border-radius: 6px;
}}
"""
                    self.setStyleSheet(strong_style)
                    return
        except Exception:
            pass

        # Subdued mode takes precedence when enabled (after strong mode)
        try:
            if getattr(self, 'subdued_mode', False):
                # Resolve an appropriate subdued palette. Prefer a direct
                # mapping from the selected named theme; otherwise fall back
                # to the mapped value or the first available subdued palette.
                theme_name = getattr(self, 'color_theme', None)
                theme_key = None
                if theme_name:
                    # Directly mapped subdued theme
                    theme_key = self.SUBDUED_THEME_MAP.get(theme_name)
                    # If the user mistakenly selected a subdued key as color_theme,
                    # allow that too.
                    if not theme_key and theme_name in self.SUBDUED_COLOR_THEMES:
                        theme_key = theme_name

                if not theme_key:
                    # Choose the first subdued theme as a safe fallback
                    try:
                        theme_key = next(iter(self.SUBDUED_COLOR_THEMES.keys()))
                    except Exception:
                        theme_key = None

                theme = self.SUBDUED_COLOR_THEMES.get(theme_key) if theme_key else None
                if theme:
                    wbg = theme.get('window_bg', '#111111')
                    pbg = theme.get('panel_bg', '#1a1a1a')
                    txt = theme.get('text', '#ffffff')
                    acc = theme.get('accent', '#ff4d00')

                    # If dark mode is enabled, darken the colors further
                    if getattr(self, 'dark_mode', False):
                        # Make backgrounds darker for dark mode
                        from PyQt5.QtGui import QColor
                        wbg_color = QColor(wbg)
                        pbg_color = QColor(pbg)
                        # Darken the background colors by 30%
                        wbg = wbg_color.darker(130).name()
                        pbg = pbg_color.darker(130).name()

                    subdued_style = f"""
                    QWidget, QDialog {{
                        background-color: {wbg};
                        color: {txt};
                    }}
                    QFrame, QGroupBox {{
                        background-color: {pbg};
                        color: {txt};
                    }}
                    QPushButton {{
                        background-color: {pbg};
                        color: {txt};
                        border: 1px solid rgba(0,0,0,0.12);
                        border-radius: 3px;
                        padding: 5px 12px;
                    }}
                    QMenu, QMenuBar {{ background-color: {pbg}; color: {txt}; }}
                    QWidget:selected, QTableWidget::item:selected {{ background-color: {acc}; color: #ffffff; }}
                    """
                    self.setStyleSheet(subdued_style)
                    return
        except Exception:
            # If something goes wrong while trying to apply subdued styles,
            # fall through to existing dark/light handling.
            pass
        if self.dark_mode:
            # Prefer a theme-specific dark palette if available so the selected
            # theme feels consistent in dark mode.
            theme_key = getattr(self, 'color_theme', 'Default Light')
            dark_theme = None
            try:
                dark_theme = self.DARK_COLOR_THEMES.get(theme_key)
            except Exception:
                dark_theme = None

            if dark_theme:
                # Build a dark stylesheet using the dark_theme palette
                wbg = dark_theme.get('window_bg', '#2b2b2b')
                pbg = dark_theme.get('panel_bg', '#363636')
                txt = dark_theme.get('recommended_text', dark_theme.get('text', '#ffffff'))
                acc = dark_theme.get('accent', '#3daee9')
                dark_style = f"""
                QMainWindow {{
                    background-color: {wbg};
                    color: {txt};
                }}
                QWidget {{
                    background-color: {pbg};
                    color: {txt};
                }}
                QTreeView, QListView, QTableView {{
                    background-color: {pbg};
                    color: {txt};
                    selection-background-color: {acc};
                    selection-color: {txt};
                }}
                QMenuBar {{
                    background-color: {pbg};
                    color: {txt};
                }}
                QToolBar {{
                    background-color: {pbg};
                    color: {txt};
                }}
                QPushButton {{
                    background-color: {pbg};
                    color: {txt};
                    border: 1px solid rgba(255,255,255,0.06);
                    padding: 5px;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {wbg};
                }}
                QStatusBar {{
                    background-color: {pbg};
                    color: {txt};
                }}
                QMenu {{
                    background-color: {pbg};
                    color: {txt};
                }}
                QScrollArea {{
                    background-color: {wbg};
                    border: none;
                }}
                """
                self.setStyleSheet(dark_style)
            else:
                # Fallback to the generic dark stylesheet
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
                QListView {
                    background-color: #363636;
                    color: #ffffff;
                    border: 1px solid #555555;
                    selection-background-color: #0078d7;
                    selection-color: #ffffff;
                    alternate-background-color: #404040;
                }
                QListView::item {
                    padding: 4px;
                    border: none;
                }
                QListView::item:hover {
                    background-color: #4a4a4a;
                }
                QListView::item:selected {
                    background-color: #0078d7;
                    color: #ffffff;
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
                except Exception:
                    pass
                def _set_theme(checked, name=name):
                    try:
                        if checked:
                            # Selecting a regular named theme switches out of subdued
                            self.subdued_mode = False
                            try:
                                settings = QSettings('garysfm', 'garysfm')
                                settings.setValue('subdued_mode', False)
                            except Exception:
                                pass
                            self.set_color_theme(name)
                    except Exception:
                        pass
                a.toggled.connect(_set_theme)
                theme_menu.addAction(a)
                self._theme_actions[name] = a

            # Remove deprecated separate colorful themes submenu since we've integrated them into main menu
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

            # Apply dark theme flag to custom widgets
            for widget in self.findChildren(IconWidget):
                widget.update_style_for_theme(True)
        else:
            # Light mode (use selected color theme)
            try:
                theme = self.COLOR_THEMES.get(getattr(self, 'color_theme', 'Default Light'), self.COLOR_THEMES['Default Light'])
                window_bg = theme.get('window_bg', '#ffffff')
                panel_bg = theme.get('panel_bg', '#f5f5f5')
                text_col = theme.get('recommended_text', theme.get('text', '#000000'))
                accent = theme.get('accent', '#0078d7')

                # If dark mode is enabled, apply dark mode transformations to regular themes
                if getattr(self, 'dark_mode', False):
                    # Convert light colors to dark equivalents
                    from PyQt5.QtGui import QColor
                    
                    # Transform background colors
                    if window_bg == '#ffffff':
                        window_bg = '#2b2b2b'
                    else:
                        win_color = QColor(window_bg)
                        window_bg = win_color.darker(200).name()
                    
                    if panel_bg == '#f5f5f5':
                        panel_bg = '#363636'
                    else:
                        panel_color = QColor(panel_bg)
                        panel_bg = panel_color.darker(200).name()
                    
                    # Transform text color
                    if text_col == '#000000':
                        text_col = '#ffffff'
                    else:
                        text_color = QColor(text_col)
                        # If the text color is dark, make it light
                        r, g, b, _ = text_color.getRgb()
                        brightness = (r + g + b) / 3
                        if brightness < 128:  # Dark text
                            text_col = '#ffffff'
                    
                    # Keep accent color but may need to adjust for contrast
                    accent_color = QColor(accent)
                    # Make accent brighter for dark mode if it's too dark
                    r, g, b, _ = accent_color.getRgb()
                    brightness = (r + g + b) / 3
                    if brightness < 100:
                        accent = accent_color.lighter(150).name()

                light_style = f"""
                QMainWindow {{
                    background-color: {window_bg};
                    color: {text_col};
                }}
                QWidget {{
                    background-color: {panel_bg};
                    color: {text_col};
                }}
                QTreeView, QListView, QTableView {{
                    background-color: {panel_bg};
                    color: {text_col};
                    selection-background-color: {accent};
                    selection-color: {text_col};
                }}
                QMenuBar {{
                    background-color: {panel_bg};
                    color: {text_col};
                }}
                QToolBar {{
                    background-color: {panel_bg};
                    color: {text_col};
                }}
                QPushButton {{
                    background-color: {panel_bg};
                    color: {text_col};
                    border: 1px solid rgba(0,0,0,0.08);
                    padding: 5px;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {window_bg};
                }}
                QStatusBar {{
                    background-color: {panel_bg};
                    color: {text_col};
                }}
                QMenu {{
                    background-color: {panel_bg};
                    color: {text_col};
                }}
                """
                self.setStyleSheet(light_style)
            except Exception:
                self.setStyleSheet("")

            # Apply light theme flag to custom widgets
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
        """Show a scrollable about dialog with release notes."""
        # Build about text
        about_lines = [
            "Gary's File Manager",
            "Version 1.2.1 - Theme enhancements, yellow themes, and visual improvements",
            "Release: September 2025",
            "",
            "What's New in 1.2.1:",
            "• Added yellow themes for all categories: 'Sunny Yellow' (regular), 'Golden Thunder' (strong), 'Muted Gold' (subdued)",
            "• Updated strong and subdued theme swatches to use rounded corners for better visual consistency",
            "• Enhanced universal dark mode support across all theme types",
            "• Moved Royal Indigo and Electric Lime themes to Strong Themes category",
            "• Improved theme swatch previews with distinctive shapes for each category",
            "",
            "Previous Updates (1.2.0):",
            "• Added new 'Grape' (purple) and 'Orange' themes with matching dark variants",
            "• Theme menu now shows a small rounded color swatch preview for each theme",
            "• Computed accessible recommended text colors per theme for better contrast",
            "• Persisted event-filter verbosity toggle and added a View → Verbose Event Filter Messages checkbox",
            "• Reduced noisy thumbnail and icon-container debug output (toggleable)",
            "• Right-click context menus now use non-blocking popups so clicks outside the app are received",
            "• Fixed various bugs including a context-menu NameError on startup",
            "• Misc UI polish and accessibility improvements",
            "",
            "🚀 FEATURES:",
            "• APK thumbnail extraction and adaptive icon composition (extracts launcher icons from .apk)",
            "• Cache generated APK thumbnails for faster reloads",
            "• Improved ISO thumbnails – extract EXE icons and composite them over disc artwork",
            "• Improved heuristics and fallbacks for APK/ISO layouts",
            "• Video thumbnailing for major formats (mp4, mkv, avi, mov, etc.)",
            "• ffmpeg-based thumbnail extraction (cross-platform)",
            "• Persistent thumbnail cache for images and videos",
            "• Improved error handling and stability",
            "• 'Open with...' option in right-click menu for files",
            "• Custom PyQt dialog for choosing applications",
            "• Platform-specific handling for launching files",
            "• Multiple view modes (Thumbnail, List, Detail)",
            "• Advanced file operations with progress tracking",
            "• Multi-tab browsing with session persistence",
            "• Per-folder sort settings (remembers preferences)",
            "• Tree view navigation sidebar",
            "• ZIP, TAR, TAR.GZ, TGZ, TAR.BZ2, RAR support",
            "• Create, extract, and browse archives",
            "• Built-in directory selection dialogs",
            "• Archive preview with file listing",
            "• Advanced search engine with filters",
            "• File content preview pane",
            "• Image preview with scaling",
            "• Text file syntax highlighting",
            "• Dark/Light theme toggle",
            "• Customizable thumbnail sizes",
            "• Word wrapping for long filenames",
            "• Resizable panels and toolbars",
            "• Professional context menus",
            "• Background file operations",
            "• Smart memory management",
            "• Thumbnail caching system",
            "• Responsive UI with progress indicators",
            "• Cross-platform compatibility with Windows optimizations",
            "",
            "FEATURES ADDED IN 1.1.3 (moved):",
            "• Tools → Recursive Precache Thumbnails... for multi-size, fast thumbnail generation",
            "• Always shows a progress dialog during thumbnail caching",
            "• Thread-safe thumbnail generation",
            "• No extra popups during recursive precache; only the progress dialog is shown",
            "",
        ]

        about_text = "\n".join(about_lines)

        # Show dialog
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QLabel, QDialogButtonBox
            from PyQt5.QtCore import Qt

            dlg = QDialog(self)
            dlg.setWindowTitle("About Gary's File Manager")
            dlg.resize(560, 420)

            layout = QVBoxLayout(dlg)

            content = QLabel()
            content.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            content.setWordWrap(True)
            html = '<br>'.join([f"{line}" for line in about_text.split('\n')])
            content.setText(html)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(content)

            layout.addWidget(scroll)

            btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
            btn_box.accepted.connect(dlg.accept)
            layout.addWidget(btn_box)

            dlg.exec_()
        except Exception:
            # Fallback to QMessageBox if widgets unavailable
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.about(self, "About Gary's File Manager", about_text)
            except Exception:
                print(about_text)

    def show_sourceforge_upload_dialog(self, prefill_path=None, auto_start=False):
        """Show SourceForge upload dialog using a QThread worker.

        Arguments:
            prefill_path (str|None): if provided, pre-fill the File field with this path.
            auto_start (bool): if True and prefill_path is provided, start upload automatically.
        """
        try:
            from PyQt5.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QVBoxLayout, QMessageBox, QProgressDialog
            from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
        except Exception:
            try:
                QMessageBox.information(self, "Upload", "Qt not available for upload dialog")
            except Exception:
                print("Qt not available for upload dialog")
            return

        class MultiUploadWorker(QObject):
            file_finished = pyqtSignal(str, dict)  # path, result
            all_finished = pyqtSignal()

            def __init__(self, paths, project, username, password):
                super().__init__()
                self.paths = list(paths)
                self.project = project
                self.username = username
                self.password = password
                self._stopped = False

            def stop(self):
                self._stopped = True

            def run(self):
                for p in self.paths:
                    if self._stopped:
                        break
                    try:
                        res = upload_to_sourceforge(p, self.project, self.username, self.password)
                        if not isinstance(res, dict):
                            res = {'status': 'ok', 'result': res}
                    except Exception as e:
                        res = {'status': 'error', 'message': str(e)}
                    self.file_finished.emit(p, res)
                self.all_finished.emit()

        dlg = QDialog(self)
        dlg.setWindowTitle("Upload to SourceForge")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        # Multi-file list
        from PyQt5.QtWidgets import QListWidget, QHBoxLayout

        file_list = QListWidget()
        add_btn = QPushButton("Add Files...")
        remove_btn = QPushButton("Remove Selected")

        def on_add():
            paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
            for p in paths:
                file_list.addItem(p)

        def on_remove():
            for it in file_list.selectedItems():
                file_list.takeItem(file_list.row(it))

        add_btn.clicked.connect(on_add)
        remove_btn.clicked.connect(on_remove)

        form.addRow(QLabel("Files:"), file_list)
        form.addRow("Project:", QLineEdit())
        project_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        form.addRow("Username:", QLineEdit())
        username_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        form.addRow("Password:", QLineEdit())
        password_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        password_edit.setEchoMode(QLineEdit.Password)

        layout.addLayout(form)
        btns_h = QHBoxLayout()
        btns_h.addWidget(add_btn)
        btns_h.addWidget(remove_btn)
        btns_h.addStretch()
        layout.addLayout(btns_h)

        btn_upload = QPushButton("Start Upload")
        btn_cancel = QPushButton("Cancel")
        layout.addWidget(btn_upload)
        layout.addWidget(btn_cancel)

        progress = QProgressDialog("Uploading...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(200)

        worker_thread = None
        worker_obj = None

        def start_upload():
            nonlocal worker_thread, worker_obj
            paths = [file_list.item(i).text() for i in range(file_list.count())]
            project = project_edit.text().strip()
            username = username_edit.text().strip()
            password = password_edit.text()
            if not paths or not project:
                QMessageBox.warning(dlg, "Upload", "Please add one or more files and enter project name")
                return

            progress.show()

            worker_obj = MultiUploadWorker(paths, project, username, password)
            worker_thread = QThread()
            worker_obj.moveToThread(worker_thread)
            worker_thread.started.connect(worker_obj.run)

            def on_file_finished(path, result):
                # Show a non-blocking notification for each file
                if result.get('status') == 'ok':
                    self.status_bar.showMessage(f"Uploaded {os.path.basename(path)}", 4000)
                else:
                    self.status_bar.showMessage(f"Error uploading {os.path.basename(path)}: {result.get('message')}", 6000)

            def on_all_finished():
                progress.close()
                QMessageBox.information(self, "Upload", "All queued uploads finished")
                worker_thread.quit()
                worker_thread.wait()
                dlg.accept()

            worker_obj.file_finished.connect(on_file_finished)
            worker_obj.all_finished.connect(on_all_finished)
            worker_thread.start()

        btn_upload.clicked.connect(start_upload)

        def on_cancel():
            try:
                if worker_obj:
                    worker_obj.stop()
            except Exception:
                pass
            dlg.reject()

        btn_cancel.clicked.connect(on_cancel)

        # Pre-fill list if provided
        if prefill_path:
            # accept either a single path or a list
            if isinstance(prefill_path, (list, tuple)):
                for p in prefill_path:
                    file_list.addItem(p)
            else:
                file_list.addItem(prefill_path)
            if auto_start:
                QTimer.singleShot(150, start_upload)

        dlg.exec_()

    def show_github_upload_dialog(self):
        """Show GitHub release upload dialog with simple progress indicator."""
        try:
            from PyQt5.QtWidgets import QDialog, QFormLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QVBoxLayout, QMessageBox, QProgressDialog
            from PyQt5.QtCore import Qt, QTimer
        except Exception:
            try:
                QMessageBox.information(self, "Upload", "Qt not available for upload dialog")
            except Exception:
                print("Qt not available for upload dialog")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Upload to GitHub Release")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        file_edit = QLineEdit()
        browse_btn = QPushButton("Browse...")
        def on_browse():
            path, _ = QFileDialog.getOpenFileName(self, "Select file to upload")
            if path:
                file_edit.setText(path)
        browse_btn.clicked.connect(on_browse)

        form.addRow(QLabel("File:"), file_edit)
        form.addRow("Repo (owner/repo):", QLineEdit())
        repo_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        form.addRow("Tag (e.g. v1.0.0):", QLineEdit())
        tag_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        form.addRow("Access Token:", QLineEdit())
        token_edit = form.itemAt(form.rowCount()-1, QFormLayout.FieldRole).widget()
        token_edit.setEchoMode(QLineEdit.Password)

        layout.addLayout(form)
        layout.addWidget(browse_btn)
        btn_upload = QPushButton("Upload")
        btn_cancel = QPushButton("Cancel")
        layout.addWidget(btn_upload)
        layout.addWidget(btn_cancel)

        def do_upload():
            path = file_edit.text().strip()
            repo = repo_edit.text().strip()
            tag = tag_edit.text().strip()
            token = token_edit.text().strip()
            if not path or not repo or not tag or not token:
                QMessageBox.warning(dlg, "Upload", "Please fill all fields")
                return

            progress = QProgressDialog("Uploading to GitHub...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.ApplicationModal)
            progress.setMinimumDuration(200)
            progress.show()

            done_event = {'done': False, 'result': None}

            def worker():
                try:
                    res = upload_to_github_release(path, repo, tag, token)
                    done_event['result'] = res
                except Exception as e:
                    done_event['result'] = {'status': 'error', 'message': str(e)}
                finally:
                    done_event['done'] = True

            import threading
            t = threading.Thread(target=worker, daemon=True)
            t.start()

            def poll():
                if done_event['done']:
                    progress.close()
                    r = done_event['result']
                    if isinstance(r, dict) or hasattr(r, 'get'):
                        if r.get('status') == 'ok' or r.get('state') or r.get('id'):
                            QMessageBox.information(self, "Upload", f"Upload finished: {r}")
                        else:
                            QMessageBox.information(self, "Upload", str(r))
                    else:
                        QMessageBox.information(self, "Upload", str(r))
                    dlg.accept()
                else:
                    QTimer.singleShot(200, poll)

            QTimer.singleShot(200, poll)

        btn_upload.clicked.connect(do_upload)
        btn_cancel.clicked.connect(dlg.reject)
        dlg.exec_()

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
        """Show preferences dialog allowing user to control caching dialog behavior"""
        try:
            class PreferencesDialog(QDialog):
                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.setWindowTitle("Preferences")
                    self.setMinimumWidth(360)
                    layout = QVBoxLayout(self)

                    label = QLabel("Thumbnail caching dialog behavior:")
                    layout.addWidget(label)

                    from PyQt5.QtWidgets import QRadioButton, QButtonGroup
                    self.group = QButtonGroup(self)
                    self.rb_ask = QRadioButton("Ask (show when work needed)")
                    self.rb_always = QRadioButton("Always show caching dialog")
                    self.rb_never = QRadioButton("Always hide caching dialog")
                    self.group.addButton(self.rb_ask)
                    self.group.addButton(self.rb_always)
                    self.group.addButton(self.rb_never)

                    layout.addWidget(self.rb_ask)
                    layout.addWidget(self.rb_always)
                    layout.addWidget(self.rb_never)

                    btn_layout = QHBoxLayout()
                    ok = QPushButton("OK")
                    cancel = QPushButton("Cancel")
                    btn_layout.addWidget(ok)
                    btn_layout.addWidget(cancel)
                    layout.addLayout(btn_layout)

                    ok.clicked.connect(self.accept)
                    cancel.clicked.connect(self.reject)

                    # Load current setting
                    try:
                        settings = QSettings("garysfm", "garysfm")
                        val = settings.value('cache_dialog_pref', 'ask')
                    except Exception:
                        val = 'ask'
                    if val == 'always_show':
                        self.rb_always.setChecked(True)
                    elif val == 'always_hide':
                        self.rb_never.setChecked(True)
                    else:
                        self.rb_ask.setChecked(True)

                def selected_value(self):
                    if self.rb_always.isChecked():
                        return 'always_show'
                    if self.rb_never.isChecked():
                        return 'always_hide'
                    return 'ask'

            dlg = PreferencesDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                val = dlg.selected_value()
                try:
                    settings = QSettings("garysfm", "garysfm")
                    settings.setValue('cache_dialog_pref', val)
                except Exception:
                    pass
                QMessageBox.information(self, "Preferences", "Preferences saved.")
        except Exception as e:
            QMessageBox.information(self, "Preferences", f"Preferences dialog failed: {e}")
    
    def toggle_show_hidden_files(self):
        """Toggle showing hidden files (placeholder for future implementation)"""
        # For now, show a simple message
        QMessageBox.information(self, "Hidden Files", "Show/hide hidden files coming soon!")
    
    def open_new_tab(self):
        """Open new tab (placeholder for future implementation)"""
        # For now, show a simple message
        QMessageBox.information(self, "New Tab", "Tabbed interface coming soon!")
    
    def move_to_trash(self):
        """Move selected items to trash (cross-platform).

        Tries send2trash, then platform helpers, and finally prompts to permanently
        delete items that could not be moved to trash.
        """
        selected_items = self.get_selected_items()
        if not selected_items:
            return

        failures = []

        # Try send2trash first
        try:
            import send2trash
            for item in selected_items:
                try:
                    send2trash.send2trash(item)
                except Exception:
                    failures.append(item)
            if not failures:
                self.refresh_current_view()
                QMessageBox.information(self, "Success", f"Moved {len(selected_items)} item(s) to trash.")
                return
        except Exception:
            failures = list(selected_items)

        # Try platform-specific fallbacks for remaining failures
        remaining = []
        for item_path in failures:
            try:
                if PlatformUtils.is_windows():
                    cmd = f'powershell.exe -Command "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(\'{item_path}\', \'OnlyErrorDialogs\', \'SendToRecycleBin\')"'
                    subprocess.run(cmd, shell=True, check=True)
                elif PlatformUtils.is_macos():
                    script = f'tell application "Finder" to delete POSIX file "{item_path}"'
                    subprocess.run(["osascript", "-e", script], check=True)
                else:
                    subprocess.run(["gio", "trash", item_path], check=True)
            except Exception:
                remaining.append(item_path)

        # If any items still remain, ask the user whether to permanently delete them
        if remaining:
            reply = QMessageBox.question(
                self,
                "Move to Trash",
                f"Some items could not be moved to the trash. Permanently delete {len(remaining)} item(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                for p in remaining:
                    try:
                        if os.path.isdir(p):
                            import shutil
                            shutil.rmtree(p)
                        else:
                            os.remove(p)
                    except Exception:
                        # ignore failures on delete
                        pass

        try:
            self.refresh_current_view()
        except Exception:
            pass

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
        """Use the selected history entry and update clipboard and UI"""
        selection = self.history_list.selectionModel().selectedRows()
        if selection:
            row = selection[0].row()
            history = self.clipboard_manager.get_history()
            if row < len(history):
                self.selected_entry = history[row]
                # Restore clipboard state
                self.clipboard_manager.set_current_operation(
                    self.selected_entry['operation'],
                    self.selected_entry['paths']
                )
                # Optionally refresh UI if parent is main window
                if self.parent() and hasattr(self.parent(), 'refresh_current_view'):
                    self.parent().refresh_current_view()
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
        self.parent_window = parent  # Store reference to parent
        self.setup_ui()
    
    def __del__(self):
        """Destructor to ensure proper cleanup"""
        try:
            pass  # No special cleanup needed
        except:
            pass
    
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
            archive_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            archive_path = os.path.join(self.current_folder, archive_name)
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item_path in self.selected_items:
                    try:
                        if os.path.isfile(item_path):
                            zipf.write(item_path, os.path.basename(item_path))
                        elif os.path.isdir(item_path):
                            for root, dirs, files in os.walk(item_path):
                                for file in files:
                                    try:
                                        file_path = os.path.join(root, file)
                                        arc_path = os.path.relpath(file_path, os.path.dirname(item_path))
                                        zipf.write(file_path, arc_path)
                                    except Exception as file_error:
                                        self.results_text.append(f"Skipped file {file}: {str(file_error)}")
                                        continue
                    except Exception as item_error:
                        self.results_text.append(f"Error processing {os.path.basename(item_path)}: {str(item_error)}")
                        continue
            
            self.results_text.append(f"Archive created: {archive_name}")
        except Exception as e:
            self.results_text.append(f"Archive creation failed: {str(e)}")
            print(f"Archive creation error: {e}")
            import traceback
            traceback.print_exc()
    
    def calculate_size(self):
        """Calculate total size of selected items"""
        try:
            total_size = 0
            file_count = 0
            folder_count = 0
            
            for item_path in self.selected_items:
                try:
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
                                except (OSError, IOError):
                                    continue  # Skip inaccessible files
                except Exception as item_error:
                    self.results_text.append(f"Error accessing {os.path.basename(item_path)}: {str(item_error)}")
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
        except Exception as e:
            self.results_text.append(f"Size calculation failed: {str(e)}")
            print(f"Size calculation error: {e}")
            import traceback
            traceback.print_exc()
    
    def duplicate_items(self):
        """Create duplicates of selected items"""
        try:
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
                    base_name = os.path.basename(item_path) if item_path else "unknown"
                    self.results_text.append(f"Failed to duplicate {base_name}: {str(e)}")
                    continue
            
            self.results_text.append(f"Successfully duplicated {success_count} item(s)")
        except Exception as e:
            self.results_text.append(f"Duplication operation failed: {str(e)}")
            print(f"Duplication error: {e}")
            import traceback
            traceback.print_exc()

    def closeEvent(self, event):
        """Handle dialog close event safely"""
        try:
            # Clean up any resources if needed
            event.accept()
        except Exception as e:
            print(f"Error closing advanced operations dialog: {e}")
            event.accept()  # Accept anyway to prevent hanging


# Main application entry point
def main():
    """Start the file manager application"""
    try:
        # Enable high DPI scaling BEFORE creating QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)

        # Set application metadata
        app.setApplicationName("Gary's File Manager")
        app.setApplicationVersion("1.2.1")
        app.setOrganizationName("Gary's Software")

        # All widget creation must be after QApplication
        manager = SimpleFileManager()
        manager.show()

        # Run application and capture exit code
        exit_code = app.exec_()

        # Platform-specific cleanup
        if sys.platform.startswith('win'):
            print("Windows cleanup - forcing exit...")
            import os
            os._exit(exit_code)
        else:
            print("Standard exit...")
            sys.exit(exit_code)

    except Exception as e:
        print(f"Application startup failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()


# -------------------- Upload helpers (GitHub + SourceForge) --------------------
def upload_to_github_release(file_path, repo, tag, token, release_name=None):
    """Upload a file to a GitHub release. If release for tag doesn't exist, create it.

    Args:
        file_path: local path to upload
        repo: 'owner/repo'
        tag: git tag name for the release
        token: GitHub personal access token with repo permissions
        release_name: optional release name
    Returns: dict response JSON on success
    """
    import os
    import requests

    api = 'https://api.github.com'
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}

    # Find release for tag
    r = requests.get(f'{api}/repos/{repo}/releases', headers=headers)
    r.raise_for_status()
    releases = r.json()
    release = next((rel for rel in releases if rel.get('tag_name') == tag), None)

    if release is None:
        # Create release
        payload = {'tag_name': tag, 'name': release_name or tag, 'prerelease': False}
        r = requests.post(f'{api}/repos/{repo}/releases', json=payload, headers=headers)
        r.raise_for_status()
        release = r.json()

    upload_url = release.get('upload_url', '').split('{')[0]
    if not upload_url:
        raise RuntimeError('Release upload URL not found')

    filename = os.path.basename(file_path)
    params = {'name': filename}
    with open(file_path, 'rb') as fh:
        headers['Content-Type'] = 'application/octet-stream'
        upload_resp = requests.post(upload_url, params=params, data=fh, headers=headers)
        upload_resp.raise_for_status()
        return upload_resp.json()


def upload_to_sourceforge(file_path, project, username, password, sftp_path='/incoming'):
    """Upload a file to SourceForge.

    Strategy:
    1. Attempt a simple HTTP POST to an illustrative FRS endpoint (may fail).
    2. If HTTP POST fails, fall back to SFTP upload to the project's incoming directory
       using paramiko. This is often the recommended programmatic approach.

    Returns: dict {status: 'ok'|'error', message: str, details: opt}
    """
    import os
    import requests

    basename = os.path.basename(file_path)

    # First attempt: HTTP POST (illustrative)
    try:
        upload_url = f'https://frs.sourceforge.net/api/1.0/projects/{project}/upload/'
        with open(file_path, 'rb') as fh:
            files = {'file': (basename, fh)}
            data = {'user': username, 'pass': password}
            r = requests.post(upload_url, files=files, data=data, timeout=60)
        if r.status_code in (200, 201):
            try:
                payload = r.json() if r.headers.get('Content-Type', '').startswith('application/json') else {'status': 'ok'}
            except Exception:
                payload = {'status': 'ok', 'text': r.text}
            return {'status': 'ok', 'method': 'http', 'details': payload}
    except Exception as e:
        http_err = e
    else:
        http_err = None

    # Fallback: SFTP via paramiko
    try:
        import paramiko
    except Exception as e:
        return {'status': 'error', 'message': 'HTTP upload failed and paramiko (SFTP) is not available', 'details': str(http_err or e)}

    try:
        transport = paramiko.Transport(("frs.sourceforge.net", 22))
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        remote_dir = sftp_path or '/incoming'
        try:
            sftp.chdir(remote_dir)
        except IOError:
            # try to create remote dir
            try:
                sftp.mkdir(remote_dir)
                sftp.chdir(remote_dir)
            except Exception:
                pass

        remote_path = os.path.join(remote_dir, basename)
        sftp.put(file_path, remote_path)
        sftp.close()
        transport.close()
        return {'status': 'ok', 'method': 'sftp', 'path': remote_path}
    except Exception as e:
        return {'status': 'error', 'message': 'Both HTTP and SFTP upload attempts failed', 'details': str(e)}


def cli_upload():
    """Simple CLI helper to upload a file to GitHub or SourceForge.

    Prompts the user on stdin for required values.
    """
    import getpass
    import requests
    print('Upload helper')
    choice = input('Upload to (g)ithub or (s)ourceforge? [g/s]: ').strip().lower()
    path = input('Path to file: ').strip()
    if choice == 'g':
        repo = input('GitHub repo (owner/repo): ').strip()
        tag = input('Release tag (e.g. v1.0): ').strip()
        token = getpass.getpass('GitHub token: ')
        print('Uploading...')
        print(upload_to_github_release(path, repo, tag, token))
    else:
        project = input('SourceForge project short name: ').strip()
        username = input('SF username: ').strip()
        password = getpass.getpass('SF password: ')
        print('Uploading...')
        print(upload_to_sourceforge(path, project, username, password))

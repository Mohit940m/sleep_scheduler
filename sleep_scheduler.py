import sys
import math
import time
import threading
import platform
import os
import subprocess
import json

from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QMessageBox, QFrame
)

# This block is specifically for Windows taskbar icon issue
if sys.platform == 'win32':
    import ctypes
    # Arbitrary string: Use a unique identifier for your application.
    # Reverse DNS format is common, e.g., 'com.yourcompany.yourapp.version'
    myappid = 'com.mycompany.sleepscheduler.v1_0'
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except AttributeError:
        # Handle cases where SetCurrentProcessExplicitAppUserModelID might not be available
        pass

# --- Windows Acrylic Blur Helper ---
def enable_blur_behind_win(window):
    """
    Enables the Windows 10/11 acrylic blur behind the given Qt window.
    Only works on Windows 10/11.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        import ctypes.wintypes

        hwnd = int(window.winId())
        accent_policy = ctypes.c_int(3)  # ACCENT_ENABLE_BLURBEHIND = 3
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_int),
                ("AnimationId", ctypes.c_int)
            ]
        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t)
            ]
        accent = ACCENTPOLICY()
        accent.AccentState = 3  # ACCENT_ENABLE_BLURBEHIND
        accent.AccentFlags = 2  # Default
        accent.GradientColor = 0xCC222222  # 0xAABBGGRR (AA=alpha, BB=blue, GG=green, RR=red)
        accent.AnimationId = 0

        data = WINCOMPATTRDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        set_window_comp_attr = ctypes.windll.user32.SetWindowCompositionAttribute
        set_window_comp_attr(hwnd, ctypes.byref(data))
    except Exception as e:
        print("Acrylic blur not supported:", e)

class GlassFrame(QFrame):
    """A semi-transparent frame to simulate glass effect (no blur here)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(34,34,34,180);
                border-radius: 18px;
            }
        """)

class CircularTimerWidget(QWidget):
    def __init__(self, diameter=200, parent=None):
        super().__init__(parent)
        self.diameter = diameter
        self.setMinimumSize(diameter, diameter)
        self.total_seconds = 1
        self.remaining_seconds = 1

    def set_timer(self, total, remaining):
        self.total_seconds = total
        self.remaining_seconds = remaining
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Define geometry
        rect = QRectF(10, 10, self.diameter - 20, self.diameter - 20)

        # 1. Draw the background track for the ring (e.g., a dark grey)
        painter.setBrush(QColor(60, 60, 60, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)

        # Draw the arc (progress)
        if self.total_seconds > 0:
            angle = 360 * (self.remaining_seconds / self.total_seconds)
        else:
            angle = 0

        # 2. Draw the progress pie slice on top of the track
        if angle > 0:
            painter.setBrush(QColor(0,234,255,255))
            painter.setPen(Qt.NoPen)
            # Start at 90 degrees (top) and draw clockwise for the remaining time
            painter.drawPie(rect, 90 * 16, int(-angle * 16))

        # 3. Draw an inner circle to create the "hole", making it a ring.
        # The color should match the main frame's background.
        inner_circle_margin = 30  # Adjust this to change the ring's thickness
        inner_rect = QRectF(
            inner_circle_margin,
            inner_circle_margin,
            self.diameter - 2 * inner_circle_margin,
            self.diameter - 2 * inner_circle_margin
        )
        painter.setBrush(QColor(34, 34, 34, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(inner_rect)

        # 4. Draw the time text
        mins, secs = divmod(self.remaining_seconds, 60)
        time_str = f"{mins:02}:{secs:02}"
        painter.setPen(QColor(255,255,255,255))
        font = QFont("Segoe UI", 32, QFont.Bold)
        painter.setFont(font)
        text_rect = QRectF(0, 0, self.diameter, self.diameter)
        painter.drawText(text_rect, Qt.AlignCenter, time_str)

class SleepScheduler(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sleep/Hibernate Scheduler")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(370, 440)

        # Main glass frame
        self.frame = GlassFrame(self)
        self.frame.setGeometry(10, 10, 350, 420)

        # Close button
        self.close_btn = QPushButton("×", self)
        self.close_btn.setGeometry(340, 15, 20, 20)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff5f57;
                color: #bf0000;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:pressed {
                background-color: #d94c44;
            }
        """)
        self.close_btn.clicked.connect(self.close)

        # Layouts
        main_layout = QVBoxLayout(self.frame)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(12)

        # Input
        label = QLabel("Enter time in seconds:")
        label.setStyleSheet("color: #fff; font-size: 14px;")
        main_layout.addWidget(label)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Seconds")
        self.entry.setStyleSheet("""
            QLineEdit {
                background: #333;
                color: #fff;
                border: none;
                border-radius: 8px;
                padding: 8px;
                font-size: 18px;
            }
        """)
        self.entry.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.entry)

        # Radio buttons
        radio_layout = QHBoxLayout()
        self.sleep_radio = QRadioButton("Sleep")
        self.sleep_radio.setChecked(True)
        self.hibernate_radio = QRadioButton("Hibernate")
        for rb in (self.sleep_radio, self.hibernate_radio):
            rb.setStyleSheet("""
                QRadioButton {
                    color: #fff;
                    font-size: 13px;
                }
                QRadioButton::indicator:checked {
                    background-color: #00eaff;
                    border: 1px solid #00eaff;
                }
            """)
        radio_layout.addWidget(self.sleep_radio)
        radio_layout.addWidget(self.hibernate_radio)
        main_layout.addLayout(radio_layout)

        # Schedule button
        self.schedule_btn = QPushButton("Schedule")
        self.schedule_btn.setStyleSheet("""
            QPushButton {
                background: #00eaff;
                color: #222;
                font-weight: bold;
                font-size: 16px;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:pressed {
                background: #00bcd4;
                color: #fff;
            }
        """)
        self.schedule_btn.clicked.connect(self.schedule_action)
        main_layout.addWidget(self.schedule_btn)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #ff5f57;
                color: #fff;
                font-weight: bold;
                font-size: 16px;
                border: none;
                border-radius: 8px;
                padding: 8px 0;
            }
            QPushButton:pressed {
                background: #d94c44;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_action)
        main_layout.addWidget(self.cancel_btn)
        self.cancel_btn.hide()

        # Circular timer
        self.circular_timer = CircularTimerWidget(diameter=200)
        main_layout.addWidget(self.circular_timer, alignment=Qt.AlignCenter)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #aaa; font-style: italic; font-size: 12px;")
        main_layout.addWidget(self.status_label)

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)
        self.total_seconds = 0
        self.remaining_seconds = 0
        self.is_cancelled = False

        self.load_settings()

    def showEvent(self, event):
        super().showEvent(event)
        enable_blur_behind_win(self)

    def schedule_action(self):
        try:
            delay = int(self.entry.text())
            if delay <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Please enter a valid number of seconds.")
            return

        self.is_cancelled = False
        action = "Sleep" if self.sleep_radio.isChecked() else "Hibernate"
        self.save_settings(delay, action)

        self.status_label.setText(f"Scheduled {action} in {delay} seconds...")
        self.total_seconds = delay
        self.remaining_seconds = delay
        self.circular_timer.set_timer(self.total_seconds, self.remaining_seconds)
        self.timer.start(1000)

        # Update UI for active timer
        self.schedule_btn.hide()
        self.cancel_btn.show()
        self.entry.setEnabled(False)
        self.sleep_radio.setEnabled(False)
        self.hibernate_radio.setEnabled(False)

        # Start the actual action in a thread
        threading.Thread(target=self.delayed_action, args=(delay, action), daemon=True).start()

    def cancel_action(self):
        self.is_cancelled = True
        self.timer.stop()

        self.total_seconds = 0
        self.remaining_seconds = 0
        self.circular_timer.set_timer(0, 0)
        self.status_label.setText("Action cancelled.")

        # Reset UI
        self.cancel_btn.hide()
        self.schedule_btn.show()
        self.entry.setEnabled(True)
        self.sleep_radio.setEnabled(True)
        self.hibernate_radio.setEnabled(True)

    def update_timer(self):
        self.remaining_seconds -= 1
        if self.remaining_seconds >= 0:
            self.circular_timer.set_timer(self.total_seconds, self.remaining_seconds)
        if self.remaining_seconds < 0:
            self.timer.stop()
            if not self.is_cancelled:
                self.status_label.setText("Action executed.")

            # Reset UI
            self.cancel_btn.hide()
            self.schedule_btn.show()
            self.entry.setEnabled(True)
            self.sleep_radio.setEnabled(True)
            self.hibernate_radio.setEnabled(True)

    def delayed_action(self, delay, action):
        time.sleep(delay)
        if self.is_cancelled:
            return
        if platform.system() == "Windows":
            if action == "Sleep":
                subprocess.call(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            elif action == "Hibernate":
                os.system("shutdown /h")
        else:
            # Show message on main thread
            def show_msg():
                QMessageBox.information(self, "Unsupported OS", "This script currently supports only Windows.")
            QTimer.singleShot(0, show_msg)

    def save_settings(self, seconds, action):
        """Saves the last used duration and action to a file."""
        settings = {'last_duration': seconds, 'last_action': action}
        try:
            with open('settings.json', 'w') as f:
                json.dump(settings, f)
        except IOError as e:
            print(f"Could not save settings: {e}")

    def load_settings(self):
        """Loads the last used duration from a file."""
        settings_file = 'settings.json'
        if not os.path.exists(settings_file):
            return
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                last_duration = settings.get('last_duration')
                if isinstance(last_duration, int):
                    self.entry.setText(str(last_duration))
                last_action = settings.get('last_action')
                if last_action == "Hibernate":
                    self.hibernate_radio.setChecked(True)
                # Default is "Sleep", which is already checked in __init__
        except (IOError, json.JSONDecodeError) as e:
            print(f"Could not load settings: {e}")

    # Optional: Drag window by clicking anywhere
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SleepScheduler()
    win.show()
    sys.exit(app.exec_())
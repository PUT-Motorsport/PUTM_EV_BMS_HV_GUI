import sys
import json
import threading
import queue
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from lv_2 import MainWindow as MainWindowLV
from hv_6 import MainWindow as MainWindowHV

import serial
import socket

def safe_readline(source):
    raw = source.readline()
    return raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()

def detect_source_and_type():
    try:
        source = open_socket()
        line = safe_readline(source)
        if line:
            data = json.loads(line)
            return source, data
        source.close()
    except Exception:
        pass

    ports = serial.tools.list_ports.comports()
    for p in ports:
        try:
            s = serial.Serial(p.device, baudrate=9600, timeout=1)
            time.sleep(0.1)
            line = safe_readline(s)
            if line:
                data = json.loads(line)
                return s, data 
            s.close()
        except Exception as e:
            print(f"Port {p.device} failed: {e}")
            continue

    return None, None


class MainApp(QMainWindow):
    def __init__(self, source=None):
        super().__init__()
        self.setWindowTitle("BMS App")

        self.overlay = PendingOverlay(self)

        self.source = source
        self.exit_event = threading.Event()
        self.widget_lv = None
        self.widget_hv = None
        self.active_widget = None

        self.last_data = None
        self.last_data_time = 0

        if self.source:
            self.thread = threading.Thread(target=self.reader_thread, daemon=True)
            self.thread.start()

        self.timer = self.startTimer(100)
        placeholder = QLabel("Waiting for data...")
        placeholder.setAlignment(Qt.AlignCenter)
        self.set_widget(placeholder) 
        self.show()

    def reconnect_source(self):
        print("Trying to reconnect.")
        try:
            new_source, new_data = detect_source_and_type()
            if new_source:
                self.source = new_source
                self.last_data = new_data
                self.last_data_time = time.time()

                self.thread = threading.Thread(target=self.reader_thread, daemon=True)
                self.thread.start()
                print("Reconnected to new data source.")
        except Exception as e:
            print(f"Reconnection failed: {e}")


    def reader_thread(self):
        while not self.exit_event.is_set():
            try:
                line = safe_readline(self.source)
                if line:
                    data = json.loads(line)
                    self.last_data = data
                    self.last_data_time = time.time()
            except Exception as e:
                time.sleep(0.5)  

    def timerEvent(self, _):
        data_timeout = 3 
        time_since_last = time.time() - self.last_data_time

        if self.last_data is None or time_since_last > data_timeout:
            if self.overlay.isHidden():
                print("Pending.")
                self.overlay.setVisible(True)

            if self.source:
                try:
                    self.source.close()
                except:
                    pass
                self.source = None

            if not hasattr(self, 'last_recconnect_attempt'):
                self.last_recconnect_attempt = 0
            if time.time() - self.last_recconnect_attempt > 5:
                self.last_recconnect_attempt = time.time()
                self.reconnect_source()
            return

        data = self.last_data
        is_lv = "state_of_charge" in data and "battery_state" in data
        is_hv = "soc" in data and "cell_voltage" in data

        if is_lv and not isinstance(self.active_widget, MainWindowLV):
            print("Switching to LV GUI")
            self.set_widget(self.get_lv_widget())

        elif is_hv and not isinstance(self.active_widget, MainWindowHV):
            print("Switching to HV GUI")
            self.set_widget(self.get_hv_widget())

        if hasattr(self.active_widget, "feed_data"):
            self.active_widget.feed_data(data)
        if self.overlay.isVisible():
            self.overlay.setVisible(False)

    def eventFilter(self, obj, event):
        if event.type() == event.Resize and obj == self.active_widget:
            self.overlay.resize(obj.size())
        return super().eventFilter(obj, event)

    def set_widget(self, widget):
        if self.active_widget and self.active_widget != widget:
            self.active_widget.setParent(None)

        '''if hasattr(widget, 'size'):
            self.resize()  '''
        self.active_widget = widget
        self.setCentralWidget(widget)

        self.overlay.setParent(self)
        self.overlay.resize(widget.size())
        self.overlay.raise_()

        widget.installEventFilter(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.centralWidget():
            self.overlay.resize(self.centralWidget().size())

    def get_lv_widget(self):
        if not self.widget_lv:
            self.widget_lv = MainWindowLV(None, [], self.exit_event)
        return self.widget_lv

    def get_hv_widget(self):
        if not self.widget_hv:
            self.hv_read_queue = queue.Queue(maxsize=1)
            self.widget_hv = MainWindowHV(
                self.hv_read_queue, 
                queue.Queue(maxsize=1),
                threading.Event(),
                self.exit_event,
                None
            )
            def feed_data_hv(data):
                try:
                    while not self.hv_read_queue.empty():
                        self.hv_read_queue.get_nowait()
                    self.hv_read_queue.put(json.dumps(data))
                except queue.Full:
                    pass
            self.widget_hv.feed_data = feed_data_hv
        return self.widget_hv

    def closeEvent(self, event):
        self.exit_event.set()
        if self.source:
            try:
                self.source.close()
            except:
                pass
        event.accept()
        QApplication.quit()

class PendingOverlay(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("Waiting for data...")
        self.setAlignment(Qt.AlignCenter)
        #self.setFont(QFont("Sans Serif", 20))
        self.setStyleSheet("background-color: rgba(255, 255, 255, 180); color: black;")
        self.setVisible(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  #pozwala klikać pod overlayem

    def resizeEvent(self, event):
        self.setFixedSize(self.parent().size())

def open_serial(port):
    return serial.Serial(port=port, baudrate=9600, timeout=1)

def open_socket(host="127.0.0.1", port=7000):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s.makefile("r")

def main():
    app = QApplication(sys.argv)

    source, first_data = detect_source_and_type()
    
    win = MainApp(source)

    if first_data:
        win.last_data = first_data
        win.last_data_time = time.time()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

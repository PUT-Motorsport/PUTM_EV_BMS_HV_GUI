import sys
import json
import threading
import queue
import time
import types
import logging 
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from lv_2 import MainWindow as MainWindowLV
from hv_4_d import MainWindow as MainWindowHV, serial_task

import serial
import serial.tools.list_ports
import socket

logger=logging.getLogger("BMS_App_logs")
file_handler= RotatingFileHandler("BMS_App_logs", maxBytes=1_000_000, backupCount=3)
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", 
                    handlers=[file_handler, logging.StreamHandler()])

def safe_readline(source):
    raw = source.readline()
    return raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()

def detect_source_and_type():
    '''socket do symulacji'''
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

class Overlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 180);")

        label = QLabel("Pending…", self)
        label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        self.setLayout(layout)
        self.hide()


class MainApp(QMainWindow):
    def __init__(self, source=None):
        super().__init__()
        self.setWindowTitle("BMS App")

        self.pending_label = QLabel("Waiting for data.")
        self.pending_label.setMinimumSize(300, 300)
        self.pending_label.setAlignment(Qt.AlignCenter)

        self.source = source
        self.exit_event = threading.Event()
        self.widget_lv = None
        self.widget_hv = None
        self.active_widget = None

        self.last_data = None
        self.last_data_time = 0
        self.first_data_received = False

        self.overlay = Overlay(self)

        if self.source:
            self.thread = threading.Thread(target=self.reader_thread, daemon=True)
            self.thread.start()

        self.timer = self.startTimer(100)
        self.set_widget(self.pending_label)
        self.show()


    def reconnect_source(self):
        logger.info("Trying to reconnect.")
        try:
            new_source, new_data = detect_source_and_type()
            if new_source:
                self.source = new_source
                self.last_data = new_data
                self.last_data_time = time.time()

                self.thread = threading.Thread(target=self.reader_thread, daemon=True)
                self.thread.start()
                logger.info("Reconnected to a new data source.")
        except Exception as e:
            logger.exception(f"Reconnection failed: {e}")

    def reader_thread(self):
        while not self.exit_event.is_set():
            try:
                line = safe_readline(self.source)
                if line:
                    data = json.loads(line)
                    self.last_data = data
                    self.last_data_time = time.time()
                    logger.debug(f'Received data: {data}')
            except Exception as e:
                logger.exception("Reader thread error")
                time.sleep(0.5)

    def timerEvent(self, _):
        data_timeout = 30
        time_since_last = time.time() - self.last_data_time

        data_invalid = (
            self.last_data is None or
            time_since_last > data_timeout or
            not isinstance(self.last_data, dict) or
            ("soc" in self.last_data and not isinstance(self.last_data["soc"], list)) or
            ("state_of_charge" in self.last_data and not isinstance(self.last_data["state_of_charge"], (int, float)))
        )

        if data_invalid:
            if not self.first_data_received:
                if self.active_widget != self.pending_label:
                    self.set_widget(self.pending_label)
                self.overlay.hide()
            else:
                self.overlay.show()

            if hasattr(self, 'active_widget') and isinstance(self.active_widget, MainWindowHV):
                if hasattr(self, 'serial_thread') and self.serial_thread:
                    if hasattr(self, 'source') and isinstance(self.source, serial.Serial):
                        try:
                            self.source.close()
                        except Exception:
                            pass
                    self.exit_event.set()
                    self.serial_thread.join(timeout=1.0)
                    self.serial_thread = None

            if self.source:
                try:
                    self.source.close()
                except Exception:
                    pass
                self.source = None

            self.last_data = None

            if not hasattr(self, 'last_recconnect_attempt'):
                self.last_recconnect_attempt = 0
            if time.time() - self.last_recconnect_attempt > 5:
                self.last_recconnect_attempt = time.time()
                self.reconnect_source()
            return
    
        if not self.first_data_received:
            self.first_data_received = True

        self.overlay.hide()

        if not self.first_data_received:
            self.first_data_received = True
            self.overlay.hide()

        data = self.last_data
        '''is_lv = "state_of_charge" in data and "battery_state" in data'''
        is_hv = "soc" in data and "cell_voltage" in data

        '''if is_lv and not isinstance(self.active_widget, MainWindowLV):
            logger.info("Switching to LV GUI")
            self.set_widget(self.get_lv_widget())'''

        #elif
        if is_hv and not isinstance(self.active_widget, MainWindowHV):
            logger.info("Switching to HV GUI")
            self.set_widget(self.get_hv_widget())

        if hasattr(self.active_widget, "feed_data"):
            self.active_widget.feed_data(data)

    def set_widget(self, widget):
        if self.active_widget and self.active_widget != widget:
            self.active_widget.setParent(None)

        self.active_widget = widget
        self.setCentralWidget(widget)
        
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215) #ważne żeby resize działało jak trzeba (+ te 3 ify niżej)

        if widget == self.pending_label:
            self.resize(400, 300)  
        elif isinstance(widget, MainWindowHV):
            self.resize(1750, 900)
        elif isinstance(widget, MainWindowLV):
            self.resize(500, 717)
        
        
        self.overlay.raise_()
        self.overlay.resize(self.size())

    def get_lv_widget(self):
        if not self.widget_lv:
            self.widget_lv = MainWindowLV(self.source, [], self.exit_event)
        return self.widget_lv

    def get_hv_widget(self):
        if not self.widget_hv:
            self.hv_read_queue = queue.Queue(maxsize=1)
            self.hv_write_queue = queue.Queue(maxsize=1)
            self.hv_connected_event = threading.Event()

            if isinstance(self.source, serial.Serial):
                port_name = self.source.port
                try:
                    self.source.close()
                except Exception:
                    pass
            elif isinstance(self.source, str):
                port_name = self.source

            self.serial_thread = threading.Thread(
                target=serial_task,
                args=(port_name, self.hv_read_queue, self.hv_write_queue, self.hv_connected_event, self.exit_event),
                daemon=True,
            )
            self.serial_thread.start()

            self.widget_hv = MainWindowHV(
                self.hv_read_queue,
                self.hv_write_queue,
                self.hv_connected_event,
                self.exit_event,
                self.serial_thread
            )

        def feed_data_hv(self, data):
            try:
                while not self.hv_read_queue.empty():
                    self.hv_read_queue.get_nowait()
                self.hv_read_queue.put(json.dumps(data))
            except queue.Full:
                pass

            self.widget_hv.feed_data = types.MethodType(feed_data_hv, self.widget_hv)

        return self.widget_hv

    def closeEvent(self, event):
        self.exit_event.set()
        if hasattr(self, 'serial_thread') and self.serial_thread and self.serial_thread.is_alive():
            self.serial_thread.join(timeout=1.0)
        if self.source:
            try:
                self.source.close()
            except:
                pass
        event.accept()



def open_serial(port):
    return serial.Serial(port=port, baudrate=9600, timeout=1)

def open_socket(host="127.0.0.1", port=7000):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s.makefile("r")

def main():
    logger.info("BMS App starting")
    app = QApplication(sys.argv)

    source, first_data = detect_source_and_type()
    
    win = MainApp(source)

    if first_data:
        win.last_data = first_data
        win.last_data_time = time.time()
    
    try:
        logger.info("BMS App start")
        sys.exit(app.exec_())
    finally:
        logger.info("BMS App exit")

if __name__ == "__main__":
    main()

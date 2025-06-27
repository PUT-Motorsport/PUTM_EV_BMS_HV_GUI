import json
import time
import queue
from types import SimpleNamespace
from statistics import median
from dataclasses import dataclass
import sys
import threading

import numpy as np
import serial
from colorama import Fore, Style

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QHeaderView,
    QTabWidget
    
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import QTimer, Qt

IMAGE_PATH = "putm_logo.png"
SERIAL_DATA_IN_FREQ_SEC = 0.250
FLOAT_PRECISION = 3

@dataclass
class BmsHvData:
    current: float
    acc_voltage: float
    car_voltage: float
    temp_name: int 
    soc: list[float]
    cell_voltage: list[float]
    temperature: list[float]
    discharge: list[int]
    balance: int
    charging: int
    under_voltage: list[int]
    over_voltage: list[int]
    under_temperature: list[int]
    over_temperature: list[int]
    over_current: list[int]
    current_sensor_disconnected: list[int]
    timestamp: float

def float_to_string_with_precision(value, precision):
    return f"{value:.{precision}f}"

def mark_cell_if_discharge(value, is_discharging):
    return f"#{value}#" if is_discharging else value

def print_ok(msg):
    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}")

def print_error(msg):
    print(f"{Fore.RED}{msg}{Style.RESET_ALL}")

def print_warning(msg):
    print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")

def send_message_to_write_queue(write_queue, message):
    try:
        write_queue.put_nowait(message)
    except queue.Full:
        print_error("The write queue is full, the message will be discarded")
        
def feed_data(self, data):
    self.bms_hv_read_queue.queue.clear()
    self.bms_hv_read_queue.put(json.dumps(data))


def adjust_table_height(table):
    table.resizeColumnsToContents()
    table.resizeRowsToContents()
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    total_height = table.verticalHeader().length() + table.horizontalHeader().height()
    table.setMaximumHeight(total_height)


def serial_task(port, read_queue, write_queue, connected_event, exit_event):
    serial_task_prefix = "SERIAL TASK: "
    write_prefix = "WRITE: "
    read_prefix = "READ: "
    keep_alive_prefix = "KEEP_ALIVE: "
    keep_alive_message = "!C-CC@"

    ser = serial.Serial()
    ser.port = port
    ser.timeout = SERIAL_DATA_IN_FREQ_SEC + 0.2

    while not ser.is_open:
        if exit_event.is_set():
            return
        try:
            ser.open()
            connected_event.set()
            print_ok(f"{serial_task_prefix} Serial port: {port} opened")
        except serial.serialutil.SerialException:
            print_error(f"{serial_task_prefix} Serial port: {port} not available")
            time.sleep(1)
            continue

    while True:
        if exit_event.is_set():
            ser.close()
            return
        try:
            print_ok("-------------------------------------------------------")
            ser.write(keep_alive_message.encode("utf-8"))
            print_ok(f"{keep_alive_prefix} Keep alive message sent to the serial port")
            try:
                data = write_queue.get_nowait()
                ser.write(data.encode("utf-8"))
                print_ok(f"{write_prefix} New data sent to the serial port: {data}")
            except queue.Empty:
                print_warning(f"{write_prefix} Nothing to send to the serial port")
            try:
                ser.reset_input_buffer()
                ser.readline()
                line = ser.readline().decode("utf-8")
                if line == "":
                    print_error(f"{read_prefix} Nothing received from the serial port")
                    continue
                read_queue.put_nowait(line)
                print_ok(f"{read_prefix} New data received from the serial port")
            except queue.Full:
                print_warning(f"{read_prefix} Read queue is full")
        except serial.serialutil.SerialException:
            connected_event.clear()
            print_error(f"{serial_task_prefix} Serial port: {port} disconnected")
            while True:
                if exit_event.is_set():
                    return
                try:
                    ser.open()
                    connected_event.set()
                    break
                except serial.serialutil.SerialException:
                    print_error(f"{serial_task_prefix} Failed to reopen serial port: {port}")
                    time.sleep(1)
                    continue

class MainWindow(QMainWindow):
    def __init__(self, bms_hv_read_queue, bms_hv_write_queue, connected_event, exit_event, serial_thread):
        super().__init__()
        self.setWindowTitle("BMS HV Utility")
        self.setMinimumSize(1750, 900)

        self.bms_hv_read_queue = bms_hv_read_queue
        self.bms_hv_write_queue = bms_hv_write_queue
        self.serial_task_connected_event = connected_event
        self.main_exit_event = exit_event
        self.serial_thread = serial_thread

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.updateData)
        self.timer.start(250)

    def init_ui(self):
        main_widget = QWidget()
        tabs = QTabWidget()
        main_widget.setLayout(QVBoxLayout())
        main_widget.layout().addWidget(tabs)
        self.setCentralWidget(main_widget)

        self.tab_main_view = QWidget()
        main_layout = QVBoxLayout()
        self.tab_main_view.setLayout(main_layout)
        tabs.addTab(self.tab_main_view, "Main View")

        self.tab_soc_errors = QWidget()
        self.init_soc_errors_tab()
        tabs.addTab(self.tab_soc_errors, "SOC & Errors")

        image_label = QLabel()
        pixmap = QPixmap(IMAGE_PATH)
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(image_label)

        columns_layout = QHBoxLayout()
        main_layout.addLayout(columns_layout)

        left_layout = QVBoxLayout()
        columns_layout.addLayout(left_layout)

        basic_info_box = QGroupBox("Basic Info")
        basic_info_layout = QGridLayout()
        basic_info_box.setLayout(basic_info_layout)

        basic_info_layout.addWidget(QLabel("Connection Status:"), 0, 0)
        self.label_connection_status = QLabel("-")
        basic_info_layout.addWidget(self.label_connection_status, 0, 1)

        basic_info_layout.addWidget(QLabel("Timestamp:"), 1, 0)
        self.label_timestamp = QLabel("-")
        basic_info_layout.addWidget(self.label_timestamp, 1, 1)
        basic_info_layout.addWidget(QLabel("s"), 1, 2)

        basic_info_layout.addWidget(QLabel("Current:"), 2, 0)
        self.label_current = QLabel("-")
        basic_info_layout.addWidget(self.label_current, 2, 1)
        basic_info_layout.addWidget(QLabel("A"), 2, 2)

        basic_info_layout.addWidget(QLabel("Charging Status:"), 3, 0)
        self.label_charging_status = QLabel("-")
        basic_info_layout.addWidget(self.label_charging_status, 3, 1)

        basic_info_layout.addWidget(QLabel("Balance Status:"), 4, 0)
        self.label_balance_status = QLabel("-")
        basic_info_layout.addWidget(self.label_balance_status, 4, 1)

        basic_info_layout.addWidget(QLabel("SOC Avg:"), 5, 0)
        self.label_soc_avg = QLabel("-")
        basic_info_layout.addWidget(self.label_soc_avg, 5, 1)
        basic_info_layout.addWidget(QLabel("%"), 5, 2)

        basic_info_layout.addWidget(QLabel("Errors:"), 6, 0)
        self.label_errors = QLabel("None")
        basic_info_layout.addWidget(self.label_errors, 6, 1)

        left_layout.addWidget(basic_info_box)

        charge_control_box = QGroupBox("Charge control")
        charge_control_layout = QVBoxLayout()
        charge_control_box.setLayout(charge_control_layout)

        self.btn_full_battery_soc = QPushButton("Full Battery Soc")
        self.btn_full_battery_soc.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!B-FC@"))
        charge_control_layout.addWidget(self.btn_full_battery_soc)

        self.btn_start_charging = QPushButton("Start Charging")
        self.btn_start_charging.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!C-ON@"))
        charge_control_layout.addWidget(self.btn_start_charging)

        self.btn_stop_charging = QPushButton("Stop Charging")
        self.btn_stop_charging.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!C-OF@"))
        charge_control_layout.addWidget(self.btn_stop_charging)

        self.btn_start_balance = QPushButton("Start Balance")
        self.btn_start_balance.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!B-ON@"))
        charge_control_layout.addWidget(self.btn_start_balance)

        self.btn_stop_balance = QPushButton("Stop Balance")
        self.btn_stop_balance.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!B-OF@"))
        charge_control_layout.addWidget(self.btn_stop_balance)

        self.btn_charge_1A = QPushButton("Set Charge Current to 1A")
        self.btn_charge_1A.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!I-1A@"))
        charge_control_layout.addWidget(self.btn_charge_1A)

        self.btn_charge_2A = QPushButton("Set Charge Current to 2A")
        self.btn_charge_2A.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!I-2A@"))
        charge_control_layout.addWidget(self.btn_charge_2A)

        self.btn_charge_4A = QPushButton("Set Charge Current to 4A")
        self.btn_charge_4A.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!I-4A@"))
        charge_control_layout.addWidget(self.btn_charge_4A)

        self.btn_charge_8A = QPushButton("Set Charge Current to 8A")
        self.btn_charge_8A.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!I-8A@"))
        charge_control_layout.addWidget(self.btn_charge_8A)

        self.btn_charge_12A = QPushButton("Set Charge Current to 12A")
        self.btn_charge_12A.clicked.connect(lambda: send_message_to_write_queue(self.bms_hv_write_queue, "!I-12@"))
        charge_control_layout.addWidget(self.btn_charge_12A)

        left_layout.addWidget(charge_control_box)

        exit_box = QGroupBox("Exit or Change")
        exit_layout = QVBoxLayout()
        exit_box.setLayout(exit_layout)
        self.btn_exit = QPushButton("Exit")
        self.btn_exit.clicked.connect(self.close)
        
        exit_layout.addWidget(self.btn_exit)
        left_layout.addWidget(exit_box)

        right_layout = QVBoxLayout()
        columns_layout.addLayout(right_layout)

        # --- GroupBox: Cell Voltages ---
        cell_voltage_box = QGroupBox("Cell Voltages")
        cell_voltage_layout = QHBoxLayout()
        cell_voltage_box.setLayout(cell_voltage_layout)

        self.table_cell_voltage = QTableWidget()
        self.table_cell_voltage.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_cell_voltage.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_cell_voltage.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_cell_voltage.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_cell_voltage.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        cell_voltage_layout.addWidget(self.table_cell_voltage)

        voltage_info_layout = QGridLayout()
        voltage_info_layout.addWidget(QLabel("Max Voltage:"), 0, 0)
        self.label_cell_max_voltage = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_max_voltage, 0, 1)
        voltage_info_layout.addWidget(QLabel("V"), 0, 2)
        voltage_info_layout.addWidget(QLabel("LTC:"), 0, 3)
        self.label_cell_max_voltage_ltc = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_max_voltage_ltc, 0, 4)
        voltage_info_layout.addWidget(QLabel("Cell:"), 0, 5)
        self.label_cell_max_voltage_cell = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_max_voltage_cell, 0, 6)

        voltage_info_layout.addWidget(QLabel("Min Voltage:"), 1, 0)
        self.label_cell_min_voltage = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_min_voltage, 1, 1)
        voltage_info_layout.addWidget(QLabel("V"), 1, 2)
        voltage_info_layout.addWidget(QLabel("LTC:"), 1, 3)
        self.label_cell_min_voltage_ltc = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_min_voltage_ltc, 1, 4)
        voltage_info_layout.addWidget(QLabel("Cell:"), 1, 5)
        self.label_cell_min_voltage_cell = QLabel("-")
        voltage_info_layout.addWidget(self.label_cell_min_voltage_cell, 1, 6)

        cell_voltage_layout.addLayout(voltage_info_layout)
        right_layout.addWidget(cell_voltage_box)

        # --- GroupBox: Temperatures ---
        temperature_box = QGroupBox("Temperatures")
        temperature_layout = QHBoxLayout()
        temperature_box.setLayout(temperature_layout)

        self.table_temperature = QTableWidget()
        self.table_temperature.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_temperature.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_temperature.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_temperature.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_temperature.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        temperature_layout.addWidget(self.table_temperature)

        temp_info_layout = QHBoxLayout()
        temp_info_layout.addWidget(QLabel("Max Temp:"))
        self.label_max_temperature = QLabel("-")
        temp_info_layout.addWidget(self.label_max_temperature)
        temp_info_layout.addWidget(QLabel("°C"))
        temperature_layout.addLayout(temp_info_layout)
        right_layout.addWidget(temperature_box)

    def init_soc_errors_tab(self):
        layout = QVBoxLayout()
        self.tab_soc_errors.setLayout(layout)

        soc_box = QGroupBox("SOC")
        soc_layout = QVBoxLayout()
        self.table_soc = QTableWidget(1, 4)
        self.table_soc.setHorizontalHeaderLabels(["Min", "Max", "Avg", "Median"])
        self.table_soc.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_soc.verticalHeader().setVisible(False)
        self.table_soc.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        soc_layout.addWidget(self.table_soc)
        soc_box.setLayout(soc_layout)
        layout.addWidget(soc_box)

        error_box = QGroupBox("Errors")
        error_layout = QVBoxLayout()
        self.table_error = QTableWidget()
        self.table_error.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_error.verticalHeader().setVisible(False)
        self.table_error.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        error_layout.addWidget(self.table_error)
        error_box.setLayout(error_layout)
        layout.addWidget(error_box)


    def updateData(self):
        if self.serial_task_connected_event.is_set():
            self.label_connection_status.setText("Connected")
        else:
            self.label_connection_status.setText("Disconnected")

        while not self.bms_hv_read_queue.empty():
            bms_hv_data_json = self.bms_hv_read_queue.get()
            try:
                bms_hv_data_obj = json.loads(bms_hv_data_json, object_hook=lambda d: SimpleNamespace(**d))
                bms_data = BmsHvData(**bms_hv_data_obj.__dict__)
                
                self.updateBasicInfo(bms_data)
                self.updateCellVoltageTable(bms_data)
                self.updateTemperatureTable(bms_data)
                self.updateSOCTab(bms_data)
                self.updateErrorTab(bms_data)     

            except json.decoder.JSONDecodeError:
                print_error(f"Invalid JSON: {bms_hv_data_json}")
                continue
            except TypeError:
                print_error(f"Received JSON is not of type BmsHvData: {bms_hv_data_json}")
                continue



    def updateBasicInfo(self, bms_data: BmsHvData):
        self.label_timestamp.setText(float_to_string_with_precision(bms_data.timestamp / 1000, 3))
        self.label_current.setText(float_to_string_with_precision(bms_data.current, FLOAT_PRECISION))
        self.label_charging_status.setText("On" if bms_data.charging else "Off")
        self.label_balance_status.setText("On" if bms_data.balance else "Off")
        self.label_max_temperature.setText(float_to_string_with_precision(max(bms_data.temperature), FLOAT_PRECISION))
        avg_soc = sum(bms_data.soc) / len(bms_data.soc)
        self.label_soc_avg.setText(float_to_string_with_precision(avg_soc * 100, FLOAT_PRECISION))

        has_error = any([
            bms_data.under_voltage[0],
            bms_data.over_voltage[0],
            bms_data.under_temperature[0],
            bms_data.over_temperature[0],
            bms_data.over_current[0],
            bms_data.current_sensor_disconnected[0]
        ])

        if has_error:
            self.label_errors.setText("Error occured")
            self.label_errors.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.label_errors.setText("None")
            self.label_errors.setStyleSheet("")


    def updateCellVoltageTable(self, bms_data: BmsHvData):
        columns = bms_data.temp_name
        rows = len(bms_data.cell_voltage) // columns

        font = QFont("Sans Serif", 7)

        self.table_cell_voltage.setRowCount(rows)
        self.table_cell_voltage.setColumnCount(columns)
        self.table_cell_voltage.setHorizontalHeaderLabels([f"LTC {j}" for j in range(columns)])
        self.table_cell_voltage.horizontalHeader().setFont(font)
        self.table_cell_voltage.verticalHeader().setFont(font)
        self.table_cell_voltage.verticalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_cell_voltage.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        cell_values = [
            mark_cell_if_discharge(float_to_string_with_precision(v, FLOAT_PRECISION), bms_data.discharge[i])
            for i, v in enumerate(bms_data.cell_voltage)
        ]

        try:
            matrix = np.array(cell_values).reshape((rows, columns))

            for row in range(rows):
                for col in range(columns):
                    item = QTableWidgetItem(str(matrix[row, col]))
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setFont(font)
                    self.table_cell_voltage.setItem(row, col, item)


            for row in range(rows):
                self.table_cell_voltage.setRowHeight(row, 2)

            total_height = rows * 29
            header_height = self.table_cell_voltage.horizontalHeader().height()
            frame_height = 2 * self.table_cell_voltage.frameWidth() 

            self.table_cell_voltage.setFixedHeight(total_height + header_height + frame_height)
            self.table_cell_voltage.resizeColumnsToContents()

            cell_voltage_floats = np.array(bms_data.cell_voltage).reshape((rows, columns))
            max_voltage = np.max(cell_voltage_floats)
            min_voltage = np.min(cell_voltage_floats)

            self.label_cell_max_voltage.setText(float_to_string_with_precision(max_voltage, FLOAT_PRECISION))
            self.label_cell_min_voltage.setText(float_to_string_with_precision(min_voltage, FLOAT_PRECISION))

            max_idx = np.where(cell_voltage_floats == max_voltage)
            min_idx = np.where(cell_voltage_floats == min_voltage)

            if max_idx[0].size > 0:
                self.label_cell_max_voltage_ltc.setText(str(int(max_idx[1][0])))
                self.label_cell_max_voltage_cell.setText(str(int(max_idx[0][0])))

            if min_idx[0].size > 0:
                self.label_cell_min_voltage_ltc.setText(str(int(min_idx[1][0])))
                self.label_cell_min_voltage_cell.setText(str(int(min_idx[0][0])))

            self.table_cell_voltage.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        except ValueError as e:
            print_error(f"Error reshaping cell voltage data: {e}")


    def updateTemperatureTable(self, bms_data: BmsHvData):
        columns = bms_data.temp_name
        rows = len(bms_data.temperature) // columns

        font = QFont("Sans Serif", 7)

        self.table_temperature.setRowCount(rows)
        self.table_temperature.setColumnCount(columns)
        self.table_temperature.setHorizontalHeaderLabels([f"LTC {j}" for j in range(columns)])
        self.table_temperature.horizontalHeader().setFont(font)
        self.table_temperature.verticalHeader().setFont(font)
        self.table_temperature.verticalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_temperature.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        
            
        temp_values = [float_to_string_with_precision(v, FLOAT_PRECISION) for v in bms_data.temperature]

        try:
            matrix = np.array(temp_values).reshape((rows, columns))

            for row in range(rows):
                for col in range(columns):
                    item = QTableWidgetItem(str(matrix[row, col]))
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setFont(font)
                    self.table_temperature.setItem(row, col, item)


            for row in range(rows):
                self.table_temperature.setRowHeight(row, 30)
            self.table_temperature.resizeColumnsToContents()

            total_height = rows * 30
            header_height = self.table_temperature.horizontalHeader().height()
            self.table_temperature.setFixedHeight(total_height + header_height )

            self.table_temperature.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        except ValueError as e:
            print_error(f"Error reshaping temperature data: {e}")

    def updateSOCTab(self, bms_data: BmsHvData):
        soc_values = [
            float_to_string_with_precision(v * 100, FLOAT_PRECISION)
            for v in [min(bms_data.soc), max(bms_data.soc), sum(bms_data.soc) / len(bms_data.soc), median(bms_data.soc)]
        ]
        for col in range(4):
            item = QTableWidgetItem(soc_values[col])
            item.setTextAlignment(Qt.AlignCenter)
            self.table_soc.setItem(0, col, item)

    def updateErrorTab(self, bms_data: BmsHvData):
        errors = [
            ["Under Voltage", str(bms_data.under_voltage[1])] if bms_data.under_voltage[0] else None,
            ["Over Voltage", str(bms_data.over_voltage[1])] if bms_data.over_voltage[0] else None,
            ["Under Temperature", str(bms_data.under_temperature[1])] if bms_data.under_temperature[0] else None,
            ["Over Temperature", str(bms_data.over_temperature[1])] if bms_data.over_temperature[0] else None,
            ["Over Current", str(bms_data.over_current[1])] if bms_data.over_current[0] else None,
            ["Current Sensor", "Disconnected"] if bms_data.current_sensor_disconnected[0] else None,
        ]
        errors = [e for e in errors if e]

        if not errors:
            self.table_error.setRowCount(1)
            self.table_error.setColumnCount(1)
            item = QTableWidgetItem("Brak błędów")
            item.setTextAlignment(Qt.AlignCenter)
            self.table_error.setItem(0, 0, item)
            self.table_error.setSpan(0, 0, 1, 2)
        else:
            self.table_error.setRowCount(len(errors))
            self.table_error.setColumnCount(2)
            self.table_error.setHorizontalHeaderLabels(["Error", "Value"])
            for row, (name, value) in enumerate(errors):
                item_name = QTableWidgetItem(name)
                item_value = QTableWidgetItem(value)
                item_name.setTextAlignment(Qt.AlignCenter)
                item_value.setTextAlignment(Qt.AlignCenter)
                self.table_error.setItem(row, 0, item_name)
                self.table_error.setItem(row, 1, item_value)

    
    def closeEvent(self, event):
        self.main_exit_event.set()
        if self.serial_thread is not None:
            self.serial_thread.join()
        print("Exiting...")
        event.accept()
        QApplication.quit()




'''def main():
    if len(sys.argv) != 2:
        print("Usage: python hv_4_d.py <serial_port>")
        sys.exit(1)

    print("Starting...")

    serial_task_connected_event = threading.Event()
    main_exit_event = threading.Event()

    bms_hv_read_queue = queue.Queue(maxsize=1)
    bms_hv_write_queue = queue.Queue(maxsize=1)

    serial_thread = threading.Thread(
        target=serial_task,
        args=(sys.argv[1], bms_hv_read_queue, bms_hv_write_queue, serial_task_connected_event, main_exit_event),
        daemon=True,
    )
    serial_thread.start()

    app = QApplication(sys.argv)
    main_window = MainWindow(bms_hv_read_queue, bms_hv_write_queue, serial_task_connected_event, main_exit_event, serial_thread)
    main_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()'''
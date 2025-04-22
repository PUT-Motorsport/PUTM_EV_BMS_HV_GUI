import json
import sys
import time
import queue
import threading
from types import SimpleNamespace
from statistics import median
from dataclasses import dataclass

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
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, Qt


IMAGE_PATH = "putm_logo.png"

SERIAL_DATA_IN_FREQ_SEC = 0.250

CELL_VOLTAGE_TABLE_COLUMNS = 15
CELL_VOLTAGE_TABLE_ROWS = 9

TEMPERATURE_TABLE_COLUMNS = 15
TEMPERATURE_TABLE_ROWS = 3

ERROR_TABLE_COLUMNS = 2
ERROR_TABLE_ROWS = 6

SOC_TABLE_COLUMNS = 4
SOC_TABLE_ROWS = 1

FLOAT_PRECISION = 4

@dataclass
class BmsHvData:
    current: float
    acc_voltage: float
    car_voltage: float
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

def to_matrix(l, columns):
    matrix = np.reshape(np.array(l), (columns, -1)).T
    return matrix

def send_message_to_write_queue(write_queue, message):
    try:
        write_queue.put_nowait(message)
    except queue.Full:
        print_error("The write queue is full, the message will be discarded")


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
        
        self.setFixedSize(1600, 1000)

        self.bms_hv_read_queue = bms_hv_read_queue
        self.bms_hv_write_queue = bms_hv_write_queue
        self.serial_task_connected_event = connected_event
        self.main_exit_event = exit_event
        self.serial_thread = serial_thread

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.updateData)
        self.timer.start(500)

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

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

        exit_box = QGroupBox("Exit")
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
        cell_voltage_layout = QVBoxLayout()
        cell_voltage_box.setLayout(cell_voltage_layout)

        self.table_cell_voltage = QTableWidget(CELL_VOLTAGE_TABLE_ROWS, CELL_VOLTAGE_TABLE_COLUMNS)
        self.table_cell_voltage.setEditTriggers(QTableWidget.NoEditTriggers)
        headers = [f"LTC {j}" for j in range(CELL_VOLTAGE_TABLE_COLUMNS)]
        self.table_cell_voltage.setHorizontalHeaderLabels(headers)
        self.table_cell_voltage.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_cell_voltage.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_cell_voltage.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        for col in range(CELL_VOLTAGE_TABLE_COLUMNS):
            self.table_cell_voltage.setColumnWidth(col, 70)
        self.table_cell_voltage.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_cell_voltage.verticalHeader().setDefaultSectionSize(25)
        
        self.table_cell_voltage.setFixedHeight(9 * 25 + 30)

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
        temperature_layout = QVBoxLayout()
        temperature_box.setLayout(temperature_layout)

        self.table_temperature = QTableWidget(TEMPERATURE_TABLE_ROWS, TEMPERATURE_TABLE_COLUMNS)
        self.table_temperature.setEditTriggers(QTableWidget.NoEditTriggers)
        temp_headers = [f"Col {j+1}" for j in range(TEMPERATURE_TABLE_COLUMNS)]
        self.table_temperature.setHorizontalHeaderLabels(temp_headers)
        self.table_temperature.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_temperature.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_temperature.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        for col in range(TEMPERATURE_TABLE_COLUMNS):
            self.table_temperature.setColumnWidth(col, 50)
        self.table_temperature.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_temperature.verticalHeader().setDefaultSectionSize(25)

        temperature_layout.addWidget(self.table_temperature)

        temp_info_layout = QHBoxLayout()
        temp_info_layout.addWidget(QLabel("Max Temp:"))
        self.label_max_temperature = QLabel("-")
        temp_info_layout.addWidget(self.label_max_temperature)
        temp_info_layout.addWidget(QLabel("°C"))
        temperature_layout.addLayout(temp_info_layout)
        right_layout.addWidget(temperature_box)

        # --- GroupBox: SOC ---
        soc_box = QGroupBox("Soc")
        soc_layout = QVBoxLayout()
        soc_box.setLayout(soc_layout)
        self.table_soc = QTableWidget(SOC_TABLE_ROWS, SOC_TABLE_COLUMNS)
        self.table_soc.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_soc.setHorizontalHeaderLabels(["Min", "Max", "Avg", "Median"])
        self.table_soc.verticalHeader().setVisible(False)
        self.table_soc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_soc.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_soc.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        
        for col in range(SOC_TABLE_COLUMNS):
            self.table_soc.setColumnWidth(col, 50)
        soc_layout.addWidget(self.table_soc)
        right_layout.addWidget(soc_box)

        # --- GroupBox: Errors ---
        error_box = QGroupBox("Errors")
        error_layout = QVBoxLayout()
        error_box.setLayout(error_layout)
        self.table_error = QTableWidget(ERROR_TABLE_ROWS, ERROR_TABLE_COLUMNS)
        self.table_error.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_error.setHorizontalHeaderLabels(["Error", "Value"])
        self.table_error.verticalHeader().setVisible(False)
        self.table_error.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        for col in range(ERROR_TABLE_COLUMNS):
            self.table_error.setColumnWidth(col, 100)
        error_layout.addWidget(self.table_error)
        right_layout.addWidget(error_box)

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
            except json.decoder.JSONDecodeError:
                print_error(f"Invalid JSON: {bms_hv_data_json}")
                continue
            except TypeError:
                print_error(f"Received JSON is not of type BmsHvData: {bms_hv_data_json}")
                continue

            self.updateBasicInfo(bms_data)
            self.updateCellVoltageTable(bms_data)
            self.updateTemperatureTable(bms_data)
            self.updateSOCTable(bms_data)
            self.updateErrorTable(bms_data)

    def updateBasicInfo(self, bms_data: BmsHvData):
        self.label_timestamp.setText(float_to_string_with_precision(bms_data.timestamp / 1000, 3))
        self.label_current.setText(float_to_string_with_precision(bms_data.current, FLOAT_PRECISION))
        self.label_charging_status.setText("On" if bms_data.charging else "Off")
        self.label_balance_status.setText("On" if bms_data.balance else "Off")
        self.label_max_temperature.setText(float_to_string_with_precision(max(bms_data.temperature), FLOAT_PRECISION))

    def updateCellVoltageTable(self, bms_data: BmsHvData):
        cell_values = [
            mark_cell_if_discharge(float_to_string_with_precision(v, FLOAT_PRECISION), bms_data.discharge[i])
            for i, v in enumerate(bms_data.cell_voltage)
        ]
        try:
            matrix = np.array(cell_values).reshape((CELL_VOLTAGE_TABLE_ROWS, CELL_VOLTAGE_TABLE_COLUMNS))
        except ValueError:
            print_error("Invalid number of cell voltage entries")
            return

        for row in range(CELL_VOLTAGE_TABLE_ROWS):
            for col in range(CELL_VOLTAGE_TABLE_COLUMNS):
                item = QTableWidgetItem(str(matrix[row, col]))
                item.setTextAlignment(Qt.AlignCenter)
                self.table_cell_voltage.setItem(row, col, item)

        cell_voltage_floats = np.array(bms_data.cell_voltage).reshape((CELL_VOLTAGE_TABLE_ROWS, CELL_VOLTAGE_TABLE_COLUMNS))
        max_voltage = np.max(cell_voltage_floats)
        min_voltage = np.min(cell_voltage_floats)
        self.label_cell_max_voltage.setText(float_to_string_with_precision(max_voltage, FLOAT_PRECISION))
        self.label_cell_min_voltage.setText(float_to_string_with_precision(min_voltage, FLOAT_PRECISION))
        max_idx = np.where(cell_voltage_floats == max_voltage)
        if max_idx[0].size > 0:
            self.label_cell_max_voltage_ltc.setText(str(int(max_idx[1][0])))
            self.label_cell_max_voltage_cell.setText(str(int(max_idx[0][0])))
        min_idx = np.where(cell_voltage_floats == min_voltage)
        if min_idx[0].size > 0:
            self.label_cell_min_voltage_ltc.setText(str(int(min_idx[1][0])))
            self.label_cell_min_voltage_cell.setText(str(int(min_idx[0][0])))

    def updateTemperatureTable(self, bms_data: BmsHvData):
        temp_values = [float_to_string_with_precision(v, FLOAT_PRECISION) for v in bms_data.temperature]
        try:
            matrix_temp = np.array(temp_values).reshape((TEMPERATURE_TABLE_ROWS, TEMPERATURE_TABLE_COLUMNS))
        except ValueError:
            print_error("Invalid number of temperature entries")
            return

        for row in range(TEMPERATURE_TABLE_ROWS):
            for col in range(TEMPERATURE_TABLE_COLUMNS):
                item = QTableWidgetItem(str(matrix_temp[row, col]))
                item.setTextAlignment(Qt.AlignCenter)
                self.table_temperature.setItem(row, col, item)

    def updateSOCTable(self, bms_data: BmsHvData):
        soc_values = [
            float_to_string_with_precision(v * 100, FLOAT_PRECISION)
            for v in [min(bms_data.soc), max(bms_data.soc), sum(bms_data.soc) / len(bms_data.soc), median(bms_data.soc)]
        ]
        for col in range(SOC_TABLE_COLUMNS):
            item = QTableWidgetItem(soc_values[col])
            item.setTextAlignment(Qt.AlignCenter)
            self.table_soc.setItem(0, col, item)

    def updateErrorTable(self, bms_data: BmsHvData):
        errors = [
            ([e[0], str(e[2])] if e[1] == 1 else ["-", "-"])
            for e in [
                ["Under Voltage", bms_data.under_voltage[0], bms_data.under_voltage[1]],
                ["Over Voltage", bms_data.over_voltage[0], bms_data.over_voltage[1]],
                ["Under Temperature", bms_data.under_temperature[0], bms_data.under_temperature[1]],
                ["Over Temperature", bms_data.over_temperature[0], bms_data.over_temperature[1]],
                ["Over Current", bms_data.over_current[0], bms_data.over_current[1]],
                ["Current Sensor", bms_data.current_sensor_disconnected[0], "Disconnected"],
            ]
        ]
        for row in range(ERROR_TABLE_ROWS):
            for col in range(ERROR_TABLE_COLUMNS):
                item = QTableWidgetItem(errors[row][col])
                item.setTextAlignment(Qt.AlignCenter)
                self.table_error.setItem(row, col, item)

    def closeEvent(self, event):
        self.main_exit_event.set()
        self.serial_thread.join()
        print_ok("Exiting...")
        event.accept()

def main():
    if len(sys.argv) != 2:
        print_error("Usage: python main_pyqt.py <serial_port>")
        sys.exit(1)

    print_ok("Starting...")

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
    main()

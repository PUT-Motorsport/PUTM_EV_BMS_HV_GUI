""" This is the main file for the BMS HV Utility. It is used to display the data from the BMS HV and to change its settings"""
import json
from types import SimpleNamespace
from dataclasses import dataclass
import queue
import threading
import sys
import time
import PySimpleGUI as sg
import serial
from colorama import Fore, Style
import numpy as np
from statistics import median

sg.theme("Material2")
sg.set_options(font=("Helvetica", 13))

IMAGE_PATH = "putm_logo.png"

STANDARD_TEXT_WIDTH = 8

TABLE_COLUMNS = 15
CELL_VOLTAGE_TABLE_ROWS = 9
TEMPERATURE_TABLE_ROWS = 3

KEY_CONNECTION_STATUS = "-CONNECTION-STATUS-"
KEY_TIMESTAMP = "-TIMESTAMP-"
KEY_MAX_VOLTAGE = "-MAX-VOLTAGE-"
KEY_MIN_VOLTAGE = "-MIN-VOLTAGE-"
KEY_MAX_TEMPERATURE = "-MAX-TEMPERATURE-"
KEY_CURRENT = "-CURRENT-"
KEY_ACC_VOLTAGE = "-ACC-VOLTAGE-"
KEY_CAR_VOLTAGE = "-CAR-VOLTAGE-"
KEY_SOC_MIN = "-SOC-MIN-"
KEY_SOC_MAX = "-SOC-MAX-"
KEY_SOC_AVG = "-SOC-AVG-"
KEY_SOC_MEDIAN = "-SOC-MEDIAN-"
KEY_CELL_VOLTAGE = "-CELL-VOLTAGE-"
KEY_TEMPERATURE = "-TEMPERATURE-"
KEY_CHARGING_STATUS = "-CHARGING-STATUS-"
KEY_BALANCING_STATUS = "-BALANCING-STATUS-"


@dataclass
class BmsHvData:
    """Dataclass for BMS HV data"""

    current: float
    acc_voltage: float
    car_voltage: float
    soc: list[float]
    cell_voltage: list[float]
    temperature: list[float]


basic_info = [
    [sg.Text("Connection Status: "), sg.Text("-", key="-CONNECTION-STATUS-")],
    [
        sg.Text("Timestamp:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_TIMESTAMP, justification="c"
        ),
        sg.Text("s"),
    ],
    [
        sg.Text("Max Voltage:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_MAX_VOLTAGE, justification="c"
        ),
        sg.Text("V"),
    ],
    [
        sg.Text("Min Voltage:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_MIN_VOLTAGE, justification="c"
        ),
        sg.Text("V"),
    ],
    [
        sg.Text("Max Temp:"),
        sg.Text(
            "-",
            size=(STANDARD_TEXT_WIDTH, 1),
            key=KEY_MAX_TEMPERATURE,
            justification="c",
        ),
        sg.Text("°C"),
    ],
    [
        sg.Text("Current:"),
        sg.Text("-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_CURRENT, justification="c"),
        sg.Text("A"),
    ],
    [
        sg.Text("Acc Voltage:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_ACC_VOLTAGE, justification="c"
        ),
        sg.Text("V"),
    ],
    [
        sg.Text("Car Voltage:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_CAR_VOLTAGE, justification="c"
        ),
        sg.Text("V"),
    ],
    [
        sg.Text("Soc Min:"),
        sg.Text("-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_SOC_MIN, justification="c"),
        sg.Text("%"),
    ],
    [
        sg.Text("Soc Max:"),
        sg.Text("-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_SOC_MAX, justification="c"),
        sg.Text("%"),
    ],
    [
        sg.Text("Soc Avg:"),
        sg.Text("-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_SOC_AVG, justification="c"),
        sg.Text("%"),
    ],
    [
        sg.Text("Soc Median:"),
        sg.Text(
            "-", size=(STANDARD_TEXT_WIDTH, 1), key=KEY_SOC_MEDIAN, justification="c"
        ),
        sg.Text("%"),
    ],
    [
        sg.Text("Charging Status:"),
        sg.Text(
            "-",
            size=(STANDARD_TEXT_WIDTH, 1),
            key=KEY_CHARGING_STATUS,
            justification="c",
        ),
    ],
    [
        sg.Text("Balancing Status:"),
        sg.Text(
            "-",
            size=(STANDARD_TEXT_WIDTH, 1),
            key=KEY_BALANCING_STATUS,
            justification="c",
        ),
    ],
]

cell_voltage = [
    [
        sg.Table(
            values=[
                ["-" for i in range(TABLE_COLUMNS)]
                for j in range(CELL_VOLTAGE_TABLE_ROWS)
            ],
            headings=[f"LTC {j+1}" for j in range(TABLE_COLUMNS)],
            select_mode=sg.TABLE_SELECT_MODE_NONE,
            display_row_numbers=True,
            auto_size_columns=False,
            justification="center",
            num_rows=CELL_VOLTAGE_TABLE_ROWS,
            enable_events=False,
            hide_vertical_scroll=True,
            key=KEY_CELL_VOLTAGE,
            def_col_width=STANDARD_TEXT_WIDTH,
        )
    ]
]

temperature = [
    [
        sg.Table(
            values=[
                ["-" for i in range(TABLE_COLUMNS)]
                for j in range(TEMPERATURE_TABLE_ROWS)
            ],
            headings=[f"Col {j+1}" for j in range(TABLE_COLUMNS)],
            select_mode=sg.TABLE_SELECT_MODE_NONE,
            display_row_numbers=True,
            auto_size_columns=False,
            justification="center",
            num_rows=TEMPERATURE_TABLE_ROWS,
            enable_events=False,
            hide_vertical_scroll=True,
            key=KEY_TEMPERATURE,
            def_col_width=STANDARD_TEXT_WIDTH,
        )
    ]
]

charge_control = [
    [sg.Button("Start Charging")],
    [sg.Button("Stop Charging")],
    [sg.Button("Start Balance")],
    [sg.Button("Stop Balance")],
    [sg.Button("Set Charge Current to 1A")],
    [sg.Button("Set Charge Current to 2A")],
    [sg.Button("Set Charge Current to 4A")],
    [sg.Button("Set Charge Current to 8A")],
    [sg.Button("Set Charge Current to 12A")],
]

exit_button = [[sg.Button("Exit")]]

image = [sg.Image(IMAGE_PATH)]

frame_basic_info = [sg.Frame("Basic Info", basic_info)]
frame_charge_control = [sg.Frame("Charge control", charge_control)]

frame_cell_voltage = [sg.Frame("Cell Voltages", cell_voltage)]
frame_temperature = [sg.Frame("Temperatures", temperature)]
frame_exit_button = [sg.Frame("Exit", exit_button)]

column_left = sg.Column(
    [frame_basic_info, frame_charge_control, frame_exit_button],
    element_justification="l",
    vertical_alignment="top",
)
column_right = sg.Column(
    [frame_cell_voltage, frame_temperature],
    element_justification="r",
    vertical_alignment="top",
)

layout = [
    image,
    [column_left, sg.VerticalSeparator(pad=None), column_right],
]
window = sg.Window("BMS HV Utility", layout, element_justification="c")


def float_to_string_with_precision(value, precision):
    """Converts a float to a string with the specified precision"""
    return f"{value:.{precision}f}"


def mark_cell_if_balancing(value, is_balancing):
    """Marks a cell if it is balancing"""
    return (f"|{value}|") if is_balancing else value


def print_ok(msg):
    """Prints an ok message"""
    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}")


def print_error(msg):
    """Prints an error message"""
    print(f"{Fore.RED}{msg}{Style.RESET_ALL}")


def print_warning(msg):
    """Prints a warning message"""
    print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")


def to_matrix(l, columns):
    """Converts a list to a matrix with the specified number of columns"""
    matrix = np.reshape(np.array(l), (columns, -1)).T
    return matrix.tolist()


def send_message_to_write_queue(write_queue, message):
    """This function is used to send a message to the write queue"""
    try:
        write_queue.put_nowait(message)
    except queue.Full:
        print_error("The write queue is full, the message will be discarded")


def serial_task(port, read_queue, write_queue, connected_event, exit_event):
    """This function is used to read data from and to write data to the serial port"""
    write_prefix = "WRITE: "
    read_prefix = "READ: "

    ser = serial.Serial()
    ser.port = port
    # this value has to be bigger than frequency of sending data from BMS HV
    ser.timeout = 1.2

    while not ser.is_open:
        if exit_event.is_set():
            return
        try:
            ser.open()
            connected_event.set()
            print_ok("Serial port opened")
        except serial.serialutil.SerialException:
            print_error("Failed to open serial port")
            time.sleep(1)
            continue

    while True:
        if exit_event.is_set():
            ser.close()
            return
        try:
            # Write data
            try:
                data = write_queue.get_nowait()
                ser.write(data.encode("utf-8"))
                print_ok(f"{write_prefix} New data sent to the serial port")
            except queue.Empty:
                print_warning(f"{write_prefix} Nothing to send to the serial port")

            # Read data
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
                print_warning("Read queue is full")

        except serial.serialutil.SerialException:
            connected_event.clear()
            print_error("Serial port was closed")
            while True:
                if exit_event.is_set():
                    return
                try:
                    ser.open()
                    connected_event.set()
                    break
                except serial.serialutil.SerialException:
                    print_error("Failed to reopen serial port")
                    time.sleep(1)
                    continue


def main():
    """Main function"""
    if len(sys.argv) != 2:
        print_error("Usage: python3 pyserial_tests.py <serial_port>")
        sys.exit(1)

    print_ok("Starting...")

    serial_task_connected_event = threading.Event()
    main_exit_event = threading.Event()

    bms_hv_data_queue = queue.Queue(maxsize=1)
    bms_hv_settings_queue = queue.Queue(maxsize=1)

    serial_task_thread = threading.Thread(
        target=serial_task,
        args=(
            sys.argv[1],
            bms_hv_data_queue,
            bms_hv_settings_queue,
            serial_task_connected_event,
            main_exit_event,
        ),
        daemon=True,
    )
    serial_task_thread.start()

    while True:
        event, values = window.read(timeout=1000)

        if serial_task_connected_event.is_set():
            window[KEY_CONNECTION_STATUS].update("Connected")
        else:
            window[KEY_CONNECTION_STATUS].update("Disconnected")

        if event == sg.WINDOW_CLOSED or event == "Exit":
            break

        elif event == "Start Charging":
            send_message_to_write_queue(bms_hv_settings_queue, "!C-ON@")

        elif event == "Stop Charging":
            send_message_to_write_queue(bms_hv_settings_queue, "!C-OF@")

        elif event == "Start Balance":
            send_message_to_write_queue(bms_hv_settings_queue, "!B-ON@")

        elif event == "Stop Balance":
            send_message_to_write_queue(bms_hv_settings_queue, "!B-OF@")

        elif event == "Set Charge Current to 1A":
            send_message_to_write_queue(bms_hv_settings_queue, "!I-1A@")

        elif event == "Set Charge Current to 2A":
            send_message_to_write_queue(bms_hv_settings_queue, "!I-2A@")

        elif event == "Set Charge Current to 4A":
            send_message_to_write_queue(bms_hv_settings_queue, "!I-4A@")

        elif event == "Set Charge Current to 8A":
            send_message_to_write_queue(bms_hv_settings_queue, "!I-8A@")

        elif event == "Set Charge Current to 12A":
            send_message_to_write_queue(bms_hv_settings_queue, "!I-12@")

        if not bms_hv_data_queue.empty():
            bms_hv_data_json = bms_hv_data_queue.get()
            try:
                bms_hv_data = json.loads(
                    bms_hv_data_json, object_hook=lambda d: SimpleNamespace(**d)
                )
                bms_hv_data = BmsHvData(**bms_hv_data.__dict__)

            except json.decoder.JSONDecodeError:
                print_error(f"Invalid JSON: {bms_hv_data_json}")
                continue

            except TypeError:
                print_error(
                    f"Received JSON is not of type BmsHvData: {bms_hv_data_json}"
                )
                continue

            window[KEY_MAX_VOLTAGE].update(
                float_to_string_with_precision(max(bms_hv_data.cell_voltage), 3)
            )
            window[KEY_MIN_VOLTAGE].update(
                float_to_string_with_precision(min(bms_hv_data.cell_voltage), 3)
            )
            window[KEY_MAX_TEMPERATURE].update(
                float_to_string_with_precision(max(bms_hv_data.temperature), 3)
            )
            window[KEY_CURRENT].update(
                float_to_string_with_precision(bms_hv_data.current, 3)
            )
            window[KEY_ACC_VOLTAGE].update(
                float_to_string_with_precision(bms_hv_data.acc_voltage, 3)
            )
            window[KEY_CAR_VOLTAGE].update(
                float_to_string_with_precision(bms_hv_data.car_voltage, 3)
            )
            window[KEY_SOC_MIN].update(
                float_to_string_with_precision(min(bms_hv_data.soc) * 100, 3)
            )
            window[KEY_SOC_MAX].update(
                float_to_string_with_precision(max(bms_hv_data.soc) * 100, 3)
            )
            window[KEY_SOC_AVG].update(
                float_to_string_with_precision(
                    (sum(bms_hv_data.soc) / len(bms_hv_data.soc)) * 100, 3
                )
            )
            window[KEY_SOC_MEDIAN].update(
                float_to_string_with_precision(median(bms_hv_data.soc) * 100, 3)
            )

            window[KEY_CELL_VOLTAGE].update(
                values=to_matrix(
                    [
                        mark_cell_if_balancing(float_to_string_with_precision(v, 3), True)
                        for v in bms_hv_data.cell_voltage
                    ],
                    TABLE_COLUMNS,
                )
            )

            window[KEY_TEMPERATURE].update(
                values=to_matrix(
                    [
                        float_to_string_with_precision(v, 3)
                        for v in bms_hv_data.temperature
                    ],
                    TABLE_COLUMNS,
                )
            )

    main_exit_event.set()
    serial_task_thread.join()

    window.close()
    print_ok("Exiting...")
    return 0


if __name__ == "__main__":
    main()

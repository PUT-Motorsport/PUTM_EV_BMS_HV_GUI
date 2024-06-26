""" This is the main file for the BMS HV Utility. It is used to display the data from the BMS HV and to change its settings"""
import json
from types import SimpleNamespace
from dataclasses import dataclass
import queue
import threading
import sys
import time
from statistics import median
import PySimpleGUI as sg
import serial
from colorama import Fore, Style
import numpy as np

sg.theme("Material2")
sg.set_options(font=("Helvetica", 11))

IMAGE_PATH = "putm_logo.png"

SERIAL_DATA_IN_FREQ_SEC = 0.250

STANDARD_TEXT_WIDTH = 9

CELL_VOLTAGE_TABLE_COLUMNS = 15
CELL_VOLTAGE_TABLE_ROWS = 9

TEMPERATURE_TABLE_COLUMNS = 15
TEMPERATURE_TABLE_ROWS = 3

ERROR_TABLE_COLUMNS = 2
ERROR_TABLE_ROWS = 6

SOC_TABLE_COLUMNS = 4
SOC_TABLE_ROWS = 1

FLOAT_PRECISION = 4

KEY_CONNECTION_STATUS = "-CONNECTION-STATUS-"
KEY_TIMESTAMP = "-TIMESTAMP-"

KEY_CELL_MAX_VOLTAGE = "-MAX-VOLTAGE-"
KEY_CELL_MAX_VOLTAGE_LTC = "-MAX-VOLTAGE-LTC-"
KEY_CELL_MAX_VOLTAGE_CELL = "-MAX-VOLTAGE-CELL-"

KEY_CELL_MIN_VOLTAGE = "-MIN-VOLTAGE-"
KEY_CELL_MIN_VOLTAGE_LTC = "-MIN-VOLTAGE-LTC-"
KEY_CELL_MIN_VOLTAGE_CELL = "-MIN-VOLTAGE-CELL-"

KEY_MAX_TEMPERATURE = "-MAX-TEMPERATURE-"
KEY_CURRENT = "-CURRENT-"
KEY_ACC_VOLTAGE = "-ACC-VOLTAGE-"
KEY_CAR_VOLTAGE = "-CAR-VOLTAGE-"
KEY_SOC = "-SOC-"
KEY_CELL_VOLTAGE = "-CELL-VOLTAGE-"
KEY_TEMPERATURE = "-TEMPERATURE-"
KEY_ERROR = "-CELL-ERRORS-"
KEY_CHARGING_STATUS = "-CHARGING-STATUS-"
KEY_BALANCE_STATUS = "-BALANCE-STATUS-"


@dataclass
class BmsHvData:
    """Dataclass for BMS HV data"""

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


basic_info = [
    [
        sg.Text("Connection Status: "),
        sg.Text("-", size=(12, 1), key=KEY_CONNECTION_STATUS, justification="l"),
    ],
    [
        sg.Text("Timestamp:"),
        sg.Text("-", auto_size_text=True, key=KEY_TIMESTAMP),
        sg.Text("s"),
    ],
    [
        sg.Text("Current:"),
        sg.Text("-", auto_size_text=True, key=KEY_CURRENT),
        sg.Text("A"),
    ],
    # [
    #     sg.Text("Acc Voltage:"),
    #     sg.Text("-", auto_size_text=True, key=KEY_ACC_VOLTAGE),
    #     sg.Text("V"),
    # ],
    # [
    #     sg.Text("Car Voltage:"),
    #     sg.Text("-", auto_size_text=True, key=KEY_CAR_VOLTAGE),
    #     sg.Text("V"),
    # ],
    [
        sg.Text("Charging Status:"),
        sg.Text("-", auto_size_text=True, key=KEY_CHARGING_STATUS),
    ],
    [
        sg.Text("Balance Status:"),
        sg.Text("-", auto_size_text=True, key=KEY_BALANCE_STATUS),
    ],
]

cell_voltage = [
    [
        sg.Table(
            values=[
                ["-" for i in range(CELL_VOLTAGE_TABLE_COLUMNS)]
                for j in range(CELL_VOLTAGE_TABLE_ROWS)
            ],
            headings=[f"LTC {j}" for j in range(CELL_VOLTAGE_TABLE_COLUMNS)],
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
    ],
    [
        sg.Text("Max Voltage:"),
        sg.Text("-", key=KEY_CELL_MAX_VOLTAGE, justification="l"),
        sg.Text("V"),
        sg.Text("LTC:"),
        sg.Text("-", key=KEY_CELL_MAX_VOLTAGE_LTC, justification="l"),
        sg.Text("Cell:"),
        sg.Text("-", key=KEY_CELL_MAX_VOLTAGE_CELL, justification="l"),
    ],
    [
        sg.Text("Min Voltage:"),
        sg.Text("-", key=KEY_CELL_MIN_VOLTAGE, justification="l"),
        sg.Text("V"),
        sg.Text("LTC:"),
        sg.Text("-", key=KEY_CELL_MIN_VOLTAGE_LTC, justification="l"),
        sg.Text("Cell:"),
        sg.Text("-", key=KEY_CELL_MIN_VOLTAGE_CELL, justification="l"),
    ],
]

temperature = [
    [
        sg.Table(
            values=[
                ["-" for i in range(TEMPERATURE_TABLE_COLUMNS)]
                for j in range(TEMPERATURE_TABLE_ROWS)
            ],
            headings=[f"Col {j+1}" for j in range(TEMPERATURE_TABLE_COLUMNS)],
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
    ],
    [
        sg.Text("Max Temp:"),
        sg.Text("-", key=KEY_MAX_TEMPERATURE, justification="L"),
        sg.Text("°C"),
    ],
]

error = [
    [
        sg.Table(
            values=[
                ["-" for i in range(ERROR_TABLE_COLUMNS)]
                for j in range(ERROR_TABLE_ROWS)
            ],
            headings=["Error", "Value"],
            select_mode=sg.TABLE_SELECT_MODE_NONE,
            display_row_numbers=False,
            auto_size_columns=False,
            justification="r",
            num_rows=ERROR_TABLE_ROWS,
            enable_events=False,
            hide_vertical_scroll=True,
            key=KEY_ERROR,
            def_col_width=14,
        )
    ]
]

soc = [
    [
        sg.Table(
            values=[
                ["-" for i in range(SOC_TABLE_COLUMNS)] for j in range(SOC_TABLE_ROWS)
            ],
            headings=[
                "Min",
                "Max",
                "Avg",
                "Median",
            ],
            select_mode=sg.TABLE_SELECT_MODE_NONE,
            display_row_numbers=False,
            auto_size_columns=False,
            justification="c",
            num_rows=SOC_TABLE_ROWS,
            enable_events=False,
            hide_vertical_scroll=True,
            key=KEY_SOC,
            def_col_width=STANDARD_TEXT_WIDTH,
        )
    ]
]


charge_control = [
    [sg.Button("Full Battery Soc")],
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

image = sg.Image(IMAGE_PATH)

frame_basic_info = sg.Frame("Basic Info", basic_info)
frame_charge_control = sg.Frame("Charge control", charge_control)
frame_exit_button = sg.Frame("Exit", exit_button)

frame_cell_voltage = sg.Frame("Cell Voltages", cell_voltage)
frame_temperature = sg.Frame("Temperatures", temperature)
frame_error = sg.Frame("Errors", error)
frame_soc = sg.Frame("Soc", soc)

column_left = sg.Column(
    [[frame_basic_info], [frame_charge_control], [frame_exit_button]],
    element_justification="l",
    vertical_alignment="top",
)
column_right = sg.Column(
    [[frame_cell_voltage], [frame_temperature], [frame_soc], [frame_error]],
    element_justification="l",
    vertical_alignment="top",
)

layout = [
    [image],
    [column_left, sg.VerticalSeparator(pad=None), column_right],
]
window = sg.Window("BMS HV Utility", layout, element_justification="c")


def float_to_string_with_precision(value, precision):
    """Converts a float to a string with the specified precision"""
    return f"{value:.{precision}f}"


def mark_cell_if_discharge(value, is_discharging):
    """Marks a cell if it is discharging"""
    return (f"#{value}#") if is_discharging else value


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
    return matrix


def send_message_to_write_queue(write_queue, message):
    """This function is used to send a message to the write queue"""
    try:
        write_queue.put_nowait(message)
    except queue.Full:
        print_error("The write queue is full, the message will be discarded")


def serial_task(port, read_queue, write_queue, connected_event, exit_event):
    """This function is used to read data from and to write data to the serial port"""
    serial_task_prefix = "SERIAL TASK: "
    write_prefix = "WRITE: "
    read_prefix = "READ: "
    keep_alive_prefix = "KEEP_ALIVE: "
    keep_alive_message = "!C-CC@"

    ser = serial.Serial()
    ser.port = port
    # this value has to be bigger than frequency of sending data from BMS HV
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

            # Keep alive
            ser.write(keep_alive_message.encode("utf-8"))
            print_ok(f"{keep_alive_prefix} Keep alive message sent to the serial port")

            # Write data
            try:
                data = write_queue.get_nowait()
                ser.write(data.encode("utf-8"))
                print_ok(f"{write_prefix} New data sent to the serial port: {data}")
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
                    print_error(
                        f"{serial_task_prefix} Failed to reopen serial port: {port}"
                    )
                    time.sleep(1)
                    continue


def main():
    """Main function"""
    if len(sys.argv) != 2:
        print_error("Usage: python main.py <serial_port>")
        sys.exit(1)

    print_ok("Starting...")

    serial_task_connected_event = threading.Event()
    main_exit_event = threading.Event()

    bms_hv_read_queue = queue.Queue(maxsize=1)
    bms_hv_write_queue = queue.Queue(maxsize=1)

    serial_task_thread = threading.Thread(
        target=serial_task,
        args=(
            sys.argv[1],
            bms_hv_read_queue,
            bms_hv_write_queue,
            serial_task_connected_event,
            main_exit_event,
        ),
        daemon=True,
    )
    serial_task_thread.start()

    while True:
        event, values = window.read(timeout=500)

        if serial_task_connected_event.is_set():
            window[KEY_CONNECTION_STATUS].update("Connected")
        else:
            window[KEY_CONNECTION_STATUS].update("Disconnected")

        if event == sg.WINDOW_CLOSED or event == "Exit":
            break
        
        elif event == "Full Battery Soc":
            send_message_to_write_queue(bms_hv_write_queue, "!B-FC@")

        elif event == "Start Charging":
            send_message_to_write_queue(bms_hv_write_queue, "!C-ON@")

        elif event == "Stop Charging":
            send_message_to_write_queue(bms_hv_write_queue, "!C-OF@")

        elif event == "Start Balance":
            send_message_to_write_queue(bms_hv_write_queue, "!B-ON@")

        elif event == "Stop Balance":
            send_message_to_write_queue(bms_hv_write_queue, "!B-OF@")

        elif event == "Set Charge Current to 1A":
            send_message_to_write_queue(bms_hv_write_queue, "!I-1A@")

        elif event == "Set Charge Current to 2A":
            send_message_to_write_queue(bms_hv_write_queue, "!I-2A@")

        elif event == "Set Charge Current to 4A":
            send_message_to_write_queue(bms_hv_write_queue, "!I-4A@")

        elif event == "Set Charge Current to 8A":
            send_message_to_write_queue(bms_hv_write_queue, "!I-8A@")

        elif event == "Set Charge Current to 12A":
            send_message_to_write_queue(bms_hv_write_queue, "!I-12@")

        if not bms_hv_read_queue.empty():
            bms_hv_data_json = bms_hv_read_queue.get()
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

            # BASIC INFO
            window[KEY_TIMESTAMP].update(
                float_to_string_with_precision((bms_hv_data.timestamp / 1000), 3)
            )
            window[KEY_MAX_TEMPERATURE].update(
                float_to_string_with_precision(
                    max(bms_hv_data.temperature), FLOAT_PRECISION
                )
            )
            window[KEY_CURRENT].update(
                float_to_string_with_precision(bms_hv_data.current, FLOAT_PRECISION)
            )
            # window[KEY_ACC_VOLTAGE].update(
            #     float_to_string_with_precision(bms_hv_data.acc_voltage, FLOAT_PRECISION)
            # )
            # window[KEY_CAR_VOLTAGE].update(
            #     float_to_string_with_precision(bms_hv_data.car_voltage, FLOAT_PRECISION)
            # )
            window[KEY_CHARGING_STATUS].update("On" if bms_hv_data.charging else "Off")
            window[KEY_BALANCE_STATUS].update("On" if bms_hv_data.balance else "Off")

            # CELL VOLTAGE TABLE
            window[KEY_CELL_VOLTAGE].update(
                values=to_matrix(
                    [
                        [
                            mark_cell_if_discharge(
                                float_to_string_with_precision(v, FLOAT_PRECISION),
                                bms_hv_data.discharge[i],
                            )
                            for i, v in enumerate(bms_hv_data.cell_voltage)
                        ]
                    ],
                    CELL_VOLTAGE_TABLE_COLUMNS,
                ).tolist()
            )
            window[KEY_CELL_MAX_VOLTAGE].update(
                float_to_string_with_precision(
                    max(bms_hv_data.cell_voltage), FLOAT_PRECISION
                )
            )
            max_cell_num, max_ltc_num = np.where(
                to_matrix(bms_hv_data.cell_voltage, CELL_VOLTAGE_TABLE_COLUMNS)
                == max(bms_hv_data.cell_voltage)
            )
            window[KEY_CELL_MAX_VOLTAGE_LTC].update(max_ltc_num[0])
            window[KEY_CELL_MAX_VOLTAGE_CELL].update(max_cell_num[0])

            window[KEY_CELL_MIN_VOLTAGE].update(
                float_to_string_with_precision(
                    min(bms_hv_data.cell_voltage), FLOAT_PRECISION
                )
            )
            min_cell_num, min_ltc_num = np.where(
                to_matrix(bms_hv_data.cell_voltage, CELL_VOLTAGE_TABLE_COLUMNS)
                == min(bms_hv_data.cell_voltage)
            )
            window[KEY_CELL_MIN_VOLTAGE_LTC].update(min_ltc_num[0])
            window[KEY_CELL_MIN_VOLTAGE_CELL].update(min_cell_num[0])

            # TEMPERATURE TABLE
            window[KEY_TEMPERATURE].update(
                values=to_matrix(
                    [
                        float_to_string_with_precision(v, FLOAT_PRECISION)
                        for v in bms_hv_data.temperature
                    ],
                    TEMPERATURE_TABLE_COLUMNS,
                ).tolist()
            )

            # SOC TABLE
            window[KEY_SOC].update(
                values=to_matrix(
                    [
                        [
                            float_to_string_with_precision(v * 100, FLOAT_PRECISION)
                            for v in [
                                min(bms_hv_data.soc),
                                max(bms_hv_data.soc),
                                sum(bms_hv_data.soc) / len(bms_hv_data.soc),
                                median(bms_hv_data.soc),
                            ]
                        ]
                    ],
                    SOC_TABLE_COLUMNS,
                ).tolist()
            )

            errors = [
                ([e[0], e[2]] if e[1] == 1 else ["-", "-"])
                for e in [
                    [
                        "Under Voltage",
                        bms_hv_data.under_voltage[0],
                        bms_hv_data.under_voltage[1],
                    ],
                    [
                        "Over Voltage",
                        bms_hv_data.over_voltage[0],
                        bms_hv_data.over_voltage[1],
                    ],
                    [
                        "Under Temperature",
                        bms_hv_data.under_temperature[0],
                        bms_hv_data.under_temperature[1],
                    ],
                    [
                        "Over Temperature",
                        bms_hv_data.over_temperature[0],
                        bms_hv_data.over_temperature[1],
                    ],
                    [
                        "Over Current",
                        bms_hv_data.over_current[0],
                        bms_hv_data.over_current[1],
                    ],
                    [
                        "Current Sensor",
                        bms_hv_data.current_sensor_disconnected[0],
                        "Disconnected",
                    ],
                ]
            ]

            # ERROR TABLE
            window[KEY_ERROR].update(values=errors)

    main_exit_event.set()
    serial_task_thread.join()

    window.close()
    print_ok("Exiting...")
    return 0


if __name__ == "__main__":
    main()

''' This is the main file for the BMS HV Utility. It is used to display the data from the BMS HV and to change its settings'''
import json
from types import SimpleNamespace
from dataclasses import dataclass
import queue
import threading
import sys
import PySimpleGUI as sg
import serial
from colorama import Fore, Style

sg.theme("Material2")
sg.set_options(font=("Helvetica", 13))

IMAGE_PATH = "putm_logo.png"

STANDARD_TEXT_WIDTH = 7

TABLE_COLUMNS = 15
CELL_VOLTAGE_TABLE_ROWS = 9
TEMPERATURE_TABLE_ROWS = 3

KEY_MAX_VOLTAGE = "-MAX-VOLTAGE-"
KEY_MIN_VOLTAGE = "-MIN-VOLTAGE-"
KEY_CURRENT = "-CURRENT-"
KEY_ACC_VOLTAGE = "-ACC-VOLTAGE-"
KEY_CAR_VOLTAGE = "-CAR-VOLTAGE-"
KEY_SOC = "-SOC-"
KEY_CELL_VOLTAGE = "-CELL-VOLTAGE-"
KEY_TEMPERATURE = "-TEMPERATURE-"


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
    [
        sg.Text("Max Voltage:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_MAX_VOLTAGE, justification="c"),
        sg.Text("V"),
    ],
    [
        sg.Text("Min Voltage:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_MIN_VOLTAGE, justification="c"),
        sg.Text("V"),
    ],
    [
        sg.Text("Current:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_CURRENT, justification="c"),
        sg.Text("A"),
    ],
    [
        sg.Text("Acc Voltage:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_ACC_VOLTAGE, justification="c"),
        sg.Text("V"),
    ],
    [
        sg.Text("Car Voltage:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_CAR_VOLTAGE, justification="c"),
        sg.Text("V"),
    ],
    [
        sg.Text("Soc:"),
        sg.Text("-", size = (STANDARD_TEXT_WIDTH, 1) ,key=KEY_SOC, justification="c"),
        sg.Text("%"),
    ],
]

cell_voltage = [
    [
        sg.Table(
            values=[
                ["-" for i in range(TABLE_COLUMNS)]
                for j in range(CELL_VOLTAGE_TABLE_ROWS)
            ],
            headings=[f"Col {j+1}" for j in range(TABLE_COLUMNS)],
            select_mode=sg.TABLE_SELECT_MODE_NONE,
            display_row_numbers=True,
            auto_size_columns=False,
            justification="center",
            num_rows=CELL_VOLTAGE_TABLE_ROWS,
            enable_events=False,
            hide_vertical_scroll=True,
            key=KEY_CELL_VOLTAGE,
            def_col_width = STANDARD_TEXT_WIDTH,
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
            def_col_width = STANDARD_TEXT_WIDTH,
        )
    ]
]

charge_control = [[sg.Button("Start Charging")], [sg.Button("Stop Charging")]]
exit_button = [[sg.Button("Exit")]]
image = [sg.Image(IMAGE_PATH)]

frame_basic_info = [sg.Frame("Basic Info", basic_info)]
frame_charge_control = [sg.Frame("Charge control", charge_control)]

frame_cell_voltage = [sg.Frame("Cell Voltages", cell_voltage)]
frame_temperature = [sg.Frame("Temperatures", temperature)]
frame_exit_button = [sg.Frame("Exit", exit_button)]

column_left = sg.Column([frame_basic_info, frame_charge_control, frame_exit_button], element_justification="l", vertical_alignment="top")
column_right = sg.Column([frame_cell_voltage, frame_temperature], element_justification="r", vertical_alignment="top")

layout = [ image,
    [column_left, sg.VerticalSeparator(pad=None), column_right],
]
window = sg.Window("BMS HV Utility", layout, element_justification="c")

def float_to_string_with_precision(value, precision):
    """Converts a float to a string with the specified precision"""
    return f"{value:.{precision}f}"

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
    return [l[i : i + columns] for i in range(0, len(l), columns)]

def serial_task(ser, read_queue, write_queue):
    ''' This function is used to read data from the serial port and to write data to the serial port '''
    WRITE_PREFIX = "WRITE: "
    READ_PREFIX = "READ: "
    while True:
        # Write data
        try:
            data = write_queue.get_nowait()
            ser.write(data.encode("utf-8"))
            print_ok(WRITE_PREFIX + "New data sent to the serial port")
        except queue.Empty:
            print_warning(WRITE_PREFIX + "Nothing to send to the serial port")

        # Read data
        try:
            ser.reset_input_buffer()
            ser.readline()
            line = ser.readline().decode("utf-8")
            if(line == ""):
                print_warning(READ_PREFIX + "Nothing received from the serial port")
                continue
            read_queue.put_nowait(line)
            print_ok(READ_PREFIX + "New data received from the serial port")
        except queue.Full:
            print_warning("Read queue is full")
            
def main():
    if len(sys.argv) != 2:
        print_error("Usage: python3 pyserial_tests.py <serial_port>")
        sys.exit(1)

    ser = serial.Serial()
    ser.port = sys.argv[1]
    ser.timeout = 0.5
    ser.open()
    
    bms_hv_data_queue = queue.Queue(maxsize=1)
    bms_hv_settings_queue = queue.Queue(maxsize=1)

    threading.Thread(
        target=serial_task, args=(ser, bms_hv_data_queue, bms_hv_settings_queue), daemon=True
    ).start()

    while True:
        event, values = window.read(timeout=1000)

        if event == sg.WINDOW_CLOSED or event == "Exit":
            break;

        elif event == "Start Charging":
            try:
                bms_hv_settings_queue.put_nowait("@kupa@")
            except queue.Full:
                print_error("Previous command still in the queue")
        
        elif event == "Stop Charging":
            try:
                bms_hv_settings_queue.put_nowait("b")
            except queue.Full:
                print_error("Previous command still in the queue")

        elif not bms_hv_data_queue.empty():
            bms_hv_data_json = bms_hv_data_queue.get()
            try:
                bms_hv_data = json.loads(
                    bms_hv_data_json, object_hook=lambda d: SimpleNamespace(**d)
                )
                bms_hv_data = BmsHvData(**bms_hv_data.__dict__)

            except json.decoder.JSONDecodeError:
                print_error("Invalid JSON: " + bms_hv_data_json)
                continue

            except TypeError:
                print_error("Received JSON is not of type BmsHvData: " + bms_hv_data_json)
                continue

            window[KEY_MAX_VOLTAGE].update(float_to_string_with_precision(max(bms_hv_data.cell_voltage), 3))
            window[KEY_MIN_VOLTAGE].update(float_to_string_with_precision(min(bms_hv_data.cell_voltage), 3))
            window[KEY_CURRENT].update(float_to_string_with_precision(bms_hv_data.current, 3))
            window[KEY_ACC_VOLTAGE].update(float_to_string_with_precision(bms_hv_data.acc_voltage, 3))
            window[KEY_CAR_VOLTAGE].update(float_to_string_with_precision(bms_hv_data.car_voltage, 3))
            window[KEY_SOC].update(float_to_string_with_precision((sum(bms_hv_data.soc) / len(bms_hv_data.soc)), 3))
            
            window[KEY_CELL_VOLTAGE].update(
                values=to_matrix( [float_to_string_with_precision(v, 3) for v in bms_hv_data.cell_voltage]
, TABLE_COLUMNS)
            )

            window[KEY_TEMPERATURE].update(
                values=to_matrix( [float_to_string_with_precision(v, 3) for v in bms_hv_data.temperature]
, TABLE_COLUMNS)
            )


    ser.close()
    window.close()
            

if __name__ == "__main__":
    main()

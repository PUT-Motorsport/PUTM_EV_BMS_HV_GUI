import json
from types import SimpleNamespace
from dataclasses import dataclass
import PySimpleGUI as sg
import serial

sg.theme("Dark2")


def to_matrix(l, columns):
    """Converts a list to a matrix with the specified number of columns"""
    return [l[i : i + columns] for i in range(0, len(l), columns)]

TABLE_COLUMNS = 15
CELL_VOLTAGE_TABLE_ROWS = 9
TEMPERATURE_TABLE_ROWS = 3

KEY_MAX_VOLTAGE = "-MAX-VOLTAGE-"
KEY_MIN_VOLTAGE = "-MIN-VOLTAGE-"
KEY_CURRENT = "-CURRENT-"
KEY_ACC_VOLTAGE = "-ACC-VOLTAGE-"
KEY_CAR_VOLTAGE = "-CAR-VOLTAGE-"
KEY_SOC = "-SOC-"
KEY_AIR = "-AIR-"
KEY_CHARGER_CURRENT = "-CHARGER-CURRENT-"
KEY_CHARGER_VOLTAGE = "-CHARGER-VOLTAGE-"
KEY_CELL_VOLTAGE = "-CELL-VOLTAGE-"
KEY_TEMPERATURE = "-TEMPERATURE-"

EXPECTED_JSON = """{
    "max_voltage": 12.3,
    "min_voltage": 14.2,
    "current": 11.2,
    "acc_voltage": 11.3,
    "car_voltage": 11.4,
    "soc": 11.5,
    "air": 11.6,
    "charger_current": 12.1,
    "charger_voltage": 12.2,
    "cell_voltage": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0,
        16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0,
        31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0, 38.0, 39.0, 40.0, 41.0, 42.0, 43.0, 44.0, 45.0,
        46.0, 47.0, 48.0, 49.0, 50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 60.0,
        61.0, 62.0, 63.0, 64.0, 65.0, 66.0, 67.0, 68.0, 69.0, 70.0, 71.0, 72.0, 73.0, 74.0, 75.0,
        76.0, 77.0, 78.0, 79.0, 80.0, 81.0, 82.0, 83.0, 84.0, 85.0, 86.0, 87.0, 88.0, 89.0, 90.0,
        91.0, 92.0, 93.0, 94.0, 95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0,
        106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0,
        121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0, 128.0, 129.0, 130.0, 131.0, 132.0, 133.0, 134.0, 135.0
    ],

	"temperature": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0,
        16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0,
        31.0, 32.0, 33.0, 34.0, 35.0, 36.0, 37.0, 38.0, 39.0, 40.0, 41.0, 42.0, 43.0, 44.0, 45.0
    ]
}"""

@dataclass
class BmsHvData:
    '''Dataclass for BMS HV data'''
    max_voltage: float
    min_voltage: float
    current: float
    acc_voltage: float
    car_voltage: float
    soc: float
    air: float
    charger_current: float
    charger_voltage: float
    cell_voltage: list[float]
    temperature: list[float]


basic_info = [
    [
        sg.Text("Max Voltage:"),
        sg.Text("-", key=KEY_MAX_VOLTAGE),
        sg.Text("V"),
    ],
    [
        sg.Text("Min Voltage:"),
        sg.Text("-", key=KEY_MIN_VOLTAGE),
        sg.Text("V"),
    ],
    [
        sg.Text("Current:"),
        sg.Text("-", key=KEY_CURRENT),
        sg.Text("A"),
    ],
    [
        sg.Text("Acc Voltage:"),
        sg.Text("-", key=KEY_ACC_VOLTAGE),
        sg.Text("V"),
    ],
    [
        sg.Text("Car Voltage:"),
        sg.Text("-", key=KEY_CAR_VOLTAGE),
        sg.Text("V"),
    ],
    [
        sg.Text("Soc:"),
        sg.Text("-", key=KEY_SOC),
        sg.Text("%"),
    ],
    [
        sg.Text("Air:"),
        sg.Text("-", key=KEY_AIR),
    ],
    [
        sg.Text("Charger Current:"),
        sg.Text("-", key=KEY_CHARGER_CURRENT),
        sg.Text("A"),
    ],
    [
        sg.Text("Charger Voltage:"),
        sg.Text("-", key=KEY_CHARGER_VOLTAGE),
        sg.Text("V"),
    ],
]

cell_voltage = [[
    sg.Table(
        values=[["-" for i in range(TABLE_COLUMNS)] for j in range(CELL_VOLTAGE_TABLE_ROWS)],
        headings=[f"Col {j+1}" for j in range(TABLE_COLUMNS)],
        select_mode=sg.TABLE_SELECT_MODE_NONE,
        display_row_numbers=True,
        auto_size_columns=False,
        justification="center",
        num_rows=10,
        enable_events=True,
        hide_vertical_scroll=True,
        key=KEY_CELL_VOLTAGE,
    )
]]

temperature = [[
    sg.Table(
        values=[["-" for i in range(TABLE_COLUMNS)] for j in range(TEMPERATURE_TABLE_ROWS)],
        headings=[f"Col {j+1}" for j in range(TABLE_COLUMNS)],
        select_mode=sg.TABLE_SELECT_MODE_NONE,
        display_row_numbers=True,
        auto_size_columns=False,
        justification="center",
        num_rows=3,
        enable_events=True,
        hide_vertical_scroll=True,
        key=KEY_TEMPERATURE,
    )
]]


frame_basic_info = [sg.Frame("Basic Info", basic_info)]
column_basic_info = sg.Column([frame_basic_info])

frame_cell_voltage = [sg.Frame("Cell Voltages", cell_voltage)]
frame_temperature = [sg.Frame("Temperatures", temperature)]
column_tables = sg.Column([frame_cell_voltage, frame_temperature])

charge_control = [[sg.Button("Start Charging"), sg.Button("Stop Charging")]]
frame_charge_control = [sg.Frame("Charge control", charge_control)]
column_charge_control = sg.Column([frame_charge_control])

buttons = [[sg.Button("Update Values"), sg.Button("Exit")]]
frame_buttons = [sg.Frame("Buttons", buttons)]
column_buttons = sg.Column([frame_buttons])

layout = [
    [column_basic_info, column_tables],
    [column_charge_control, column_buttons],
]
window = sg.Window("BMS HV Utility", layout, element_justification="c")

if __name__ == "__main__":
    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED or event == "Exit":
            break
        elif event == "Update Values":
            extracted_bms_hv_data = json.loads(EXPECTED_JSON, object_hook=lambda d: SimpleNamespace(**d))
            bms_hv_data = BmsHvData(**extracted_bms_hv_data.__dict__)

            window[KEY_MAX_VOLTAGE].update(bms_hv_data.max_voltage)
            window[KEY_MIN_VOLTAGE].update(bms_hv_data.min_voltage)
            window[KEY_CURRENT].update(bms_hv_data.current)
            window[KEY_ACC_VOLTAGE].update(bms_hv_data.acc_voltage)
            window[KEY_CAR_VOLTAGE].update(bms_hv_data.car_voltage)
            window[KEY_SOC].update(bms_hv_data.soc)
            window[KEY_AIR].update(bms_hv_data.air)
            window[KEY_CHARGER_CURRENT].update(bms_hv_data.charger_current)
            window[KEY_CHARGER_VOLTAGE].update(bms_hv_data.charger_voltage)

            window[KEY_CELL_VOLTAGE].update(
                values=to_matrix(bms_hv_data.cell_voltage, TABLE_COLUMNS)
            )

            window[KEY_TEMPERATURE].update(
                values=to_matrix(bms_hv_data.temperature, TABLE_COLUMNS)
            )

    window.close()

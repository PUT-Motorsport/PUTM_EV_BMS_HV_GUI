import PySimpleGUI as sg

# Create a layout for the GUI


basic_info = [
    sg.Text("MAX VOLTAGE:"), sg.Text("", size=(10, 1), key="-VALUE1-"),
    sg.Text("MIN VOLTAGE:"), sg.Text("", size=(10, 1), key="-VALUE2-"),
    sg.Text("CURRENT:"), sg.Text("", size=(10, 1), key="-VALUE3-"),
    sg.Text("ACC VOLTAGE:"), sg.Text("", size=(10, 1), key="-VALUE4-"),
    sg.Text("CAR VOLTAGE:"), sg.Text("", size=(10, 1), key="-VALUE5-"),
    sg.Text("SOC:"), sg.Text("", size=(10, 1), key="-VALUE6-"),
    sg.Text("AIR:"), sg.Text("", size=(10, 1), key="-VALUE7-"),
    sg.Text("CHARGER CURRENT:"), sg.Text("", size=(10, 1), key="-VALUE8-"),
    sg.Text("CHARGER VOLTAGE:"), sg.Text("", size=(10, 1), key="-VALUE9-"),
]

voltage_matrix = [['-' for row in range(15)]for col in range(9)]
voltage = [sg.Table(values=voltage_matrix,
              headings=[f"Col {j+1}" for j in range(15)],
              select_mode = sg.TABLE_SELECT_MODE_NONE,
              display_row_numbers = True,
              auto_size_columns=False,
              justification='center',
              num_rows=10,
              enable_events=True,
              hide_vertical_scroll=True,
              key="-TABLE1-")]

temperature_matrix = [['-' for row in range(15)]for col in range(3)]
temperature = [sg.Table(values=temperature_matrix,
                headings=[f"Col {j+1}" for j in range(15)],
                select_mode = sg.TABLE_SELECT_MODE_NONE,
                display_row_numbers = True,
                auto_size_columns=False,
                justification='center',
                num_rows=3,
                enable_events=True,
                hide_vertical_scroll=True,
                key="-TABLE2-")]

charge_control = [sg.Button("Start Charging"), sg.Button("Stop Charging")]

buttons = [sg.Button("Update Values"), sg.Button("Exit")]

frame_basic_info = [sg.Frame("Basic Info", [basic_info])]
frame_voltage = [sg.Frame("Voltage", [voltage])]
frame_temperature = [sg.Frame("Temperature", [temperature])]
frame_charge_control = [sg.Frame("Charge control", [charge_control])]
frame_buttons = [sg.Frame("Temperature", [buttons])]

layout = [frame_basic_info, frame_voltage, frame_temperature, frame_charge_control, frame_buttons]

# Create the window
window = sg.Window("BMS HV Utility", layout, element_justification='c')

# Event loop
while True:
    event, values = window.read()

    if event == sg.WINDOW_CLOSED or event == "Exit":
        break
    elif event == "Update Values":
        # Replace these placeholder values with your actual values
        values = ["123", "456", "789", "012", "345", "678", "901", "234", "567"]

        # Update the GUI elements with new values
        for i in range(9):
            window["-VALUE{}-".format(i + 1)].update(values[i])

        # Update the table with new values
        voltage_matrix[2][4] = 12
        window['-TABLE1-'].update(values=voltage_matrix)
        
        temperature_matrix[1][7] = 24
        window['-TABLE2-'].update(values=temperature_matrix)

# Close the window when the loop ends
window.close()
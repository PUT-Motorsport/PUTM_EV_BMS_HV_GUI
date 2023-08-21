import PySimpleGUI as sg
import random

"""
    Demo - Using a Graph Element to make Bar Charts

    The Graph Element is very versatile. Because you can define your own
    coordinate system, it makes producing graphs of many lines (bar, line, etc) very
    straightforward.
    
    In this Demo a "bar" is nothing more than a rectangle drawn in a Graph Element (draw_rectangle).
    
    To make things a little more interesting, this is a barchart with that data values
    placed as labels atop each bar, another Graph element method (draw_text)

    Copyright 2022 PySimpleGUI
"""

HEIGHT=500
WIDTH=1350
NUM_OF_BARS = 27
MAX_VALUE = 4.5
MIN_VALUE = 0

GRAPH_SIZE= DATA_SIZE = (WIDTH, HEIGHT)
BAR_SPACING = WIDTH/NUM_OF_BARS
BAR_WIDTH = BAR_SPACING * .8

EDGE_OFFSET = 3

sg.theme('Material2')

layout = [[sg.Graph(GRAPH_SIZE, (0,0), DATA_SIZE, k='-GRAPH-')],
          [sg.Button('OK'), sg.T('Click to display more data'), sg.Exit()]]

window = sg.Window('Bar Graph', layout, finalize=True)

graph = window['-GRAPH-']

while True:

    graph.erase()
    for i in range(NUM_OF_BARS):
        graph_value = random.randint(0, GRAPH_SIZE[1]-25)       # choose an int just short of the max value to give room for the label
        graph.draw_rectangle(top_left=(i * BAR_SPACING + EDGE_OFFSET, graph_value),
                             bottom_right=(i * BAR_SPACING + EDGE_OFFSET + BAR_WIDTH, 0),
                             fill_color=sg.theme_button_color()[1])

        graph.draw_text(text=graph_value, location=(i*BAR_SPACING+EDGE_OFFSET+(BAR_WIDTH)/2, graph_value+10), font='_ 7')

    event, values = window.read()

    if event in (sg.WIN_CLOSED, 'Exit'):
        break


window.close()

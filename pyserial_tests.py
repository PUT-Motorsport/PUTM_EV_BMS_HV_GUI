import serial
import sys



if(len(sys.argv) != 2):
    print("Usage: python3 pyserial_tests.py <serial_port>")
    sys.exit(1)


ser =  serial.Serial()
ser.port = sys.argv[1]
ser.open()
ser.readline()
line = ser.readline().decode('ascii')
print(line)

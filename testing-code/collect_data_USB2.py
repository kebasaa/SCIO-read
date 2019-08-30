'''
DO NOT USE. THIS DOES NOT WORK YET
----------------------------------

Run using python3 collect_data.py

This script searches for a SCIO spectrometer.
When found, it connects to the device, waits
for the button to be pressed and then performs
a scan.
The scan's data will be saved in a sub-
directory called "scans" as a raw hex data
file (in JSON, containing also the temperature
of the SCIO before & after the scan) and as
a decoded CSV. HOW TO DECODE IS NOT CLEAR YET!

Uses the following libraries:
- Json
- http://www.pyinstaller.org/
'''

import json
import platform

import logging
log = logging.getLogger('root')
log.setLevel(logging.DEBUG)
#logging.basicConfig(format='[%(asctime)s] %(levelname)8s %(module)15s: %(message)s')
logging.basicConfig(format='[%(asctime)s] %(levelname)8s: %(message)s', datefmt='%y-%m-%y %H:%M:%S')

import glob
import re
import os
import argparse

import serial

# Functions performing scans
def read_temperature_simple(scio_dev):
    # This reads the temperature
    import struct
    
    # Open serial connection
    try:
        ser = serial.Serial(scio_dev)
    except OSError as error:
        print(error)
        quit()
    # Check if it the serial port is open
    #print(ser.isOpen()) # debug
    msg = b"\x01\xba\x04\x00\x00" # message needed to read the temperature
    ser.write(msg)                # write the message to the serial device
    s = ser.read(16)              # Read the response. I expect 16 hex values
    # TODO read until the end of the message automatically. The message encodes the number of values!!!
    #print(s) # debug
    ser.close()
    
    # Convert bytes to unsigned int
    #temp = struct.unpack('<bbHlll',s) # convert bytes to unsigned int
    temp = struct.unpack('<bbHlll',s)
    print(temp)

    # Convert to temperatures
    cmosTemperature = (temp[3] - 375.22) / 1.4092 # Does this make sense? It's from the disassembled Android app...
    chipTemperature = (temp[4] - 375.22) / 100 # The subtraction is added by me. Not true it should be there
    objectTemperature = temp[5]
    return(cmosTemperature, chipTemperature, objectTemperature)

def read_temperature(scio_dev):
    # This reads the temperature
    import struct
    
    # Open serial connection
    try:
        ser = serial.Serial(scio_dev)
    except OSError as error:
        log.error(error)
        quit()
    # Check if it the serial port is open
    #print(ser.isOpen()) # debug
    msg = b"\x01\xba\x04\x00\x00" # message needed to read the temperature
    ser.write(msg)                # write the message to the serial device
    #s = ser.read(16)              # Read the response. I expect 16 hex values
    s = ser.read(1)
    message_type    = struct.unpack('<b',s)[0]
    if(message_type != -70):
        log.debug("Wrong message type: " + str(message_type))
    s = ser.read(1)
    message_content = struct.unpack('<b',s)[0]
    if(message_content == 4):
        log.debug("Receiving temperature data: " + str(message_content))
    elif(message_content == 2):
        log.debug("Receiving scan data: " + str(message_content))
    else:
        log.debug("Receiving unknown message: " + str(message_content))
    s = ser.read(2)
    message_length = struct.unpack('<H',s)[0]
    log.debug("Number of bytes: " + str(message_length))
    log.debug("Number of longs: " + str(message_length/4))
    # Read the number of values specified by the message length
    s = ser.read(message_length)
    ser.close()
    
    num_vars = message_length / 4 # divide by 4 because we are dealing with longs
    data_struct = '<' + str(int(num_vars)) + 'l' # This is '<3l' or '<lll'
    print(data_struct)
    # Convert bytes to unsigned int
    print(s)
    message_data = struct.unpack(data_struct ,s)
    print(message_data)

    # Convert to temperatures
    cmosTemperature = (message_data[0] - 375.22) / 1.4092 # Does this make sense? It's from the disassembled Android app...
    chipTemperature = (message_data[1] - 375.22) / 100 # The subtraction is added by me. Not true it should be there
    objectTemperature = message_data[2]
    return(cmosTemperature, chipTemperature, objectTemperature)
    
    
def read_data(scio_dev, command):
    # This reads the temperature
    #import protocol message definitions
    # e.g. data = -70, temperature = 4, etc ################
    import struct
    
    # Open serial connection
    try:
        ser = serial.Serial(scio_dev)
    except OSError as error:
        log.error(error)
        quit()

    def protocol_message(command):
        byte_command = b"" # empty initialisation
        if(command == "read_temperature"):  # TODO: take from imported protocol
        # message needed to read the temperature
        # I could even build the command from [1, -70, 4, 0, 0] by replacing -70 & 4 #################
            byte_command = b"\x01\xba\x04\x00\x00"
        return(byte_command)

    msg = protocol_message(command)
    # write the message to the serial device
    ser.write(msg)

    # Start reading the response
    s = ser.read(1)
    message_type    = struct.unpack('<b',s)[0]
    if(message_type != -70):
        log.debug("Wrong message type: " + str(message_type))
        #raise error  #######################
    s = ser.read(1)
    message_content = struct.unpack('<b',s)[0]
    if(message_content == 4):
        log.debug("Receiving temperature data: " + str(message_content))
    elif(message_content == 2):
        log.debug("Receiving scan data: " + str(message_content))
    else:
        log.debug("Receiving unknown message: " + str(message_content))
    s = ser.read(2)
    message_length = struct.unpack('<H',s)[0]
    log.debug("Number of bytes: " + str(message_length))
    log.debug("Number of longs: " + str(message_length/4))
    log.debug("Number of variables (5 bytes each): " + str(message_length/5))
    # Read the number of values specified by the message length
    s = ser.read(message_length) # Scan data consists of 3x these messages! #################### 
    ser.close()
    
    num_vars = message_length / 4 # divide by 4 because we are dealing with longs
    data_struct = '<' + str(int(num_vars)) + 'l' # This is '<3l' or '<lll'
    print(data_struct)
    # Convert bytes to unsigned int
    print(s)
    message_data = struct.unpack(data_struct ,s)
    print(message_data)

    # Convert to temperatures
    cmosTemperature = (message_data[0] - 375.22) / 1.4092 # Does this make sense? It's from the disassembled Android app...
    chipTemperature = (message_data[1] - 375.22) / 100 # The subtraction is added by me. Not true it should be there
    objectTemperature = message_data[2]
    return(cmosTemperature, chipTemperature, objectTemperature)
    

def main_fct(calibrate, input_method, outfile):
    if(calibrate):
        log.debug("We were told to calibrate")
    log.info("Input/output")
    log.info("--> Input through:    " + input_method)
    log.info("--> Output file name: " + outfile)
    
    def find_scio_dev():
        scio_dev = ""
        # Check the platform
        # https://dzone.com/articles/linux-system-mining-python
        if(platform.uname().system == 'Linux'):
            # TODO: Add check in case multiple /dev/ttyACMs ports are available #######################
            for device in glob.glob('/dev/*'):
                for pattern in ['ttyACM*']:
                    if re.compile(pattern).match(os.path.basename(device)):
                        print('Device:           {0}'.format(device))
                        scio_dev = device
        elif(platform.uname().system == 'Windows'):
            # TODO: Add check in case multiple COM ports are available #######################
            import serial.tools.list_ports as port_list
            if(port_list.comports()):
                scio_dev = port_list.comports()[0][0]
                print(port_list.ListPortInfo.name())
        else:
            log.error("This program currently only works on Linux & Windows.")
            log.error("--> You are running " + platform.uname().system + ".")
            log.error("--> Exiting...")
            quit()
        if scio_dev == "":
            print("If no ttyACM (Linux) or COM (Windows) is detected: Is the SCIO on?")
            quit()
        # TODO: Add a check or manufacturer to determine that this is really the scio and not some arduino
        log.info("Using port: " + scio_dev)
        return(scio_dev)
    
    scio_device = find_scio_dev()
    
    # https://makersportal.com/blog/2018/2/25/python-datalogger-reading-the-serial-output-from-arduino-to-analyze-data-using-pyserial
    try: # Make sure to close the serial port if it was still open
        ser.close()
    except:
        pass
    
    #cmosTemperature, chipTemperature, objectTemperature = read_temperature_simple(scio_device)
    cmosTemperature, chipTemperature, objectTemperature = read_temperature(scio_device)
    print("CMOS T: ", cmosTemperature)
    print("Chip T: ", chipTemperature)
    print("Obj. T: ", objectTemperature)
    #hex(temp) ##convert int to string which is hexadecimal expression
    
    ser = serial.Serial(scio_device)
    #msg = b"\x01\xba\x0b\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" # turn off leds
    #ser.write(msg)
    msg = b"\x01\xba\x02\x00\x00" # scan
    ser.write(msg)
    s = ser.read(2*1800+1656+12) # For temperature, I expect 16 hex values
    #print(s)
    ser.close()

    # Start instructions for scanning
    print("\nPlease turn on your SCIO")
    print("    Do you want to load saved settings? [y/n]")
    load_settings = input("    \(If no: automatic \(slow\) search for device\): ")
    if(load_settings == "y"):
        scio_name, scio_mac_addr = read_config()
    else:
        print("    Searching for SCIO...")
        scio_name, scio_mac_addr = searchScio()
        print("    SCIO device discovered: " + scio_name)
        write_config(scio_name, scio_mac_addr)

    print("\nCalibration: Please put the SCIO in its box")
    #input("    Press Enter to continue")
    #scioCalibration(scio_mac_addr)
    #print("    Calibrating...")

    print("\nDevice ready")
    print("    Push the SCIO button to scan")
    # HERE: wait for button press, perform scan, then save to file
    print("    Scanning...")
    #scioScan(scio_mac_addr)
    print("    Saving raw hex data...")
    print("    Decoding & saving spectrum...")

    # Alternative:
    print("\nDevice ready")
    input("    Press Enter to scan")
    # HERE: perform scan, then save to file
    print("    Scanning...")
    print("    Saving raw hex data...")
    print("    Decoding & saving spectrum...")

    print("")


if __name__ == '__main__':
    # https://dzone.com/articles/linux-system-mining-python
    parser = argparse.ArgumentParser(description='SCIO Scanning Utility')

    parser.add_argument('-c','--calibrate', action='store_true',dest='calibrate',
                        default = False, help='calibrate the SCIO (no output created)')
    parser.add_argument('-i', '--input', dest='method',
                        default = 'usb', help='[bt/usb] input through USB or Bluetooth')
    parser.add_argument('-o','--output-file', dest='filename',
                        default = 'scio-scan', help='name of the output files')

    args = parser.parse_args()
    main_fct(args.calibrate, args.method, args.filename)
 

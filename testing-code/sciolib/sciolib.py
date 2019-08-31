'''
sciolib - SCIO spectrometer library
Copyright (C) 2019  kebasaa

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import logging
log = logging.getLogger('root')
log.setLevel(logging.DEBUG)
logging.basicConfig(format='[%(asctime)s] %(levelname)8s: %(message)s', datefmt='%y-%m-%y %H:%M:%S')

# To identify the OS
import platform

# To identify the device
import glob
import re
import os

# Reading the SCIO through USB serial port
import serial
from serial.tools import list_ports_common

READ_DATA = 2
READ_TEMPERATURE = 4
PROTOCOL = -70

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
                    manufacturer = self.read_line(device, 'manufacturer')
                    product = self.read_line(device, 'product')
                    print(manufacturer)
                    print(product)
    elif(platform.uname().system == 'Windows'):
        # TODO: Add check in case multiple COM ports are available
        import serial.tools.list_ports as port_list
        if(port_list.comports()):
            scio_dev = port_list.comports()[0][0]
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
            cmd = READ_TEMPERATURE
        elif(command == "read_data"):
            cmd = READ_DATA
        byte_command = struct.pack('<bbbbb',1,PROTOCOL,cmd,0,0)
        print(byte_command)
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
    
    def decode_temperature(msg, message_length):
        num_vars = message_length / 4 # divide by 4 because we are dealing with longs
        data_struct = '<' + str(int(num_vars)) + 'l' # This is '<3l' or '<lll'
        # Convert bytes to unsigned int
        message_data = struct.unpack(data_struct ,s)
        # Convert to temperatures
        cmosTemperature = (message_data[0] - 375.22) / 1.4092 # Does this make sense? It's from the disassembled Android app...
        chipTemperature = (message_data[1] - 375.22) / 100 # The subtraction is added by me. Not true it should be there
        objectTemperature = message_data[2]
        return(cmosTemperature, chipTemperature, objectTemperature)
        
    def decode_data():
        ser = serial.Serial(scio_device)
        msg = b"\x01\xba\x02\x00\x00" # scan
        ser.write(msg)
        s = ser.read(2*1800+1656+12) # For temperature, I expect 16 hex values
        #print(s)
        ser.close()
        
    cmosTemperature, chipTemperature, objectTemperature = decode_temperature(s, message_length)
    return(cmosTemperature, chipTemperature, objectTemperature)
    
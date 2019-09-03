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

# Exceptions / Assert errors
import sys

# Reading the SCIO through USB serial port
import serial
from serial.tools import list_ports_common

# encode & decode data
import struct

READ_DATA = 2        #02
READ_TEMPERATURE = 4 #04
READ_BATTERY = 5     #05
SET_READY = 14       #0e
SET_LED = 11         #0b
PROTOCOL = -70       #ba

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
    
def protocol_message(cmd):
    byte_command = b"" # empty initialisation
    if(cmd == SET_LED):
        # Setting the LED colour is special (longer command)
        byte_command = struct.pack('<bbbbbbbbbbbbbbb',1,PROTOCOL,cmd,9,0,0,0,0,0,0,0,0,0,0)
    else:
        byte_command = struct.pack('<bbbbb',1,PROTOCOL,cmd,0,0)
    return(byte_command)

def read_data(scio_dev, command):
    # This reads or writes data
    
    # Create the message
    #byte_msg = protocol_message(READ_TEMPERATURE)
    byte_msg = protocol_message(command)
    
    # Open serial connection
    try:
        ser = serial.Serial(scio_dev)
    except OSError as error:
        log.error(error)
        quit()
    
    # write the message to the serial device
    ser.write(byte_msg)

    # Start reading the response
    s = ser.read(1)
    message_type    = struct.unpack('<b',s)[0]
    
    # Error check
    assert (message_type == PROTOCOL), 'Wrong message type: {}'.format(message_type)
    
    # Data type
    s = ser.read(1)
    message_content = struct.unpack('<b',s)[0]
    if(message_content == READ_TEMPERATURE):
        log.debug("Receiving temperature data: " + str(message_content))
    elif(message_content == READ_DATA):
        log.debug("Receiving scan data: " + str(message_content))
        s = ser.read(2)
        message_length = struct.unpack('<H',s)[0]
        s = ser.read(message_length)
        # End msg 1
        s = ser.read(1)
        message_type    = struct.unpack('<b',s)[0]
        s = ser.read(1)
        message_content = struct.unpack('<b',s)[0]
        s = ser.read(2)
        message_length = struct.unpack('<H',s)[0]
        s = ser.read(message_length)
        # End msg 3
        s = ser.read(1)
        message_type    = struct.unpack('<b',s)[0]
        s = ser.read(1)
        message_content = struct.unpack('<b',s)[0]
    else:
        log.debug("Receiving unknown message: " + str(message_content))
    
    # Data length
    s = ser.read(2)
    message_length = struct.unpack('<H',s)[0]
    
    # Read the number of values specified by the message length
    s = ser.read(message_length)
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
        
    def decode_data(msg, message_length):
        # Debug
        log.debug("Number of bytes: " + str(message_length))
        log.debug("Number of longs (+145, header 332 bytes): " + str((message_length-145)/4))
        log.debug("Number of variables (5 bytes each), header 1 byte: " + str((message_length-1)/5))
        # NOTE: Only looking at part 3 (1656 bytes) withe the assumption that some 332 bytes encode something else
        #num_vars = (message_length -476) / 4 # divide by 4 because we are dealing with longs
        #data_struct = '<' + '4x472b' + str(int(num_vars)) + 'l'
        #https://stackoverflow.com/questions/7949912/how-to-unpack-6-bytes-as-single-integer-using-struct-in-python
        header = 332
        footer = 332 - header
        num_vars = (message_length - header - footer) / 4 # divide by 4 because we are dealing with longs
        data_struct = '<' + str(int(header)) + 'b' + str(int(num_vars)) + 'f' + str(int(footer)) + 'b'
        print(struct.unpack('<1656s',s))

        #data_struct = '<' + str(int(num_vars)) + 'd' + str(int(header)) + 'b'
        # Convert bytes to unsigned int
        message_data = struct.unpack(data_struct ,s)
        return(message_data)
        
    def bin5(b,k):
        """ Returns binary integer from bytes k,k+1,...,k+4 in b."""
        b0 = b[k  ]
        b1 = b[k+1]
        b2 = b[k+2]
        b3 = b[k+3]
        b4 = b[k+4]
        if b0<0: b0 += 256
        if b1<0: b1 += 256
        if b2<0: b2 += 256
        if b3<0: b3 += 256
        if b4<0: b4 += 256
        return(b0*65536.0+b1*256.0+b2+b3/256.0+b4/65536.0)
        
    if(message_content == READ_TEMPERATURE):
        cmosTemperature, chipTemperature, objectTemperature = decode_temperature(s, message_length)
        return(cmosTemperature, chipTemperature, objectTemperature)
    elif(message_content == READ_DATA):
        print(decode_data(s, message_length))
        log.debug("Data done")
    else:
        log.debug("Receiving unknown message: " + str(message_content))
    
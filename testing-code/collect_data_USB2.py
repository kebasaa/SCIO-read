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

import glob
import re
import os
import argparse

import serial

# Functions performing scans

def main_fct(calibrate, input_method, outfile):
    if(calibrate):
        print("We were told to calibrate")
    print("Input through:    " + input_method)
    print("Output file name: " + outfile)
    
    # Check the platform
    # https://dzone.com/articles/linux-system-mining-python
    if(platform.uname().system != 'Linux'):
        print("WARNING: This program only works on Linux.")
        print("         You are running " + platform.uname().system + ".")
        print("Exiting...")
        quit()
    
    def find_scio_dev():
        scio_dev = ""
        for device in glob.glob('/dev/*'):
            for pattern in ['ttyACM*']:
                if re.compile(pattern).match(os.path.basename(device)):
                    print('Device:           {0}'.format(device))
                    scio_dev = device
        if scio_dev == "":
            print("If no ttyACM is detected: Is the SCIO on?")
            quit()
        # TODO: Add a check or manufacturer to determine that this is really the scio and not some arduino
        return(scio_dev)
    
    scio_device = find_scio_dev()
    
    # https://makersportal.com/blog/2018/2/25/python-datalogger-reading-the-serial-output-from-arduino-to-analyze-data-using-pyserial
    ser = serial.Serial(scio_device)
    print(ser.isOpen())
    msg = b"\x01\xba\x04\x00\x00" # read temperature

    ser.write(msg)
    s = ser.read(16) # For temperature, I expect 16 hex values
    print(s)
    ser.close()
    
    ser = serial.Serial(scio_device)
    #msg = b"\x01\xba\x0b\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" # turn off leds
    #ser.write(msg)
    msg = b"\x01\xba\x02\x00\x00" # scan
    ser.write(msg)
    s = ser.read(2*1800+1656+12) # For temperature, I expect 16 hex values
    print(s)
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
 

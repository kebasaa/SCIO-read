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

def write_config(scio_name, scio_mac_addr):
    config["scio_name"] = scio_name
    config["scio_mac"] = scio_mac_addr
    with open('settings.json', 'w') as cfile:
        cfile.write(json.dumps(config))
		
def read_config():
    with open('settings.json') as config_file:
        config = json.load(config_file)
    scio_name = config["scio_name"]
    scio_mac_addr = config["scio_mac"]
    return(scio_name, scio_mac_addr)

def searchScio():
    async def run():
        name_alternatives = ['scio', 'Scio']
        devices = await discover()
        for d in devices:
            if any(x in d.name for x in name_alternatives):
                scio_mac_addr = d.address
                scio_name = d.name
        return(scio_name, scio_mac_addr)

    loop = asyncio.get_event_loop()
    scio_name, scio_mac_addr = loop.run_until_complete(run())
    return(scio_name, scio_mac_addr)

async def scioScan(scio_mac_addr):
    MODEL_NBR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

    temp_handle = 0x0029
    temp_cmd = b"01ba040000"

    async with BleakClient(scio_mac_addr, loop=loop) as client:
        x = await client.is_connected()
        model_number = await client.read_gatt_char(MODEL_NBR_UUID)
        print("Model Number: {0}".format("".join(map(chr, model_number))))
        write_test = await client.write_gatt_descriptor(temp_handle, temp_cmd) #https://bleak.readthedocs.io/en/latest/api.html
        print(write_test)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(scio_mac_addr, loop))
	
	#return(data)


def main_fct(calibrate, input, outfile):
    if(calibrate):
        print("We were told to calibrate")
    print("Input through:    " + input)
    print("Output file name: " + outfile)
    print("")
    
    # Check the platform
    # https://dzone.com/articles/linux-system-mining-python
    if(platform.uname().system != 'Linux'):
        print("WARNING: This program only works on Linux.")
        print("         You are running " + platform.uname().system + ".")
        print("Exiting...")
        quit()
    
    def find_scio_dev():
        for device in glob.glob('/dev/*'):
            for pattern in ['ttyACM*']:
                if re.compile(pattern).match(os.path.basename(device)):
                    print('Device:: {0}'.format(device))
                    print("If no ttyACM is detected: Is the SCIO on?")
    
    # https://makersportal.com/blog/2018/2/25/python-datalogger-reading-the-serial-output-from-arduino-to-analyze-data-using-pyserial
    ser = serial.Serial("/dev/ttyACM0")
    ser_bytes = ser.readline()
    ser.flushInput()

    # Start instructions for scanning
    print("\nPlease turn on your SCIO")
    print("    Do you want to load saved settings? [y/n]")
    load_settings = input("    (If no: automatic (slow) search for device): ")
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
    parser.add_argument('-o','--output-file', dest='file',
                        default = 'scio-scan', help='name of the output files')

    args = parser.parse_args()
    main_fct(args.calibrate, args.method, args.file)

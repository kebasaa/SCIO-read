'''
DO NOT USE. THIS DOES NOT WORK YET
----------------------------------

Run using python3 collect_data_USB.py

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

TODO
encode binary to base64, store in json

'''

# To read settings file
import json
# Parst the command line arguments
import argparse

# Logging/output format setup
import logging
log = logging.getLogger('root')
log.setLevel(logging.DEBUG)
#logging.basicConfig(format='[%(asctime)s] %(levelname)8s %(module)15s: %(message)s')
logging.basicConfig(format='[%(asctime)s] %(levelname)8s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# The SCIO library
import sciolib.sciolib as scio

def main_fct(calibrate, input_method, outfile):
    if(calibrate):
        log.debug("We were told to calibrate")
    log.info("Input/output")
    log.info("--> Input through:    " + input_method)
    log.info("--> Output file name: " + outfile)
    
    scio_device = scio.find_scio_dev()
    
    # https://makersportal.com/blog/2018/2/25/python-datalogger-reading-the-serial-output-from-arduino-to-analyze-data-using-pyserial
    try: # Make sure to close the serial port if it was still open
        ser.close()
    except:
        pass
    
    # Read temperature before scanning
    temp_before_df = scio.read_data(scio_device, 4) # 4 = read temperature
    log.info("CMOS T: {:.3f}".format(temp_before_df[0])) # cmosTemperature, chipTemperature, objectTemperature
    log.info("Chip T: {:.3f}".format(temp_before_df[1]))
    log.info("Obj. T: {:.3f}".format(temp_before_df[2]))
    
    # Scan and decode
    scan_raw_df = scio.read_data(scio_device, 2) # 2 = read data
    scan_df = scio.decode_data(scan_raw_df) # DOES NOT YET WORK
    
    # Read temperature after scanning
    temp_after_df = scio.read_data(scio_device, 4)
    
    # Path to output file within home directory
    if len(outfile) > 1:
        log.debug("write output") #blah = sys.argv[1]
    else:
        log.debug("no output")
        
    from pathlib import Path
    json_dir = str(Path.home())
    log.debug("Writing raw scan to: " + json_dir + "/scio_scan.json")
    # Save file
    scio.save_json(temp_before_df, temp_after_df, scan_raw_df, json_dir + "/scio_scan.json") # outfile from 
    
    
    '''
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
    '''
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
 

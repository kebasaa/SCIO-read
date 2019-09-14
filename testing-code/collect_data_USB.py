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

def main_fct(calibrate, infile, outfile, protocol, raw):
    if(calibrate): # DEBUG!!!
        log.debug("We were told to calibrate")
    log.info("Input/output")
        
    # Find the home folder (temporary)
    from pathlib import Path
    json_dir = str(Path.home())
    
    # Check if we need to scan
    if(infile is not None):
        # Input comes from a file
        log.info("--> Input through:    " + json_dir + "/" + infile)
        log.info("--> Output file name: " + "N/A")
        # Read the raw json file
        json_df = scio.raw_read(json_dir + "/" + infile)
        scan_raw_df = json_df[7:10] # Element 10 is not included...
    else:
        # We have to scan (Only USB currently works)
        log.info("--> Input through:    " + protocol)
        log.info("--> Output file name: " + outfile)
        
        # Try to find the device
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
    
        # Read temperature after scanning
        temp_after_df = scio.read_data(scio_device, 4)
    
        # Path to output file within home directory
        if(outfile == "scio-scan"):
            # The default file name was given!
            log.info("WARNING! The default file was used. Any existing previous file will be overwritten!")
            
        # Save the file
        log.debug("Writing raw scan to: " + json_dir + "/" + outfile + ".json")
        # Saves the raw data. In the end, I'll want to save the scan as a CSV
        scio.raw_write(temp_before_df, temp_after_df, scan_raw_df, json_dir + "/" + outfile + ".json")
    
    log.info("Trying to decode data")
    scan_df = scio.decode_data(scan_raw_df) # DOES NOT YET WORK
    #print(scan_df) #DEBUG
    log.debug("Number of scans in data:  " + str(len(scan_df)))
    log.debug("Number of variables/scan: " + str(len(scan_df[0])))
    print("")


if __name__ == '__main__':
    # https://dzone.com/articles/linux-system-mining-python
    parser = argparse.ArgumentParser(description='SCIO Scanning Utility')

    parser.add_argument('-c','--calibrate', action='store_true',dest='calibrate',
                        default = False, help='calibrate the SCIO (no output created)')
    parser.add_argument('-i','--input-file', dest='infile',
                        help='name of the input raw JSON file')
    parser.add_argument('-o','--output-file', dest='outfile',
                        default = 'scio-scan', help='name of the output files')
    parser.add_argument('-p', '--protocol', dest='protocol',
                        default = 'usb', help='[bt/usb] input through USB or Bluetooth')
    parser.add_argument('-r','--raw-save', action='store_true',dest='raw',
                        default = True, help='save the raw scan') # Temporary. Change to false once we're confident in the decoding
                        
    args = parser.parse_args()
    main_fct(args.calibrate, args.infile, args.outfile, args.protocol, args.raw)
 

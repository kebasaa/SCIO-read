'''
DO NOT USE. THIS DOES NOT WORK YET
----------------------------------

Run using python3 collect_data.py

This script searches for a SCIO spectrometer.
When found, it connects to the device, waits
for tue button to be pressed and then performs
a scan.
The scan's data will be saved in a sub-
directory called "scans" as a raw hex data
file (in JSON, containing also the temperature
of the SCIO before & after the scan) and as
a decoded CSV. HOW TO DECODE IS NOT CLEAR YET!

Uses the following libraries:
- bleak (https://github.com/hbldh/bleak),
  which supports Windows 10, Linux & Mac
  Install using: pip3 install bleak
- asyncio, a dependency of bleak
- http://www.pyinstaller.org/
'''

import asyncio
from bleak import discover
from bleak import BleakClient

# Functions performing scans

def searchScio():
    async def run():
        devices = await discover()
        for d in devices:
            if("Scio" in d.name):
                scio_mac_addr = d.address
                scio_name = d.name
        return(scio_name, scio_mac_addr)

    loop = asyncio.get_event_loop()
    scio_name, scio_mac_addr = loop.run_until_complete(run())
    return(scio_name, scio_mac_addr)

async def scioScan(scio_mac_addr):
    scio_mac_addr = "B4:99:4C:59:66:01"
    MODEL_NBR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

    temp_handle = 0x0029
    temp_cmd = b"01ba040000"

    async with BleakClient(scio_mac_addr, loop=loop) as client:
        model_number = await client.read_gatt_char(MODEL_NBR_UUID)
        print("Model Number: {0}".format("".join(map(chr, model_number))))
        write_test = await client.write_gatt_descriptor(temp_handle, temp_cmd) #https://bleak.readthedocs.io/en/latest/api.html
        print(write_test)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(scio_mac_addr, loop))
	
	#return(data)


# Wait until the user is ready
print("+-----------+")
print("| SCIO scan |")
print("+-----------+")
print("\nPlease turn on your SCIO")
#input("    Press Enter to continue")
print("    Searching for SCIO...")

scio_name, scio_mac_addr = searchScio()
print("    SCIO device discovered: " + scio_name)

print("\nCalibration: Please put the SCIO in its box")
input("    Press Enter to continue")
# HERE: Do calibration
print("    Calibrating...")

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




# OLD STUFF

import asyncio
from bleak import discover

async def run():
    devices = await discover()
    for d in devices:
        print(d)

loop = asyncio.get_event_loop()
loop.run_until_complete(run())
print(devices)

# Look at services
async def print_services(mac_addr: str, loop: asyncio.AbstractEventLoop):
    async with BleakClient(mac_addr, loop=loop) as client:
        svcs = await client.get_services()
        print("Services:", svcs)
        for s in svcs:
            print(s)


scio_mac_addr = "B4:99:4C:59:66:01"
loop = asyncio.get_event_loop()
loop.run_until_complete(print_services(scio_mac_addr, loop))






import logging
import asyncio

from bleak import BleakClient


async def run2(address, loop, debug=False):
    log = logging.getLogger(__name__)
    if debug:
        import sys

        # loop.set_debug(True)
        log.setLevel(logging.DEBUG)
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(logging.DEBUG)
        log.addHandler(h)

    async with BleakClient(address, loop=loop) as client:
        x = await client.is_connected()
        log.info("Connected: {0}".format(x))

        for service in client.services:
            log.info("[Service] {0}: {1}".format(service.uuid, service.description))
            for char in service.characteristics:
                if "read" in char.properties:
                    try:
                        value = bytes(await client.read_gatt_char(char.uuid))
                    except Exception as e:
                        value = str(e).encode()
                else:
                    value = None
                log.info(
                    "\t[Characteristic] {0}: ({1}) | Name: {2}, Value: {3} ".format(
                        char.uuid, ",".join(char.properties), char.description, value
                    )
                )
                for descriptor in char.descriptors:
                    value = await client.read_gatt_descriptor(descriptor.handle)
                    log.info(
                        "\t\t[Descriptor] {0}: (Handle: {1}) | Value: {2} ".format(
                            descriptor.uuid, descriptor.handle, bytes(value)
                        )
                    )


if __name__ == "__main__":
    address = "B4:99:4C:59:66:01"
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run2(address, loop, True))

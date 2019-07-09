'''
DO NOT USE. THIS DOES NOT WORK


Using bleak
pip3 install bleak
'''

import asyncio
from bleak import discover

async def run():
    devices = await discover()
    for d in devices:
        print(d)

loop = asyncio.get_event_loop()
loop.run_until_complete(run())

import asyncio

from bleak import BleakClient


async def print_services(mac_addr: str, loop: asyncio.AbstractEventLoop):
    async with BleakClient(mac_addr, loop=loop) as client:
        svcs = await client.get_services()
        print("Services:", svcs)
        for s in svcs:
            print(s)


mac_addr = "B4:99:4C:59:66:01"
loop = asyncio.get_event_loop()
loop.run_until_complete(print_services(mac_addr, loop))




import asyncio
from bleak import BleakClient

address = "B4:99:4C:59:66:01"
MODEL_NBR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"

temp_handle = 0x0029
temp_cmd = b"01ba040000"

async def run(address, loop):
    async with BleakClient(address, loop=loop) as client:
        model_number = await client.read_gatt_char(MODEL_NBR_UUID)
        print("Model Number: {0}".format("".join(map(chr, model_number))))
        write_test = await client.write_gatt_descriptor(temp_handle, temp_cmd) #https://bleak.readthedocs.io/en/latest/api.html
        print(write_test)

loop = asyncio.get_event_loop()
loop.run_until_complete(run(address, loop))





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

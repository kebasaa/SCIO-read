# Read the SCiO spectrometer built by [Consumer Physics](https://www.consumerphysics.com/)

In this small project, I'm trying to hack the SCiO spectrometer in order to create a Python library to read scans directly. As I'm not very experienced, this is first going to be a documentation effort of the device, and hopefully in the future also some code to make it work. Any input and help is appreciated.

## Hardware

Sparkfun published a hardware teardown of the SCiO device: [https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-](https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-). Also, a reddit channel is available for discussing the device: [https://www.reddit.com/r/scio/](https://www.reddit.com/r/scio/)

## Measurement principles
The SCiO illuminates the sample with a light and measures the reflected light in a number of wavebands. This measured spectrum is then used in large online databases to identify the content of the sample. Obviously, I'm trying to gain access raw data so I don't care too much about the online tools. 

Consumer Physics describes the process as follows in their forum: he spectrometer breaks down the light to its spectrum (the spectra), which includes all the information required to detect the result of this interaction between the illuminated light and the molecules in the sample. This means that SCiO analyses the overall spectra that is received and, comparing it to different algorithms and information provided, identifies or evaluates it.

For example, if you know the basic spectra of a watermelon, and then see that as the watermelon gets sweeter, meaning it has more sugar content, the spectra gradually changes in a specific manner, you will be able to build an algorithm in accordance. In recognizing the existence of a specific material, such as ginger, in a sample, you will need to see if the reflectance of the material changes in a specific manner when the ginger is present.  Thus, you will need two samples of the material – with and without ginger.

In order to achieve good results, large databases of materials and their properties are necessary. Usually, machine learning assists the identification. For example for tomatoes, 40 samples are recommended as a rule of thumb as a properly sized collection for a feasibility test. However, a comprehensive application should be based on hundreds of samples and thousands of scans.

## Device specifications
The specs are rather badly documented. I have managed to glean the following data so far though:
* Scans in NIR, range of 700-1100nm according to Consumer Physics, or 740-1070nm according to a [scientific research paper on ArXiv](https://arxiv.org/pdf/1805.04051.pdf)
* Bandwidth: unknown

## Currently known Bluetooth LE (BLE) handles and data format
So far, I have identified the following BLE UUIDs/handles
* Button: Notification handle `0x002c` reads a hex value `01` upon button press
* Device name: Handle `0x2a00` (equivalent to UUID 00002a00-0000-1000-8000-00805f9b34fb)
* Device/System ID: Handle `0x0012` (uuid: 00002a23-0000-1000-8000-00805f9b34fb)
* To start a scan, write `01ba020000` to handle `0x0029` (uuid 00003492-0000-1000-8000-00805f9b34fb). The answer comes in on notification handle `0x0025`. In Gatttool, the command is

```bash
    char-write-cmd 0x0029 01ba020000
```
	
* The scanning handle (`0x0029`, see above) accepts additional messages. The app sends the following before scanning. I have no clue what they mean:

```
    01ba050000
    01ba0e0000
    01ba0b0900000000000000000000
    01ba040000
	01ba020000 // This is the actual scanning command
```

## Data format
I captured BLE data on Linux using gatttool, with the following command:

```bash
    sudo gatttool -i hci0 -b xx:xx:xx:xx:xx:xx --char-write-req -a 0x0029 -n 01ba020000 --listen > file1.txt
```

Where `xx:xx:xx:xx:xx:xx` stands for your SCiO's MAC address

According to "Consumer Physics", the SCiO app with a developer license (which I don't have) can output raw data as CSV divided into three parts: The spectrum, wr_raw and sample_raw (from their forums). The first part is the reflectance spectrum (R) – how much of the light is reflected back by the sample. The second part is the raw signal from the sample (S), and the third is the raw signal from the calibration (C). In order to calculate reflectance, the equation is: R=S/C.

Raw ble messages containing data are structured as follows:
* The SCiO sends raw measurements to a server online as bytes coded in Base64. The server then returns the data as JSON. Unfortunately, this means that without an example JSON or CSV file provided by someone with a developer license, it may be impossible to hack it.
* Byte 0 of every message of a scan is an ID, coming in 3 batches, from 01-5f, 01-5f and 01-58
* Byte 1 of the first line of a message (ID = `01`) is a protocol identifier, "ba" (hex) or "-70" (int) to identify the message as using the protocol of scanned data
* Byte 2 (ID = `02`) defines that the incoming data is a spectral measurement
* Bytes 3 and 4 of the first line contain the coded message length.
* Bytes 5-19 of the first line are data
* All subsequent lines: Byte 1 is the line ID (as above), bytes 2-20 are data
* Find some example scans in the folder "example-data" along with the SCiO app's output spectrum of the same materials (images)
* Some example temperature readings are also available in the folder "example-data"

## Currently unknown
The following commands have been identified and can be used to read or write commands. For writing messages, I have currently no idea which handle they need to be written to, not what the messages need to contain

| Command (int) | hex | Meaning                | handle & message format |
| ------------- |-----| -----------------------|-----------------|
| -70           | ba  | Incoming data protocol | see above |
| 2             | 02  | Data type: spectrum    | part of protocol above |
| 4             | 04  | Temperature     | contains tempeature of chip, cmos sensor (by Aptina) & object |
| 5             | 05  | Battery state          | ? |
| 11            | 0b  | Set LED status         | ? |
| 14            | 0e  | Read for WR            | ? |
| -108          | 94? | File list (but what files?) | ? |
| -125          | 83? | Reset device           | ? |
| -111          | 91? | Change device name     | ? |


## License

### Software

This software is distributed under the GPL version 3.

### Logos and icons

All logos and icons are trademark of [Consumer Physics](https://www.consumerphysics.com/).

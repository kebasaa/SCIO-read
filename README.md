# Read the SCiO spectrometer built by [Consumer Physics](https://www.consumerphysics.com/)

In this small project, I'm trying to hack the SCiO spectrometer in order to create a Python library to read scans directly. As I'm not very experienced, this is first going to be a documentation effort of the device, and hopefully in the future also some code to make it work. Any input and help is appreciated.

**IMPORTANT, I NEED YOUR HELP:** The SCiO sends raw measurements to a server online as bytes coded in Base64. The server then returns the data as JSON. This means that I **need an example JSON or CSV file**, provided by someone with a developer license. Without this, it may be impossible to hack the device. Please provide this if you have it!

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
* According to [the user nicholas73](https://news.ycombinator.com/item?id=13939068), there were 400 datapoints corresponding to 1 nm spaced wavelengths from 700-1100 nm. Also, they are purposefully sending encrypted/encoded(?) data to your phone, which is then sent to their server ([dancsi](https://news.ycombinator.com/item?id=13941019)).
* [Another paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5862431/) claims that the device creates 331 variables from 740nm to 1070nm.
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
	
* The scanning handle (`0x0029`, see above) accepts a number of messages. The app sends the following before & after scanning:

```
    01ba050000 // inquire battery status
    01ba0e0000 // Ready for WR
    01ba0b0900000000000000000000  // set LED (is this a colour?)
    01ba040000 // inquire device temperature before
    01ba020000 // This is the actual scanning command
    01ba040000 // inquire device temperature after
```

## Data format
I captured BLE data on Linux using gatttool, with the following command:

```bash
    sudo gatttool -i hci0 -b xx:xx:xx:xx:xx:xx --char-write-req -a 0x0029 -n 01ba020000 --listen > file1.txt
```

Where `xx:xx:xx:xx:xx:xx` stands for your SCiO's MAC address

According to "Consumer Physics", the SCiO app with a developer license (which I don't have) can output raw data as CSV divided into three parts: The spectrum, wr_raw and sample_raw (from their forums). The first part is the reflectance spectrum (R) – how much of the light is reflected back by the sample. The second part is the raw signal from the sample (S), and the third is the raw signal from the calibration (C). In order to calculate reflectance, the equation is: R=S/C.

It appears that for every scan, the SCIO measures twice. It probably then takes the mean between the 2 scans. Every SCIO bluetooth LE message contains 3 parts: scan 1, scan 2 and calibration (those are my current guesses).

Raw ble messages containing data are structured as follows:
* Byte 0 of every message of a scan is an ID, coming in 3 batches, from 01-5f, 01-5f and 01-58
* Byte 1 of the first line of a message (ID = `01`) is a protocol identifier, "ba" (hex) or "-70" (int) to identify the message as using the protocol of scanned data
* Byte 2 (ID = `02`) defines that the incoming data is a spectral measurement
* Bytes 3 and 4 of the first line contain the coded message length.
* Bytes 5-19 of the first line are data
* All subsequent lines: Byte 1 is the line ID (as above), bytes 2-20 are data
* Find some example scans in the folder "example-data" along with the SCiO app's output spectrum of the same materials (images)
* A specific calibration plate was scanned with a device called the PolyPen, which has a spectral overlap with the SCiO. The scan of the calibration plate using both the SCiO and the PolyPen will be added to "example-data"
* Some example temperature readings are also available in the folder "example-data"

## Instructions for reading raw data with gatttool

1. On Linux, install _gatttool_ and _hcitool_. I'm using Ubuntu, to install:

```bash
    sudo apt-get install bluez
```

2. Turn on your SCIO with a long press on the button

3. Run hcitool to find out what your SCIO's MAC address is. It will have a name like _SCiOmyScio_ or whatever you named it:

```bash
    sudo hcitool lescan
```

4. Run gatttool with your SCIO's MAC address to collect your own data. This will store it in "file1.txt". Replace xx:xx:xx:xx:xx:xx with the MAC address you found in step 3. During the scan, the SCIO indicator light will be yellow.

```bash
    sudo gatttool -i hci0 -b xx:xx:xx:xx:xx:xx --char-write-req -a 0x0029 -n 01ba020000 --listen > file1.txt
```

5. Stop saving data to your file with _Ctrl+C_ after the indicator light of the SCIO goes back to blue.

6. In a text editor, edit your file1.txt: Remove the first line saying _"Characteristic value was written successfully"_ and in the beginning of each line remove _"Notification handle = 0x0025 value: "_. Then save the file

## Currently unknown
The meaning of the hex raw data is currently unknown. Some of the commands were identified, but not completely. I have currently no idea which handle they need to be written to, not what the messages need to contain

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

## Credits
My thanks go out to the following people:
* Github user [onoff0](https://github.com/onoff0) for some ideas regarding decoding. This lead me to try [Hexinator](https://hexinator.com/)
* Github user [franklin02](https://github.com/franklin02) for providing example scans, including details about the precision (14 decimals!) and number of bands
* My roommate D for ideas about data structure. It really helped uncover that the SCIO sends a header in the first 2 messages of each scan

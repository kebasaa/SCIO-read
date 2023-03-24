[![GitHub](https://img.shields.io/github/license/kebasaa/SCIO-read)](https://www.gnu.org/licenses/gpl-3.0)

# Read the SCiO spectrometer built by [Consumer Physics](https://www.consumerphysics.com/)

In this small project, I'm trying to create a Python library to scan and interpret data from the the SCiO spectrometer. As I'm not very experienced, this is first going to be a documentation effort of the device, and hopefully in the future the code will work. Any input and help is appreciated.

**IMPORTANT, I NEED YOUR HELP:** The SCiO sends raw measurements to a server online as bytes coded in Base64. The server then returns the data as JSON. However, it is unclear how the 1800 bytes of the sample reading, 1800 bytes of sampleDark and 1656 bytes of sampleGradient are turned into 331 float values representing a normalised reflectance spectrum from 0-1. If you have any insights, please let me know.

Further: It appears that the raw bytes reported by the SCiO don't correspond to the Base64 string sent to the Consumer Physics server. There might be some encryption happening in between these stages, can someone help decrypt it based on this information? See *02_extract_log_scan.ipynb* to obtain the data from log files or check the folder *01_rawdata/log_extracted/*

**DISCLAIMER**: All this code is experimental. I am trying to reverse-engineer the device in order to read the reflectance spectrum, but any help is appreciated! Scan data can't currently be fully decoded, this is an area where help is particularly appreciated

## Changelog

- 2023-03-21 Extract data from log files
  - **02_extract_log_scan.ipynb**: Extract and store data from log files
- 2023-03-19 Attempts at decoding the data
  - **03_scio_analyse_devel.ipynb**: Decode the data (initial unsuccessful attempts)
- 2023-03-01 Creating a class for interaction with the hardware:
  - **01_scio_scan.ipynb**: Read the device metadata and trigger a scan through USB
- 2020-05-29 Moved everything to jupyter notebooks:
  - **01_scio_scan.ipynb** identifies the device, then performs a scan and saves the raw binary data (encoded as base64) into a .json file.
  - **02_analyse.ipynb** is used to analyse the rawdata and convert it to actual numbers. It does not fully work yet
  
## Usage of the code in this repository

1. Connect the SCiO to your computer (currently supports Windows) through USB
2. Run the code in *01_scio_usb.ipynb* to calibrate and scan. This can save files with raw data
3. You can extract scan data from logs using *02_extract_log_scan.ipynb*. What is interesting is that the raw bytes reported by the SCiO don't correspond to the Base64 string sent to the server. Is some encryption happening in between these stages?
4. Run *03_scio_analyse_devel.ipynb* to attempt to decode the data

## Documentation of the SCiO device

The following is an attempt to document as much as possible of the SCiO's functioning for the reverse-engineering effort. Any additional information is appreciated.

### Hardware & device specifications

The specs are rather badly documented. The following information is known so far:

- Scans cover the **near-infrared (NIR) range**, most likely at a 1nm bandwidth:
  - The range of **740-1070nm** is claimed by multiple scientific publications:
    - [Erikson et al., 2019; IEEE Robotics And Automation Letters](https://ieeexplore.ieee.org/abstract/document/8610196), also see [ArXiv](https://arxiv.org/pdf/1805.04051.pdf)
    - [Hershberger et al., 2022; The Plant Phenome Journal](https://doi.org/10.1002/ppj2.20040)
    - [Kosmowski & Worku, 2018; PLoS One](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5862431/) stated that there are 331 datapoints from 740nm to 1070nm.
  - Consumer Physics claims a range of **700-1100nm** (in their own forums, when they were still available), confirmed by the following sources:
    - [Forum user savorypiano](https://news.ycombinator.com/item?id=13939068) stated that there were 400 datapoints corresponding to 1 nm spaced wavelengths from 700-1100 nm.
- Data recorded by the SCiO is sent through the phone to the Consumper Physics servers
  - Scan data is apparently **encrypted** ([Forum user dancsi](https://news.ycombinator.com/item?id=13941019))
  - Scan data contains the following (where "white" denotes the calibration):
    - sample and sample_dark (This starts with base64: AAAAA, 1800 bytes long): Raw spectral data representing light reflected from the sample (or calibration target)
    - sample_white and sample_white_dark (Starts with base64: AAAAA, 1800 bytes long): Raw spectral data from the SCIO's internal dark current reference, i.e. the background signal when there is no light
    - sample_white_gradient and sample_gradient (Starts with base64: bgAAA, 1656 bytes long): Raw spectral data from the SCIO's internal white reference when measuring a known white reference
  - Metadata contains the following information (with example data):
    - "device_id":"8032AB45611198F1"
    - "sampled_at":"2021-10-20T10:58:58.729+03:00" (Timestampe of current scan)
    - "sampled_white_at":"2021-10-20T10:53:18.334+03:00" (Timestampe of calibration scan)
    - "scio_edition":"scio_edition"
    - "mobile_GPS":{"longitude":-----,"latitude":----,"locality":"-----","country":"-----","admin_area":"-----","address_line":"-----" (This information should be private and should not matter for scan analysis, but it is transferred)
    - "mobile_mac_address":"------" (Phone MAC address. Again, this information should be private and doesn't matter for scan analysis)
    - "i2s_tag_config":"20150812-e:PRODUCTION" (Seems to be a hardware version)
- **Hardware teardown** documented by Sparkfun: [https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-](https://learn.sparkfun.com/tutorials/scio-pocket-molecular-scanner-teardown-)
- Reddit channel dedicated to the device: [https://www.reddit.com/r/scio/](https://www.reddit.com/r/scio/)
- Old versions of the SCiO app (I believe around the 1.2 releases) created log files that could be found in one of the folders on the phone. These log files contain the raw data and spectrum returned by the Consumer Physics server. For these versions, see [APKpure](https://apkpure.com/scio-pocket-molecular-sensor/com.consumerphysics.consumer/versions)

### Measurement principle

The SCiO illuminates the sample with a light and measures the reflected light in a number of wavelengths. This measured spectrum is then used in large online databases to identify the content of the sample. Obviously, the code and documentation in this repository is trying to gain access raw scan data for research purposes, i.e. access to the online tools is not an aim.

According to Consumer Physics, the SCiO app with a developer license (which I don't have) can output raw data as CSV divided into three parts: The spectrum, wr_raw and sample_raw (from their forums). The first part is the reflectance spectrum (R) – how much of the light is reflected back by the sample. The second part is the raw signal from the sample (S), and the third is the raw signal from the calibration (C). In order to calculate reflectance, the equation is: R=S/C.

It appears that for every scan, the SCIO measures twice. It probably then takes the mean between the 2 scans. Every SCIO bluetooth LE message contains 3 parts: sample, sampleDark and sampleGradient (No clue so far what that those mean or how to convert them). Calibration is done by scanning the calibration box, and comparing a scan with that calibration scan.

### Sample identification

Consumer Physics described the process as follows in their forum: _The spectrometer breaks down the light to its spectrum (the spectra), which includes all the information required to detect the result of this interaction between the illuminated light and the molecules in the sample. This means that SCiO analyses the overall spectra that is received and, comparing it to different algorithms and information provided, identifies or evaluates it._

_For example, if you know the basic spectra of a watermelon, and then see that as the watermelon gets sweeter, meaning it has more sugar content, the spectrum gradually changes in a specific manner, you will be able to build an algorithm in accordance. In recognizing the existence of a specific material, such as ginger, in a sample, you will need to see if the reflectance of the material changes in a specific manner when the ginger is present. Thus, you will need two samples of the material – with and without ginger._

_In order to achieve good results, large databases of materials and their properties are necessary. Usually, machine learning assists the identification. For example for tomatoes, 40 samples are recommended as a rule of thumb as a properly sized collection for a feasibility test. However, a comprehensive application should be based on hundreds of samples and thousands of scans._

## SCiO communication protocol and BLE (Bluetooth LE) handles

### BLE handles

The following BLE UUIDs/handles have been identified so far
- Button: Notification handle `0x002c` reads a hex value `01` upon button press
- Device name: Handle `0x2a00` (equivalent to UUID 00002a00-0000-1000-8000-00805f9b34fb)
- Device/System ID: Handle `0x0012` (uuid: 00002a23-0000-1000-8000-00805f9b34fb)
- To start a scan, write `01ba020000` to handle `0x0029` (uuid 00003492-0000-1000-8000-00805f9b34fb). The answer comes in on notification handle `0x0025`.
- The scanning handle (`0x0029`, see above) accepts a number of messages (protocol see below). The app sends the following before & after scanning:

```
    01ba050000 // inquire battery status
    01ba0e0000 // Ready for WR
    01ba0b0900000000000000000000  // set LED (is this a colour?)
    01ba040000 // inquire device temperature before
    01ba020000 // This is the actual scanning command
    01ba040000 // inquire device temperature after
```

### USB control

Commands can be sent to the USB port by sending bytes corresponding to the above commands sent to the BLE scanning handle described above, using the same protocol.

### Data protocol

Raw response messages from the SCiO are structured as follows:
- Only for BLE (not USB): Byte 0 of every message of a scan is an ID (typically `01`), coming in 3 batches, from 01-5f, 01-5f and 01-58
- Byte 1 of the first line of a message (`ba` or integer -70) is a protocol identifier, to inform the app what protocol the following data is
- Byte 2 (ID = `02`) defines that the incoming data is a spectral measurement. More commands, see table below
- Bytes 3 and 4 of the first line contain the coded message length, in "short" format
- For BLE: Bytes 5-19 of the first line are data
- All subsequent lines in BLE data: Byte 1 is the line ID (from 01-5f, 01-5f and 01-58 for sample, sampleDark and sampleGradient, respectively), bytes 2-20 are data
- For USB: All remaining bytes are data

| Command (int) | hex | Meaning                | handle & message format |
| ------------- |-----| -----------------------|-----------------|
| -70           | ba  | Incoming data protocol | see above |
| 2             | 02  | Data type: spectrum    | part of protocol above |
| 4             | 04  | Temperature     | contains tempeature of chip, cmos sensor (by Aptina) & object (always 0) |
| 5             | 05  | Battery state          | contains charge %, battery health, voltage, etc. |
| 11            | 0b  | Set LED status         | ? |
| 14            | 0e  | Read for WR            | ? |
| -108          | 94  | File list (likely firmware) | file identifiers as integers |
| -111          | 91  | Set device name        |   |
| -121          | 87  | File header            | file headers as integers |
| -123          | 85  | BLE status             |   |
| -124          | 84  | BLE ID                 |   |
| -125          | 83  | Reset device           |   |


How the raw scan data can be decoded is currently still unknown.

To help with the reverse-engineering effort, the following data is available:
- Some example scans are available in the folder "example-data" along with the SCiO app's output spectrum of the same materials (as screenshots)
- A specific calibration plate was scanned with a device called the PolyPen, which has a spectral overlap with the SCiO. The scan of the calibration plate using both the SCiO and the PolyPen are available in the folder "example-data"

### Instructions for reading raw data (without the script in this repository)

#### Through USB on the console

1. Connect the SCIO to your computer with a USB cable, and turn it on

2. On Linux, open the console and type to read data to "file.txt"

```bash
    cat /dev/ttyACM0 | hexdump -C > file.txt
```

3. In a second console window, type your command with a \x between each byte, for example for the temperature reading type

```bash
    echo -n -e "\x01\xba\x04\x00\x00" > /dev/ttyACM0
```

4. Wait a moment, until the SCIO stops blinking. Then go to the first console window and hit Ctrl+C to stop reading from the serial port. You will now have your readings in "file.txt"

#### Through bluetooth with gatttool

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

## License

### Software

This software is distributed under the GPL version 3.

### Logos and icons

All logos and icons are trademark of [Consumer Physics](https://www.consumerphysics.com/).

## Credits
My thanks go out to the following people:
- Github user [earwickerh](https://github.com/earwickerh) for suggestions on decoding the scan data.
- Github user [onoff0](https://github.com/onoff0) for some ideas regarding decoding. This lead me to try [Hexinator](https://hexinator.com/)
- Github user [franklin02](https://github.com/franklin02) for providing example scans, including details about the precision (14 decimals!) and number of bands
- Github user [JanBessai](https://github.com/JanBessai) for information on reading SCIO data through USB
- My previous roommate D for ideas about data structure. It really helped uncover that the SCIO sends a header in the first 2 messages of each scan

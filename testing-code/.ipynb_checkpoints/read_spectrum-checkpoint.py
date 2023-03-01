# Random: shine light & use camera RGB as spectrometer

# Convert a hex value to a signed int
def hex2int2(hexstr,bits):
    value = int(hexstr,16)
    if value & (1 << (bits-1)):
        value -= 1 << bits
    return value
	
def hex2int(hexstr,bits):
    value = int(hexstr,16)
    return value

def getU8(data, index):
    return float(data[index])

def getU16(data, index):
    return float( (int(getU8(data, index + 1)) << 8) | (int(getU8(data, index)) & 255) )

def getU32(data, index):
    dat = data[index:(index+4)]
    return float( ((( int(dat[0] & 255)) + (( int(dat[1] & 255)) << 8)) + (( int(dat[2] & 255)) << 16)) + (( int(dat[3] & 255)) << 24) )
	
def hex2float3(data, index):
    import struct
    data_list = data[index:(index+4)]
    aa = bytearray(data_list) 
    return struct.unpack('<f', aa)
	
def hex2float2(data, index):
    import numpy as np
    data_list = data[index:(index+4)]
    data_bytes = np.array(data_list, dtype=np.uint8)
    data_as_float = data_bytes.view(dtype=np.float32)
    return(data_as_float[0])

from ctypes import *
def hex2float(data, index):
    #from ctypes import *
    #cur_hex_str = hex(data[index+3])[2:4]
    cur_hex_str = ""
    for i in range(5):
        cur_hex_str += "{0:0{1}x}".format(data[index+i],2)
	#cur_hex_str = hex(data[index])[2:4] + hex(data[index+1])[2:4] + hex(data[index+2])[2:4] + hex(data[index+3])[2:4] + hex(data[index+4])[2:4]
    cur_hex_int = int(cur_hex_str,16)
    cp = pointer(c_int(cur_hex_int))
    fp = cast(cp, POINTER(c_float))
    return(fp.contents.value)
	
fname="../example-data/file1.txt"

with open(fname) as f:
    content = f.readlines()
# remove whitespace characters like `\n` at the end of each line & split by space characters
content = [x.strip().split() for x in content]

print("Read and organise the incoming data stream")
print("------------------------------------------")
# Define protocol
#PROTOCOL_MESSAGE = -70 # defines which protocol to use. This is if converted to signed
PROTOCOL_MESSAGE = 186 # defines which protocol to use. This is unsigned


restLength = 0
data = [ ]

for line in content:
    if(hex2int(line[0],8) == 1):
        temp = [ ]
        print("Reading first line of data")
        if(hex2int(line[1],8) == PROTOCOL_MESSAGE):
            print("    Identified as spectral data")
        command = hex2int(line[2],8)
        overallLength = (hex2int(line[3],8) & 255) | ((hex2int(line[4],8) & 255) << 8)
        print("    Rest length: ", restLength)
        print("    Overall length: ",overallLength)
        restLength = overallLength
        startingByte = 5
    else:
        startingByte = 1
    # Now read the data
    #print("Package number: ", hex2int(line[0],8))
    rest = min(len(line), overallLength + startingByte)
    for i in range(startingByte, rest):
        temp.append(hex2int(line[i],8))
        restLength-=1;
    if (restLength <= 0):
        print("    Done")
        data.append(temp)
# After this, the data is read as integers and nothing was done with it. I still need to figure out conversion to a proper spectrum
print("    Rest length: ", restLength)

print("")
print("Converting to floating point values")
print("-----------------------------------")
print("    Data contains " + str(len(data)) + " parts")
df = [ ]
for i in range(len(data)):
    print("Measurement part " + str(i))
    temp = [ ]
    print("    Total # of hex values: " + str(int(len(data[i]))))
    startingByte = 1
    if(int(len(data[i])) == 1800):
        startingByte = 145
        print("    Omitting # hex values: 145  (header)")
    else: print("    Omitting # hex values: 1    (header)")
    print("    Total # of bands     : " + str(int((len(data[i])-startingByte)/5)))
    for j in range(int((len(data[i])-startingByte)/5)):
        #print(data[i:(i+4)])
        #temp.append( data[index:(index+4)] )
        #temp.append( getU32(data[i], j*5+startingByte)  )#/ 10000000000 )
        temp.append( hex2float(data[i], j*5+startingByte))
    df.append(temp)
#print(df[0])
#print(df[1])
print(df[2])

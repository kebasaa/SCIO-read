
def hex2int(hexstr,bits):
    value = int(hexstr,16)
    if value & (1 << (bits-1)):
        value -= 1 << bits
    return value

def getU8(data, index):
    return float(data[index])

def getU16(data, index):
    return float( (int(getU8(data, index + 1)) << 8) | (int(getU8(data, index)) & 255) )

def getU32(data, index):
    dat = data[index:(index+4)]
    return float( ((( int(dat[0] & 255)) + (( int(dat[1] & 255)) << 8)) + (( int(dat[2] & 255)) << 16)) + (( int(dat[3] & 255)) << 24) )

fname="./example-data/temp1.txt"

with open(fname) as f:
    content = f.readlines()
# remove whitespace characters like `\n` at the end of each line & split by space characters
content = [x.strip().split() for x in content]

# Define protocol
PROTOCOL_MESSAGE = -70 # defines which message to look for

restLength = 0
data = [ ]

for line in content:
    if(hex2int(line[0],8) == 1):
        print("is the first line")
        if(hex2int(line[1],8) == PROTOCOL_MESSAGE):
            print("data coming in")
        command = hex2int(line[2],8)
        overallLength = (hex2int(line[3],8) & 255) | ((hex2int(line[4],8) & 255) << 8)
        print("Rest length: ", restLength)
        print("Overall length: ",overallLength)
        restLength = overallLength
        startingByte = 5
    else:
        startingByte = 1
    # Now read the data
    #print("Package number: ", hex2int(line[0],8))
    rest = min(20, overallLength + 5)
    for i in range(startingByte, rest):
        data.append(hex2int(line[i],8))
        restLength-=1;
    if (restLength <= 0):
        print(data)
# After this, the data is read as integers and nothing was done with it. I still need to figure out conversion to a proper spectrum
print("Rest length: ", restLength)

cmosTemperature = (getU32(data,0) - 375.22) / 1.4092;
chipTemperature = getU32(data, 4) / 100;
objectTemperature = getU32(data, 8) / 100;
print("CMOS T: ", cmosTemperature)
print("Chip T: ", chipTemperature)
print("Obj. T: ", objectTemperature)


#shine light and camera rgb as spectrometer

# Convert a hex value to a signed int
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
	
fname="../example-data/file1.txt"

with open(fname) as f:
    content = f.readlines()
# remove whitespace characters like `\n` at the end of each line & split by space characters
content = [x.strip().split() for x in content]

# Define protocol
PROTOCOL_MESSAGE = -70 # defines which protocol to use

restLength = 0
data = [ ]

for line in content:
    if(hex2int(line[0],8) == 1):
        temp = [ ]
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
    rest = min(len(line), overallLength + startingByte)
    for i in range(startingByte, rest):
        temp.append(hex2int(line[i],8))
        restLength-=1;
    if (restLength <= 0):
        print("done")
        data.append(temp)
        break
# After this, the data is read as integers and nothing was done with it. I still need to figure out conversion to a proper spectrum
print("Rest length: ", restLength)
print(data)

print(len(data))
df = [ ]
for i in range(len(data)):
    temp = [ ]
    print(int(len(data[i])))
    startingByte = 1
    if(int(len(data[i])) == 1800):
        startingByte = 145
    print(int((len(data[i])-startingByte)/5))
    for j in range(startingByte,int((len(data[i])-startingByte)/5)+startingByte):
        #print(data[i:(i+4)])
        #temp.append( data[index:(index+4)] )
        temp.append( getU32(data[i], j+4)  / 10000000000 )
    df.append(temp)
print(df[0])
print(df[1])
print(df[2])

"""Bounded headerless baseline-JPEG Huffman probe; no dimensions are assumed.

Default tables come from local Pillow encoder fixtures, not SCIO evidence.
Successful entropy parsing alone is not a decoded image or spectrum.
"""
from io import BytesIO
from PIL import Image


class HuffmanTable(dict):
    def compile(self):
        self.lookup=[(0,0)]*65536
        for (size,code),value in self.items():
            start=code<<(16-size);count=1<<(16-size)
            self.lookup[start:start+count]=[(size,value)]*count
        return self


def jpeg_parts(raw):
    if raw[:2]!=b'\xff\xd8': raise ValueError('SOI missing')
    tables={}; pos=2
    while pos<len(raw):
        if raw[pos]!=255: raise ValueError('marker missing')
        marker=raw[pos+1]; n=int.from_bytes(raw[pos+2:pos+4],'big')
        data=raw[pos+4:pos+2+n];pos+=2+n
        if marker==0xc4:
            cursor=0
            while cursor<len(data):
                identifier=data[cursor];counts=data[cursor+1:cursor+17];cursor+=17
                symbols=data[cursor:cursor+sum(counts)];cursor+=sum(counts)
                code=0;index=0;table=HuffmanTable()
                for length,count in enumerate(counts,1):
                    for _ in range(count):
                        table[(length,code)]=symbols[index];index+=1;code+=1
                    code<<=1
                tables[identifier]=table.compile()
        if marker==0xda:
            if raw[-2:]!=b'\xff\xd9':raise ValueError('EOI missing')
            return tables,raw[pos:-2]
    raise ValueError('SOS missing')


def default_tables():
    output=BytesIO();Image.new('RGB',(8,8),(127,128,129)).save(output,format='JPEG',optimize=False)
    return jpeg_parts(output.getvalue())[0]


def unstuff(raw):
    out=bytearray();i=0
    while i<len(raw):
        value=raw[i];out.append(value);i+=1
        if value==255:
            if i==len(raw) or raw[i]!=0:raise ValueError('unstuffed marker or restart')
            i+=1
    return bytes(out)


def decode(raw,dc,ac,bit_offset=0,max_blocks=2048):
    bits=int.from_bytes(raw,'big');length=len(raw)*8
    pos=bit_offset;blocks=[];previous=0
    def take(n):
        nonlocal pos
        if pos+n>length: raise ValueError('truncated coefficient')
        value=(bits>>(length-pos-n))&((1<<n)-1);pos+=n;return value
    def symbol(table):
        nonlocal pos
        remaining=length-pos
        if remaining<=0:raise ValueError('truncated Huffman code')
        prefix=(bits>>(remaining-16))&65535 if remaining>=16 else (bits&((1<<remaining)-1))<<(16-remaining)
        n,value=table.lookup[prefix]
        if not n or n>remaining:raise ValueError('invalid or truncated Huffman code')
        pos+=n
        return value
    def signed(n):
        value=take(n)
        return value if not n or value>=(1<<(n-1)) else value-((1<<n)-1)
    while pos<length:
        remaining=length-pos
        if remaining<=7 and bits&((1<<remaining)-1)==(1<<remaining)-1:break
        if len(blocks)>=max_blocks:raise ValueError('block budget exceeded')
        size=symbol(dc)
        if size>11:raise ValueError('not baseline DC')
        previous+=signed(size);block=[previous]+[0]*63;index=1
        while index<64:
            value=symbol(ac)
            if value==0:break
            if value==0xf0:
                index+=16
                if index>64:raise ValueError('run overflow')
                continue
            run,size=value>>4,value&15
            if not 1<=size<=10:raise ValueError('not baseline AC')
            index+=run
            if index>=64:raise ValueError('coefficient overflow')
            block[index]=signed(size);index+=1
        blocks.append(block)
    return blocks,length-pos


def probe(raw,tables=None):
    tables=default_tables() if tables is None else tables
    hits=[];attempts=0
    for prefix in (0,8,12,16,24,32):
        for trailer in (0,4,8,16):
            chunk=raw[prefix:len(raw)-trailer if trailer else None]
            for stuffing in ('jpeg','none'):
                try:data=unstuff(chunk) if stuffing=='jpeg' else chunk
                except ValueError:continue
                for bit in range(8):
                    for table_id in (0,1):
                        attempts+=1
                        try:blocks,padding=decode(data,tables[table_id],tables[16+table_id],bit)
                        except ValueError:continue
                        if len(blocks)>=4:
                            hits.append({'prefix':prefix,'trailer':trailer,'stuffing':stuffing,
                                'bit_offset':bit,'table_id':table_id,'blocks':len(blocks),'padding_bits':padding})
    return attempts,hits

from io import BytesIO
import pytest
from PIL import Image
from scio_offline.jpeg_entropy import jpeg_parts,default_tables,unstuff,decode,probe


@pytest.mark.parametrize('side',[16,32])
def test_real_headerless_grayscale(side):
    image=Image.frombytes('L',(side,side),bytes((i*37+i//side*19)%256 for i in range(side*side)))
    output=BytesIO();image.save(output,format='JPEG',quality=85,optimize=False)
    tables,entropy=jpeg_parts(output.getvalue())
    blocks,pad=decode(unstuff(entropy),tables[0],tables[16])
    assert len(blocks)==(side//8)**2 and pad<=7
    assert any(h['prefix']==8 and h['trailer']==4 and h['table_id']==0 and h['stuffing']=='jpeg'
               for h in probe(b'12345678'+entropy+b'TAIL',default_tables())[1])


def test_strict_byte_stuffing():
    assert unstuff(b'\x01\xff\x00\x02')==b'\x01\xff\x02'
    with pytest.raises(ValueError):unstuff(b'\xff\xd0')

"""Save codec capabilities and runtime versions without personal paths."""
import argparse
import platform
import _bootstrap
import cryptography
import PIL
from PIL import Image, features
from scio_offline import research as r


def capabilities():
    Image.init()
    names=('JPEG','JPEG2000','PNG','TIFF','GIF','WEBP')
    return {'python':platform.python_version(),'pillow':PIL.__version__,
        'cryptography':cryptography.__version__,
        'image_plugins':{name:name in Image.OPEN for name in names},
        'compiled_features':{name:features.check(name) for name in ('jpg','jpg_2000','zlib','libtiff','webp')},
        'limits':'Unavailable plugin/backend must be reported as unsupported, never a negative decode result.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    r.write_new(a.output,capabilities())

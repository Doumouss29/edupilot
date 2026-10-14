"""Generate PWA icons using Python's standard library (no runtime dependency)."""
from pathlib import Path
import struct
import zlib

OUTPUT=Path(__file__).resolve().parent.parent/'static'
OUTPUT.mkdir(exist_ok=True)

def png_chunk(name,payload):
    return struct.pack('!I',len(payload))+name+payload+struct.pack('!I',zlib.crc32(name+payload)&0xffffffff)

def build(size):
    rows=[]
    for y in range(size):
        line=bytearray([0])
        for x in range(size):
            # Dark blue background; orange rounded-square brand; white diamond.
            color=(32,57,80)
            margin=size*.18
            radius=size*.12
            dx=max(margin-x,0,x-(size-margin))
            dy=max(margin-y,0,y-(size-margin))
            if dx*dx+dy*dy <= radius*radius:
                color=(239,143,50)
            xc,yc=x-size/2,y-size/2
            diamond=abs(xc)+abs(yc)
            if diamond < size*.22 and diamond > size*.13:
                color=(255,255,255)
            line.extend((*color,255))
        rows.append(bytes(line))
    raw=zlib.compress(b''.join(rows),9)
    header=struct.pack('!2I5B',size,size,8,6,0,0,0)
    return b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',header)+png_chunk(b'IDAT',raw)+png_chunk(b'IEND',b'')

for size in (180,192,512):
    (OUTPUT/f'edupilot-{size}.png').write_bytes(build(size))
    print('Generated',size)

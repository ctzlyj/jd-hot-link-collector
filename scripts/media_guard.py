"""Read-only technical MP4 validation; no codec install or browser usage."""
import struct

def inspect_mp4(b):
    i=0;boxes=[];duration=None
    while i+8<=len(b):
        size,kind=struct.unpack('>I4s',b[i:i+8]);head=8
        if size==1:
            if i+16>len(b):raise ValueError('Truncated MP4 box')
            size=struct.unpack('>Q',b[i+8:i+16])[0];head=16
        if size==0:size=len(b)-i
        if size<head or i+size>len(b):raise ValueError('Truncated MP4 box')
        boxes.append(kind.decode('ascii'))
        if kind==b'moov':
            j=i+head
            while j+8<=i+size:
                z,k=struct.unpack('>I4s',b[j:j+8])
                if z<8 or j+z>i+size:raise ValueError('Invalid child box')
                if k==b'mvhd':
                    v=b[j+8];off=j+8+(20 if v==1 else 12)
                    scale=struct.unpack('>I',b[off:off+4])[0]
                    ticks=struct.unpack('>Q' if v==1 else '>I',b[off+4:off+(12 if v==1 else 8)])[0]
                    if not scale:raise ValueError('Invalid MP4 timescale')
                    duration=ticks/scale
                j+=z
        i+=size
    if i!=len(b) or not all(x in boxes for x in ['ftyp','moov','mdat']) or not duration or duration<=0:
        raise ValueError('Incomplete MP4 structure')
    return {'bytes':len(b),'topLevelBoxes':boxes,'durationSeconds':duration,'mp4StructureValid':True}

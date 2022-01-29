import struct
from time import sleep
import dataclasses


class Spinel97:
    PRE = b'*'[0]       # prefix, *
    FRM = 97         # protocol format (97 decimal)
    CR  = 0x0D       # sentinel byte, CR
    BROAD_ADDR = 0xFF
    UNI_ADDR = 0xFE

@dataclasses.dataclass
class Spinel97Msg:
    sig: int
    insn: int
    data: bytes=b''
    addr: int=Spinel97.UNI_ADDR
    def __str__(self): return f'{self.__class__.__name__}(sig=0x{self.sig:02x}, insn=0x{self.insn:02x}, addr=0x{self.addr:02x}, data={self.data})'

    def build(self):
        'Encodes this message into the wire format. *insn* must be set.'
        # if self.ack is not None or self.insn is None: raise RuntimeError('Outgoing messages must have *insn* set and *ack* must be None.')
        num=5+len(self.data)
        if num>0xffff: raise ValueError('Data field too long ({len(self.data)}, max is 0xffff minus 5 bytes overhead).')
        s=(255-(Spinel97.PRE+Spinel97.FRM+num+self.addr+self.sig+self.insn+sum(self.data)))%0x0100
        msg=struct.pack('>2BH3B',Spinel97.PRE,Spinel97.FRM,num,self.addr,self.sig,self.insn)+self.data+struct.pack('2B',s,Spinel97.CR)
        return msg
    @staticmethod
    def parse(msg,checkError=True):
        'Decodes wire data and returns a new Spinel97Msg instance (with *ack* and without *insn*)'
        if len(msg)<7: raise ValueError(f'At least 7 bytes expected (not {len(msg)}).')
        pre,frm,num,addr,sig,ack=struct.unpack('>2BH3B',msg[:7])
        if pre!=Spinel97.PRE: raise ValueError(f'Prefix must be 0x{Spinel97.PRE:x} (not 0x{pre:x}).')
        if frm!=Spinel97.FRM: raise ValueError(f'Format must be 0x{Spinel97.FRM:x} (not 0x{frm:x}).')
        if num!=len(msg)-4: raise ValueError(f'NUM byte inconsistent (is {num}, should be {len(data)-4}).')
        data=msg[7:-2]
        s=(255-(pre+frm+num+addr+sig+ack+sum(data)))%0x0100
        if msg[-2]!=s: raise ValueError(f'SUM byt inconsistent (is {msg[-2]}, should be {s}).')
        if msg[-1]!=Spinel97.CR: raise ValueError('CR byte incorrect (is 0x{data[-1]:x}, should be 0x{Spinel97.CR:x}).')
        if checkError:
            if   ack==0x00: pass
            elif ack==0x01: raise RuntimeError('Unspecified error.')
            elif ack==0x02: raise RuntimeError('Unrecognized instruction.')
            elif ack==0x03: raise RuntimeError('Malformed data.')
            elif ack==0x04: raise RuntimeError('Not permitted.')
            elif ack==0x05: raise RuntimeError('Device error.')
            elif ack==0x06: raise RuntimeError('No data.')
            elif ack>=0x0a and ack<=0x0f: pass # unsolicited data from device
            else: raise RuntimeError('Invalid ACK value 0x{ack:x}.')
        return Spinel97Msg(addr=addr,sig=sig,insn=ack,data=msg[7:-2])

class ThermLogD20:
    async def set_inputs(self,channel: int=0, enable: bool): pass
        # send 0x40 channel enable
        # get ack
        # return
    async def get_inputs(self): pass
        # send 0x41
        # get reply as 20-byte array: 0: off, 1: on, 2: on+disconnected
    async def start_measuring(self): pass # send 0x45 0x01
    async def stop_measuring(self): pass # send 0x45 0x00
    async def get_device_id(self): pass # send 0xf3, receive byte string

import serial
with serial.Serial('/dev/serial/by-id//usb-FTDI_TTL232R-3V3_FTHBOKJC-if00-port0',timeout=2,baudrate=460800) as ser:
    ser.write(msg:=Spinel97Msg(sig=0x02,insn=0xf3,addr=0x31).build())
    print(msg.hex(' ',1))
    while True:
        ln=ser.readline()
        # timeout waiting for reply
        if not ln: continue
        print(Spinel97Msg.parse(ln))

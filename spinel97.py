import struct
import dataclasses


class Spinel97:
    'Constants for the Spinel97 protocol'
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
    def __str__(self): return f'{self.__class__.__name__}(sig=0x{self.sig:02x}, insn=0x{self.insn:02x}, addr=0x{self.addr:02x}{", data=" if self.data else ""}{bytes(self.data).hex(" ",2)})'

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
        data=msg[7:-2]
        if pre!=Spinel97.PRE: raise ValueError(f'Prefix must be 0x{Spinel97.PRE:02x} (not 0x{pre:02x}).')
        if frm!=Spinel97.FRM: raise ValueError(f'Format must be 0x{Spinel97.FRM:02x} (not 0x{frm:02x}).')
        if num!=len(msg)-4: raise ValueError(f'NUM byte inconsistent (is {num}, should be {len(data)-4}).')
        if msg[-1]!=Spinel97.CR: raise ValueError('CR byte incorrect (is 0x{data[-1]:02x}, should be 0x{Spinel97.CR:02x}).')
        s=(255-(pre+frm+num+addr+sig+ack+sum(data)))%0x0100
        if msg[-2]!=s: raise ValueError(f'SUM byt inconsistent (is {msg[-2]}, should be {s}).')
        if checkError:
            if   ack==0x00: pass
            elif ack==0x01: raise RuntimeError('Unspecified error.')
            elif ack==0x02: raise RuntimeError('Unrecognized instruction.')
            elif ack==0x03: raise RuntimeError('Malformed data.')
            elif ack==0x04: raise RuntimeError('Not permitted.')
            elif ack==0x05: raise RuntimeError('Device error.')
            elif ack==0x06: raise RuntimeError('No data.')
            elif ack>=0x0a and ack<=0x0f: pass # unsolicited data from device
            else: raise RuntimeError('Invalid ACK value 0x{ack:02x}.')
        return Spinel97Msg(addr=addr,sig=sig,insn=ack,data=msg[7:-2])

import decimal
class ThermLogD20:
    'Class for ThermLogD20 logger. Mostly stubs.'
    async def set_inputs(self,channel: int=0, enable: bool=True): pass
        # send 0x40 channel enable
        # get ack
        # return
    async def get_inputs(self): pass
        # send 0x41
        # get reply as 20-byte array: 0: off, 1: on, 2: on+disconnected
    async def start_measuring(self): pass # send 0x45 0x01
    async def stop_measuring(self): pass # send 0x45 0x00
    async def get_device_id(self): pass # send 0xf3, receive byte string

    @dataclasses.dataclass
    class Point:
        'ThermLogD20 measurement point.'
        channel: int
        power: int
        state: int
        temp: decimal.Decimal
        def __str__(self):
            if self.power or self.state: err=f'{"!" if self.power else "_"}{"!" if self.state else "_"}'
            else: err=''
            return f'{self.channel}{err}: {self.temp} °C'

import serial
with serial.Serial('/dev/serial/by-id//usb-FTDI_TTL232R-3V3_FTHBOKJC-if00-port0',timeout=2,baudrate=460800) as ser:
    for msg in [
        # identify
        Spinel97Msg(sig=0x02,insn=0xf3,addr=0x31),
        # disable all channels
        Spinel97Msg(sig=0x04,insn=0x40,data=b'\x00\x00'),
        # enable channel 1
        Spinel97Msg(sig=0x04,insn=0x40,data=b'\x01\x01'),
        # query channel status
        Spinel97Msg(sig=0x05,insn=0x41),
        # start measurement
        Spinel97Msg(sig=0x06,insn=0x45,data=b'\x01')
    ]:
        print(f'→ {msg.build().hex(" ",1):<40} | {msg}')
        ser.write(msg.build())

    buf=bytearray()
    todo=0 # remaining bytes for message in progress
    # for now just crude incremental packet construction
    # later use asyncio-serial and define a proper protocol class
    while True:
        c=ser.read(1)
        if len(c)==0: continue # timeout waiting for data
        assert len(c)==1
        c=c[0]
        if len(buf)==0 and c!=Spinel97.PRE:
            print(f'[Skipping 0x{c:02x}]')
            continue
        buf.append(c)
        if len(buf)==4:
            if buf[:2]!=bytes([Spinel97.PRE,Spinel97.FRM]):
                print(f'[Invalid header of {buf.hex(" ",1)}, discarding]')
                buf=bytearray()
                continue
            todo=struct.unpack('>H',buf[2:4])[0]
            # print(f'Got length: {todo}')
        else: todo-=1
        if todo==0:
            if c!=Spinel97.CR: print('[Invalid message, not ending in CR where it should...?]')
            msg=Spinel97Msg.parse(buf)
            if msg.insn==0x0d:
                # decode temperature data
                pts=[ThermLogD20.Point(channel=ch,power=pw,state=st,temp=struct.unpack('<i',t0+t1+t2+t3)[0]/decimal.Decimal(100)) for ch,pw,st,t1,t0,t3,t2 in struct.iter_unpack('>3B4c',msg.data)]
                print(', '.join([str(pt) for pt in pts]))
            else: print(f'← {buf.hex(" ",1)}  |  {msg}')
            buf=bytearray()

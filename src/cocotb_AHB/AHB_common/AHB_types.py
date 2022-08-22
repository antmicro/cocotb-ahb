# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

import enum
from collections import namedtuple
from typing import Dict, Any, Tuple, NamedTuple

class HREADY(enum.IntEnum):
    WaitState = 0b0
    Working   = 0b1

class HRESP(enum.IntEnum):
    Successful = 0b0
    Failed     = 0b1

class HEXOKAY(enum.IntEnum):
    Failed     = 0b0
    Successful = 0b1

class HBURST(enum.IntEnum):
    Single = 0b0
    Incr   = 0b1
    Wrap4  = 0b10
    Incr4  = 0b11
    Wrap8  = 0b100
    Incr8  = 0b101
    Wrap16 = 0b110
    Incr16 = 0b111

class HMASTLOCK(enum.IntEnum):
    UnLocked = 0b0
    Locked   = 0b1


class HPROT(NamedTuple):
    width: int = 7
    data: bool = True
    privileged: bool = True
    bufferable: bool = False
    modifiable: bool = False
    lookup: bool = False
    allocate: bool = False
    shareable: bool = False


def hProt_to_int(hProt: HPROT) -> int:
    ret = 0
    for i in range(hProt.width):
        ret | hProt[i+1] << i;
    return ret


class HSIZE(enum.IntEnum):
    Byte        = 0b0
    Halfword    = 0b1
    Word        = 0b10
    Doubleword  = 0b11
    Quadword    = 0b100
    Octupleword = 0b101
    Bit512      = 0b110
    Bit1024     = 0b111

class HNONSEC(enum.IntEnum):
    Secure    = 0b0
    NonSecure = 0b1

class HEXCL(enum.IntEnum):
    NonExcl = 0b0
    Excl    = 0b1

class HTRANS(enum.IntEnum):
    Idle   = 0b0
    Busy   = 0b1
    NonSeq = 0b10
    Seq    = 0b11

class HWRITE(enum.IntEnum):
    Read  = 0b0
    Write = 0b1

class HSEL(enum.IntEnum):
    NotSel = 0b0
    Sel    = 0b1

class HREADYOUT(enum.IntEnum):
    NotReady = 0b0
    Ready    = 0b1

class HMONITOR():
    def __init__(self, manager: bool =True):
        self_is_manager = manager
        self.ready: bool
        self.command: Dict[Any, Any] = {}
        self.resp: Dict[Any, Any] = {}
        self.wdata: int = 0


class MCMD(NamedTuple):
    hAddr: int = 0
    hBurst: HBURST = HBURST.Incr
    hMastlock: HMASTLOCK = HMASTLOCK.UnLocked
    hProt: HPROT = HPROT()
    hSize: HSIZE = HSIZE.Byte
    hNonsec: HNONSEC = HNONSEC.Secure
    hExcl: HEXCL = HEXCL.NonExcl
    hMaster: int = 0
    hTrans: HTRANS = HTRANS.Idle
    hWstrb: int = 0
    hWrite: HWRITE = HWRITE.Read


class ICMD(NamedTuple):
    hAddr: int = 0
    hBurst: HBURST = HBURST.Incr
    hMastlock: HMASTLOCK = HMASTLOCK.UnLocked
    hProt: HPROT = HPROT()
    hSize: HSIZE = HSIZE.Byte
    hNonsec: HNONSEC = HNONSEC.Secure
    hExcl: HEXCL = HEXCL.NonExcl
    hMaster: int = 0
    hTrans: HTRANS = HTRANS.Idle
    hWstrb: int = 0
    hWrite: HWRITE = HWRITE.Read
    hSel: HSEL = HSEL.NotSel


class MDATA(NamedTuple):
    hWData: int = 0


class IDATA(NamedTuple):
    hWData: int = 0


class SRESP(NamedTuple):
    hResp: HRESP = HRESP.Successful
    hReadyOut: HREADYOUT = HREADYOUT.NotReady
    hExOkay: HEXOKAY = HEXOKAY.Failed
    hRData: int = 0


class IRESP(NamedTuple):
    hResp: HRESP = HRESP.Successful
    hExOkay: HEXOKAY = HEXOKAY.Failed
    hRData: int = 0

# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from random import randint

from typing import Any, Tuple, Dict, List, Set, TypeVar
from copy import copy
from math import log2

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly, Event # type: ignore
from cocotb_bus.bus import Bus # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface

T = TypeVar('T')

class SimTrafficGenerator(ManagerInterface, MonitorableInterface, SimulationInterface):
    def __init__(self, addr_width: int, bus_width: int, *, secure_transfer: bool = False,
                 nonsec_read: bool = False, nonsec_write: bool = False,
                 exclusive_transfers: bool = False, write_strobe: bool = False,
                 burst: bool = False, name: str = "", master_id: int = 0):

        bus_byte_width = bus_width//8
        assert bus_byte_width*8 == bus_width, "bus_width must be multiple of 8"
        assert bus_byte_width in [1, 2, 4, 8, 16, 32, 64, 128], \
                                    "Bus byte width must be power of 2 from 1 to 128 bytes wide"
        assert addr_width in range(10, 65), \
                                    "Address wisth must be from range 10 to 64 bits"

        self.addr_width: int = addr_width
        self.bus_width: int = bus_width
        self.bus_byte_width: int = bus_byte_width
        self.max_size: int = int(log2(bus_byte_width))
        self.command: MCMD = MCMD(*self._reset_value)
        self.old_command: MCMD = MCMD(*self._reset_value)
        self.eval_done: Event = Event()
        self.resp: Dict[Any, Any] = {}
        self.valid_cmd: bool = False
        self.master_id = master_id

        self.secure_transfer: bool = secure_transfer
        if secure_transfer:
            self.nonsec_read: bool = nonsec_read
            self.nonsec_write: bool = nonsec_write

        self.exclusive_transfers: bool = exclusive_transfers
        if exclusive_transfers:
            self.exclusive_trans: bool = False
            self.has_exclusive_pending: bool = False
            self.exclusive_id: Tuple[int, HSIZE, HBURST, HNONSEC, int]

        self.burst: bool = burst
        if burst:
            self.bursting: bool = False
            self.burst_addresses: List[int] = []
            self.burst_type: HBURST = HBURST.Incr
            self.burst_sec: HNONSEC
            self.burst_rw: HWRITE
            self.burst_size: HSIZE

        self.write_strobe = write_strobe
        self.to_be_delayed: MDATA = MDATA(0)
        self.delayed: MDATA = MDATA(0)
        self.valid_address_stage: bool = False


    def set_ready(self, hReady: HREADY) -> None:
        self.ready = hReady


    def is_ready(self) -> bool:
        return self.ready == HREADY.Working


    def put_rsp(self, resp: IRESP) -> None:
        self.resp["hrdata"] = resp.hRData
        self.resp["hresp"] = resp.hResp
        if self.exclusive_transfers:
            self.resp["hexokay"] = resp.hExOkay


    def get_cmd(self) -> MCMD:
        return MCMD(*self.command)


    def get_data(self) -> MDATA:
        return self.delayed


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    async def monitor_get_status(self) -> HMONITOR:
        monit = HMONITOR(False)
        await self.eval_done.wait()
        self.eval_done.clear()
        for signal, value in zip(self.old_command._fields, self.old_command):
            monit.command[signal] = value

        for signal, value in self.resp.items():
            monit.resp[signal] = value

        monit.wdata = self.delayed.hWData
        monit.ready = self.is_ready()
        return monit


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        self.command = MCMD(*self._reset_value)


    def do_nothing(self) -> None:
        self.valid_cmd = False
        temp: Dict[Any, Any] = {}
        if self.burst and self.bursting:
            temp["hTrans"] = HTRANS.Busy
            temp["hAddr"] = self.burst_addresses[0]
            temp["hBurst"] = self.burst_type
            temp["hSize"] = self.burst_size
            if self.exclusive_transfers:
                temp["hExcl"] = HEXCL.NonExcl
            temp["hMaster"] = self.master_id
            if self.secure_transfer:
                temp["hNonsec"] = self.burst_sec
            if self.write_strobe:
                temp["hWstrb"] = 0
            temp["hWrite"] = self.burst_rw
        else:
            temp["hTrans"] = HTRANS.Idle
            size = HSIZE(randint(0, self.max_size))
            temp["hAddr"] = randint(0, 2**(self.addr_width - size) - 1) << size
            temp["hBurst"] = HBURST.Incr
            temp["hSize"] = size
            if self.exclusive_transfers:
                temp["hExcl"] = HEXCL.NonExcl
            temp["hMaster"] = self.master_id
            if self.secure_transfer:
                temp["hNonsec"] = HNONSEC.NonSecure
            if self.write_strobe:
                temp["hWstrb"] = 0
            temp["hWrite"] = HWRITE(randint(0,1))
        self.to_be_delayed = MDATA(0)
        self.command = MCMD(**temp)


    def do_single(self) -> None:
        size = HSIZE(randint(0, self.max_size))
        rw = HWRITE(randint(0,1))
        temp: Dict[Any, Any] = {}

        temp["hAddr"] = randint(0, 2**(self.addr_width - size) - 1) << size
        temp["hBurst"] = HBURST.Single if self.burst else HBURST.Incr
        temp["hSize"] = size
        temp["hExcl"] = HEXCL.NonExcl
        temp["hMaster"] = self.master_id
        temp["hTrans"] = HTRANS.NonSeq
        temp["hWstrb"] = 0
        if rw == HWRITE.Write:
            temp["hWstrb"] = randint(0, 2**self.bus_byte_width-1) if self.write_strobe else 2**self.bus_byte_width - 1
        temp["hWrite"] = rw
        temp["hNonsec"] = HNONSEC.Secure
        if self.secure_transfer:
            if self.nonsec_write and rw == HWRITE.Write:
                temp["hNonsec"] = HNONSEC(randint(0,1))
            if self.nonsec_read and rw == HWRITE.Read:
                temp["hNonsec"] = HNONSEC(randint(0,1))

        self.to_be_delayed = MDATA(0)
        if rw == HWRITE.Write:
            self.to_be_delayed = MDATA(randint(0, 2**self.bus_byte_width-1))

        self.command = MCMD(**temp)


    def do_bursting(self, NonSeq: bool = False) -> None:
        temp: Dict[Any, Any] = {}
        temp["hAddr"] = self.burst_addresses[0]
        self.burst_addresses = self.burst_addresses[1:]
        if len(self.burst_addresses) == 0:
            self.bursting = False
        temp["hBurst"] = self.burst_type
        temp["hSize"] = self.burst_size
        temp["hExcl"] = HEXCL.NonExcl
        temp["hMaster"] = self.master_id
        temp["hTrans"] = HTRANS.Seq if not NonSeq else HTRANS.NonSeq
        temp["hWstrb"] = 0
        if self.burst_rw == HWRITE.Write:
            temp["hWstrb"] = randint(0, 2**self.bus_byte_width-1) if self.write_strobe else 2**self.bus_byte_width - 1
        temp["hWrite"] = self.burst_rw
        temp["hNonsec"] = self.burst_sec
        self.to_be_delayed = MDATA(0)
        if self.burst_rw == HWRITE.Write:
            self.to_be_delayed = MDATA(randint(0, 2**self.bus_byte_width-1))
        self.command = MCMD(**temp)


    def do_burst(self) -> None:
        size = HSIZE(randint(0, self.max_size))
        addr = randint(0, 2**(self.addr_width - size) - 1) << size
        burst_type = HBURST(randint(1, 7))
        _size = {HBURST.Incr: -1,
                 HBURST.Incr4 : 4, HBURST.Wrap4 : 4,
                 HBURST.Incr8 : 8, HBURST.Wrap8 : 8,
                 HBURST.Incr16 : 16, HBURST.Wrap16 : 16}[burst_type]
        if burst_type == HBURST.Incr:
            length = randint(1, int((1024 - (addr % 1024)) / 2**size))
            for i in range(0, length):
                self.burst_addresses.append(addr + i*2**size)
        elif burst_type in [HBURST.Wrap4, HBURST.Wrap8, HBURST.Wrap16]:
            _mod = (_size * 2**size)
            _base_addr = addr & ~(_mod - 1)
            _offset = addr % _mod
            self.burst_addresses = [_base_addr + (_offset + i * 2**size) % _mod for i in range(_size)]
        else:
            while (addr + _size * 2**size) // 1024 != addr // 1024:
                addr = randint(0, 2**(self.addr_width - size) - 1) << size
            self.burst_addresses = [addr + i * 2**size for i in range(_size)]
        self.bursting = True
        self.burst_type = burst_type
        self.burst_size = size
        rw = HWRITE(randint(0,1))
        self.burst_rw = rw
        self.burst_sec = HNONSEC.Secure
        if self.secure_transfer:
            if self.nonsec_write and rw == HWRITE.Write:
                self.burst_sec = HNONSEC(randint(0,1))
            if self.nonsec_read and rw == HWRITE.Read:
                self.burst_sec = HNONSEC(randint(0,1))
        self.do_bursting(True)


    def do_exclusive_transfer(self) -> None:
        rw = HWRITE.Write
        data: int = 0
        if not self.exclusive_trans:
            rw = HWRITE.Read
            sec = HNONSEC.Secure
            if self.secure_transfer:
                if self.nonsec_read and rw == HWRITE.Read:
                    sec = HNONSEC(randint(0,1))
            size = HSIZE(randint(0, self.max_size))
            addr = randint(0, 2**(self.addr_width - size) - 1) << size
            burst_type = HBURST.Incr
            if self.burst:
                burst_type = HBURST(randint(0, 1))
            self.exclusive_id = (addr, size, burst_type, sec, self.master_id)
            self.exclusive_trans = True
        else:
            data = randint(0, 2**self.exclusive_id[1]-1)
            _offset = self.exclusive_id[0] % self.bus_byte_width
            data <<= 8*_offset

        self.exclusive_transfer_pending = True
        temp: Dict[Any, Any] = {}
        temp["hAddr"] = self.exclusive_id[0]
        temp["hBurst"] = self.exclusive_id[2]
        temp["hSize"] = self.exclusive_id[1]
        temp["hExcl"] = HEXCL.Excl
        temp["hMaster"] = self.exclusive_id[4]
        temp["hTrans"] = HTRANS.NonSeq
        self.to_be_delayed = MDATA(data)
        temp["hWstrb"] = 2**self.bus_byte_width - 1
        temp["hWrite"] = rw
        temp["hNonsec"] = self.exclusive_id[3]
        if rw == HWRITE.Write:
            self.exclusive_trans = False
        self.command = MCMD(**temp)


    def do_something(self) -> None:
        self.valid_cmd = True
        if self.burst and self.bursting:
            self.do_bursting()
            return
        rand = randint(0,99)
        if self.exclusive_transfers:
            if rand == 0:
                self.do_exclusive_transfer()
            elif self.burst and rand in range(1,25):
                self.do_burst()
            else:
                self.do_single()
        elif self.burst and rand in range(0, 24):
            self.do_burst()
        else:
            self.do_single()


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while True:
            await readonly
            self.old_command = MCMD(*self.command)
            if self.is_reset():
                self.do_reset()
            elif not self.valid_cmd or self.is_ready() or self.resp["hresp"] == HRESP.Failed:
                if self.exclusive_transfers:
                    if self.has_exclusive_pending and self.resp["hexokay"] == HEXOKAY.Failed:
                        self.exclusive_trans = False
                    self.has_exclusive_pending = False
                if randint(0,1) == 0:
                    self.do_nothing()
                else:
                    self.do_something()
            self.valid_address_stage = False
            if not self.is_reset() and self.is_ready():
                self.valid_address_stage = True
            self.eval_done.set()
            if self.valid_address_stage:
                self.delayed = self.to_be_delayed
            await clock_edge

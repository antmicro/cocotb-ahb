# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from numpy.random import default_rng # type: ignore

from typing import Any, Tuple, Dict, List, Set, TypeVar
from copy import copy

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly, Event # type: ignore
from cocotb.log import SimLog # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.AHB_common.MemoryInterface import MemoryInterface

T = TypeVar('T')

class SimMem1PSubordinate(SubordinateInterface, MonitorableInterface, SimulationInterface, MemoryInterface):
    def __init__(self, length: int, bus_width: int, *, min_wait_states: int = 5,
                 max_wait_states: int = 25, secure_transfer: bool = False,
                 nonsec_read: bool = False, nonsec_write: bool = False,
                 exclusive_transfers: bool = False, write_strobe: bool = False,
                 burst: bool = False, name: str = ""):

        assert length > 0, "Length must be greater than 0"
        assert length % 1024 == 0, "Address space is not aligned to 1KiB"\
                                   ", but AHB requires such alignment"
        bus_byte_width = bus_width//8
        assert bus_byte_width*8 == bus_width, "bus_width must be multiple of 8"
        assert bus_byte_width in [1, 2, 4, 8, 16, 32, 64, 128], \
                                    "Bus width must be power of 2 from 1 to 128 bytes wide"

        self.length: int = length
        self.bus_width: int = bus_width
        self.bus_byte_width: int = bus_byte_width
        self.mem: Dict[int, int] = {}
        self.resp: SRESP = SRESP(*self._reset_value)
        self.old_resp: SRESP = SRESP(*self._reset_value)
        self.wait_cycles: int  = 0
        self.min_wait_cycles: int = min_wait_states
        self.max_wait_cycles: int = max_wait_states
        self.error: bool = False
        self.eval_done: Event = Event()
        self.log = SimLog(f"cocotb.subordinate.{name}")
        self.random_gen = default_rng()

        self.wdata: int = 0
        self.process_wdata_next_cycle: bool = False
        self.wcommand: ICMD = ICMD()

        self.burst = burst
        if burst:
            self.bursting: bool = False
            self.bursting_address: List[int]
            self.incr_burst: bool
            self.burst_size: HSIZE
            self.burst_type: HBURST
            self.burst_write: HWRITE
            self.burst_prot: HPROT

        self.secure_transfer = secure_transfer
        if secure_transfer:
            self.nonsec_read = nonsec_read
            self.nonsec_write = nonsec_write

        self.exclusive_transfers = exclusive_transfers
        if exclusive_transfers:
            self.watched_addresses: Set[int] = set()
            self.transaction_set: Set[Tuple[int, HSIZE, HPROT, HBURST, int, HNONSEC]] = set() # transactions
            self.failed_transaction_set: Set[Tuple[int, HSIZE, HPROT, HBURST, int, HNONSEC]] = set() # failed transactions
            self.no_collision: bool = True

        self.write_strobe = write_strobe

        self.command: ICMD = ICMD()
        self.input: ICMD = ICMD()
        self.temp: Dict[Any, Any] = {}


    def init_memory(self, init_array: List[int], start_address: int) -> None:
        for i, data in enumerate(init_array):
            self.mem[start_address+i] = data

    def memory_dump(self) -> List[int]:
        ret = []
        for i in range(self.length):
            if i in self.mem:
                ret.append(self.mem[i])
            else:
                ret.append(0)
        return ret


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    def set_ready(self, hReady: HREADY) -> None:
        self.hready = hReady


    def is_ready(self) -> bool:
        return self.hready == HREADY.Working


    def get_rsp(self) -> SRESP:
        return SRESP(*self.resp)

    def _check_fix_incr(self, hAddr: int, hBurst: HBURST, hSize: HSIZE) -> None:
        _first: int = hAddr // 1024
        _last: int
        if hBurst == HBURST.Incr4:
            _last = hAddr + 4 * 2**hSize
        elif hBurst == HBURST.Incr4:
            _last = hAddr + 8 * 2**hSize
        else:
            _last = hAddr + 16 * 2**hSize
        _last //= 1024
        if _first != _last:
            raise Exception("Incrementing burst crosses 1KB boundry")

    def _check_not_bursting(self, hAddr: int, hBurst: HBURST, hSize: HSIZE,
                            hTrans: HTRANS, hWrite: HWRITE, hProt: HPROT) -> None:
        if hBurst in [HBURST.Incr4, HBURST.Incr8, HBURST.Incr16]:
            self._check_fix_incr(hAddr, hBurst, hSize)
        if hBurst != HBURST.Single:
            self.bursting = True
            self.bursting_addresses = []
            self.incr_burst = False
            self.burst_size = hSize
            self.burst_type = hBurst
            self.burst_write = hWrite
            self.burst_prot = hProt
            if hBurst != HBURST.Incr:
                _incr = hBurst in [HBURST.Incr4, HBURST.Incr8, HBURST.Incr16]
                _size = {HBURST.Incr4 : 4, HBURST.Wrap4 : 4,
                         HBURST.Incr8 : 8, HBURST.Wrap8 : 8,
                         HBURST.Incr16 : 16, HBURST.Wrap16 : 16}[hBurst]
                if _incr:
                    self.bursting_addresses = [hAddr + i * 2**hSize for i in range(_size)]
                else:
                    _mod = (_size * 2**hSize)
                    _base_addr = hAddr & ~(_mod - 1)
                    _offset = hAddr % _mod
                    self.bursting_addresses = [_base_addr + (_offset + i * 2**hSize) % _mod for i in range(_size)]
                self.bursting_addresses = self.bursting_addresses[1:]
            else:
                self.incr_burst = True
                self.bursting_addresses = [hAddr + 2**hSize]
        else:
            self.bursting = False


    def burst_check(self, hAddr: int, hBurst: HBURST, hSize: HSIZE,
                    hTrans: HTRANS, hWrite: HWRITE, hProt: HPROT) -> None:
        if not self.bursting and hTrans == HTRANS.NonSeq:
            self._check_not_bursting(hAddr, hBurst, hSize, hTrans, hWrite, hProt)
        elif self.bursting:
            if hTrans in [HTRANS.Idle, HTRANS.NonSeq]:
                if not self.incr_burst:
                    self.log.warning(f"{hTrans.__str__()} in fixed size burst, possible master switch")
                self.bursting = False
                self.burst_check(hAddr, hBurst, hSize, hTrans, hWrite, hProt)
                return
            if len(self.bursting_addresses) != 0 and hAddr != self.bursting_addresses[0]:
                raise Exception(f"Incorrect burst address:{hAddr}")
            if hSize != self.burst_size:
                raise Exception(f"Incorrect burst size, got: {hSize} expected: {self.burst_size}")
            if hBurst != self.burst_type:
                raise Exception(f"Incorrect burst type, got: {hBurst} expected: {self.burst_type}")
            if hWrite != self.burst_write:
                raise Exception(f"Incorrect burst operation, got: {hWrite} expected: {self.burst_write}")
            if hProt != self.burst_prot:
                raise Exception(f"Incorrect burst protection, got: {hProt} expected: {self.burst_prot}")
            if hTrans == HTRANS.Seq:
                if self.incr_burst:
                    self.bursting_addresses[0] = hAddr + 2 ** hSize
                else:
                    self.bursting_addresses = self.bursting_addresses[1:]
                    if len(self.bursting_addresses) == 0:
                        self.bursting = False
        elif hTrans in [HTRANS.Seq, HTRANS.Busy]:
            raise Exception(f"{hTrans.__str__()} in no burst context")


    def exclusive_check(self, hAddr: int, hSize: HSIZE, hProt: HPROT,
                        hBurst: HBURST, hMaster: int, hNonsec: HNONSEC,
                        hExcl: HEXCL, hTrans: HTRANS, hWrite: HWRITE) -> None:

        _trans_id = (hAddr, hSize, hProt, hBurst, hMaster, hNonsec)
        if hExcl == HEXCL.Excl:
            if self.burst and hBurst not in [HBURST.Single, HBURST.Incr]:
                raise Exception("Exclusive transfer must be single beat")
            if hTrans == HTRANS.Busy:
                raise Exception("Exclusive transfer cannot have BUSY command, "
                                "use IDLE as it is not considered part of exclusive transfer")
            if hWrite == HWRITE.Read:
                if _trans_id in self.transaction_set:
                    raise Exception("Exclusive read after exclusive read is not permited."
                                    "Exclusive read may be followed only by exclusive write.")


    def put_cmd(self, cmd: ICMD) -> None:
        temp: Dict[Any, Any] = {}
        temp["hAddr"] = cmd.hAddr
        temp["hSize"] = cmd.hSize
        temp["hTrans"] = cmd.hTrans
        temp["hWrite"] = cmd.hWrite
        temp["hSel"] = cmd.hSel
        temp["hProt"] = cmd.hProt

        if self.burst:
            temp["hBurst"] = cmd.hBurst
        if self.secure_transfer:
            temp["hNonsec"] = cmd.hNonsec
        if self.exclusive_transfers:
            temp["hExcl"] = cmd.hExcl
            temp["hMaster"] = cmd.hMaster
        if self.write_strobe:
            temp["hWstrb"] = cmd.hWstrb

        self.input = ICMD(**temp)

        if not self.is_ready():
            return
        temp['hAddr'] %= self.length

        self.command = ICMD(*self.input)

        if cmd.hSel == HSEL.Sel:
            if cmd.hAddr % 2**cmd.hSize != 0:
                raise Exception("Unaligned address is not permited")
            if self.bus_byte_width < 2**cmd.hSize:
                raise Exception(f"HSIZE:{2**cmd.hSize} greater then bus width: {self.bus_byte_width}")
            if self.burst:
                self.burst_check(self.command.hAddr, cmd.hBurst, cmd.hSize, cmd.hTrans, cmd.hWrite, cmd.hProt)
            if self.exclusive_transfers:
                self.exclusive_check(self.command.hAddr, cmd.hSize, cmd.hProt,
                                     cmd.hBurst if self.burst else HBURST.Single, cmd.hMaster,
                                     cmd.hNonsec, cmd.hExcl, cmd.hTrans, cmd.hWrite)


    def put_data(self, data:IDATA) -> None:
        self.wdata = data.hWData


    async def monitor_get_status(self) -> HMONITOR:
        monit = HMONITOR(False)
        await self.eval_done.wait()
        self.eval_done.clear()
        for signal, value in zip(self.input._fields, self.input):
            monit.command[signal] = value

        for signal, value in zip(self.old_resp._fields, self.old_resp):
            monit.resp[signal] = value

        monit.wdata = self.wdata
        monit.ready = self.is_ready()
        return monit


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        self.error = False
        self.mem = {}
        self.wait_cycles = 0
        if self.exclusive_transfers:
            self.watched_addresses.clear()
            self.transaction_set.clear()
            self.no_collision = True
        self.resp = SRESP(*self._reset_value)


    def process_secure_transfer(self) -> None:
        if self.secure_transfer:
            if self.command.hTrans not in [HTRANS.Idle, HTRANS.Busy] and self.command.hNonsec == HNONSEC.NonSecure:
                if self.command.hWrite == HWRITE.Read and not self.nonsec_read:
                    self.error = True
                elif self.command.hWrite == HWRITE.Write and not self.nonsec_write:
                    self.error = True


    def process_exclusive_transfer(self) -> None:
        if self.exclusive_transfers:
            self.no_colision = True
            if self.command.hExcl == HEXCL.Excl:
                _trans_id = (self.command.hAddr, self.command.hSize, self.command.hProt,
                             self.command.hBurst if self.burst else HBURST.Single,
                             self.command.hMaster, self.command.hNonsec)
                if self.command.hWrite == HWRITE.Read:
                    self.transaction_set.add(_trans_id)
                    _addr = self.command.hAddr
                    for addr in range(_addr, _addr + 2**self.command.hSize):
                        self.watched_addresses.add(addr)
                    self.temp["hExOkay"] = HEXOKAY.Successful
                if self.command.hWrite == HWRITE.Write:
                    if _trans_id not in self.transaction_set or \
                       _trans_id in self.failed_transaction_set:
                        self.failed_transaction_set -= set([_trans_id])
                        self.no_collision = False
                    else:
                        self.temp["hExOkay"] = HEXOKAY.Successful


    def exclusive_trans_colision_check(self, _addr: int) -> bool:
        return self.no_collision


    def exclusive_trans_colision_update(self, _addr: int) -> None:
        rm = set()
        self.watched_addresses.remove(_addr)
        for _trans_id in self.transaction_set:
            (addr, size, *rest) = _trans_id
            if _addr in range(addr, addr + 2**size):
                self.failed_transaction_set.add(_trans_id)
                rm.add(_trans_id)
        for _trans_id in rm:
            self.transaction_set.remove(_trans_id)


    def process_write(self) -> None:
        self.process_wdata_next_cycle = False
        _offset = self.wcommand.hAddr % self.bus_byte_width
        _modify = True
        for i in range(2**self.wcommand.hSize):
            _addr = i + self.wcommand.hAddr
            if self.exclusive_transfers:
                _modify = self.exclusive_trans_colision_check(_addr)
                if _addr in self.watched_addresses:
                    self.exclusive_trans_colision_update(_addr)
            if _modify:
                _mask = 2**8 -1
                if self.write_strobe:
                    _mask *= int(bool(self.wcommand.hWstrb & (1 << i +_offset)))
                if _addr not in self.mem or _mask != 0:
                    self.mem[_addr] = ((self.wdata >> 8 * (i + _offset)) & _mask)


    def process(self) -> None:
        self.error = False
        avr = (self.max_wait_cycles + self.min_wait_cycles) / 2
        self.wait_cycles = min(self.random_gen.poisson(avr), self.max_wait_cycles)
        self.temp["hRData"] = 0
        self.temp["hResp"] = HRESP.Successful
        self.temp["hReadyOut"] = HREADYOUT.NotReady
        if self.exclusive_transfers:
            self.temp["hExOkay"] = HEXOKAY.Failed
        self.process_secure_transfer()
        if self.error:
            return
        self.process_exclusive_transfer()
        if self.command.hTrans in [HTRANS.Idle, HTRANS.Busy]:
            self.wait_cycles = 0
        elif self.burst and self.command.hTrans == HTRANS.Seq:
            self.wait_cycles = min(self.random_gen.poisson(self.min_wait_cycles),
                                   self.max_wait_cycles)


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while True:
            self.temp["hRData"] = 0
            await readonly
            self.old_resp = copy(self.resp)
            if self.is_reset():
                self.do_reset()
            elif self.is_ready() and self.command.hSel == HSEL.Sel:
                if self.process_wdata_next_cycle:
                    self.process_write()

                self.process()

                if self.error:
                    self.wait_cycles = 1
                    self.temp["hRData"] = 0
                    self.temp["hResp"] = HRESP.Failed

            if not self.is_reset() and self.wait_cycles == 0 and not self.error and \
                self.command.hTrans not in [HTRANS.Idle, HTRANS.Busy]: # update state and prepare response
                    if self.command.hWrite == HWRITE.Read:
                        _offset = self.command.hAddr % self.bus_byte_width
                        for i in range(2**self.command.hSize):
                            _addr = i + self.command.hAddr
                            _data = self.mem[_addr] if _addr in self.mem else 0
                            self.temp["hRData"] |= _data << 8*(i + _offset)
                    else:
                        self.process_wdata_next_cycle = True
                        self.wcommand = self.command

            if self.wait_cycles == 0: # mark response as avlid
                self.temp["hReadyOut"] = HREADYOUT.Ready

            self.resp = SRESP(**self.temp)
            self.wait_cycles -= 1
            self.eval_done.set()
            await clock_edge

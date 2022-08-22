# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import List, Dict, Any, TypeVar, Tuple

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly, ReadWrite, Event # type: ignore

from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface

T = TypeVar('T')

class SimSimpleManager(SimulationInterface, ManagerInterface, MonitorableInterface):
    def __init__(self, bus_width: int) -> None:
        self.commands: List[Tuple[MCMD, MDATA]] = []
        self.responses: List[IRESP] = []
        self.ready: HREADY
        self.eval_done: Event = Event()
        self.send_command: MCMD = MCMD(*self._reset_value)
        self.resp: Dict[Any, Any] = {}
        self.new_cmd: bool = False
        self.valid_cmd: bool = False
        self.bus_width = bus_width
        self.bus_byte_width: int = bus_width//8
        self.cnt: int = 0
        self.to_be_delayed: MDATA = MDATA()
        self.delayed: MDATA = MDATA()


    def set_ready(self, hReady: HREADY) -> None:
       self.ready = hReady


    def is_ready(self) -> bool:
        return self.ready == HREADY.Working


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
        for signal, value in zip(self.send_command._fields, self.send_command):
            monit.command[signal] = value

        for signal, value in self.resp.items():
            monit.resp[signal] = value

        monit.wdata = self.delayed.hWData
        monit.ready = self.is_ready()
        return monit

    def put_rsp(self, rsp: IRESP) -> None:
        self.resp["hRData"] = rsp.hRData
        self.resp["hResp"] = rsp.hResp
        self.resp["hExOkay"] = rsp.hExOkay


    def get_cmd(self) -> MCMD:
        if self.new_cmd:
            self.new_cmd = False
        if self.cnt < len(self.commands):
            self.to_be_delayed = self.commands[self.cnt][1]
            self.send_command = self.commands[self.cnt][0]
            return self.commands[self.cnt][0]
        self.to_be_delayed = MDATA(0)
        return MCMD()


    def get_data(self) -> MDATA:
        return self.delayed


    async def transfer_done(self) -> None:
        ce = RisingEdge(self.clock)
        while True:
            if len(self.responses) == len(self.commands):
                return
            await ce


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        self.cnt = 0


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while True:
            await readonly
            if self.is_reset():
                self.do_reset()
            elif self.is_ready():
                if self.cnt > 0:
                    self.responses.append(IRESP(**self.resp))
                if not self.new_cmd:
                    self.cnt += 1

            self.valid_address_stage = False
            if not self.is_reset() and self.is_ready():
                self.valid_address_stage = True
            self.eval_done.set()
            if self.valid_address_stage:
                self.delayed = self.to_be_delayed

            await clock_edge


    def read(self, address: int, length: int) -> None:
        cmds = []
        end_address = address + length
        for i in range((self.bus_byte_width).bit_length() - 1):
            if (address & 2**i) and address + 2**i <= end_address:
                _offset = address % (self.bus_byte_width)
                cmds.append((
                        MCMD(hAddr=address, hSize=HSIZE(i), hTrans=HTRANS.NonSeq, hWrite=HWRITE.Read),
                        MDATA(0)
                    )
                )
                address += 2**i
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        while address+self.bus_byte_width <= end_address:
            _size = (self.bus_byte_width).bit_length() - 1
            cmds.append((
                    MCMD(hAddr=address, hSize=HSIZE(i), hTrans=HTRANS.NonSeq, hWrite=HWRITE.Read),
                    MDATA(0)
                )
            )
            address += (self.bus_byte_width)
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        for i in range((self.bus_byte_width).bit_length()-1, -1, -1):
            if address + 2**i <= end_address:
                _offset = address % (self.bus_byte_width)
                cmds.append((
                        MCMD(hAddr=address, hSize=HSIZE(i), hTrans=HTRANS.NonSeq, hWrite=HWRITE.Read),
                        MDATA(0)
                    )
                )
                address += 2**i
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        assert False


    def write(self, address: int, length: int,
              value: List[int], byte_mask: List[bool]) -> None:
        assert length == len(value) and length == len(byte_mask)
        cmds = []
        end_address = address + length
        for i in range((self.bus_byte_width).bit_length() - 1):
            if (address & 2**i) and len(value) != 0:
                _mask = 0
                _value = 0
                _offset = address % (self.bus_byte_width)
                for j in range(0, 2**i):
                    if len(value) != 0:
                        _mask |= byte_mask[0] << _offset + j
                        _value |= value[0] << ((_offset + j) * 8)
                        byte_mask = byte_mask[1:]
                        value = value[1:]
                cmds.append((
                    MCMD(hAddr=address, hSize=HSIZE(i), hTrans=HTRANS.NonSeq,
                         hWrite=HWRITE.Write, hWstrb=_mask),
                    MDATA(_value)
                ))
                address += 2**i
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        while len(value) >= (self.bus_byte_width):
            _mask = 0
            _value = 0
            _size = (self.bus_byte_width).bit_length() - 1
            for j in range(0, (self.bus_byte_width)):
                _mask |= byte_mask[0] << j
                _value |= value[0] << (j * 8)
                byte_mask = byte_mask[1:]
                value = value[1:]
            cmds.append((
                MCMD(hAddr=address, hSize=HSIZE(_size), hTrans=HTRANS.NonSeq,
                     hWrite=HWRITE.Write, hWstrb=_mask),
                MDATA(_value)
            ))
            address += (self.bus_byte_width)
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        for i in range((self.bus_byte_width).bit_length()-1, -1 , -1):
            if len(value) & 2**i:
                _mask = 0
                _value = 0
                _offset = address % (self.bus_byte_width)
                for j in range(0, 2**i):
                    _mask |= byte_mask[0] << _offset + j
                    _value |= value[0] << ((_offset + j) * 8)
                    byte_mask = byte_mask[1:]
                    value = value[1:]
                cmds.append((
                    MCMD(hAddr=address, hSize=HSIZE(i), hTrans=HTRANS.NonSeq,
                         hWrite=HWRITE.Write, hWstrb=_mask),
                    MDATA(_value)
                ))
                address += 2**i
        if address >= end_address:
            self.responses = []
            self.cnt = 0
            self.commands = cmds
            self.new_cmd = True
            assert len(cmds)>0
            return
        assert False


    def get_rsp_success(self) -> List[bool]:
        ret: List[bool] = []
        for resp in self.responses:
            ret.append(bool(resp.hResp))
        return ret


    def get_rsp(self, base_address: int, bus_byte_width: int) -> List[int]:
        ret: List[int] = []
        if self.commands[0][0].hWrite == HWRITE.Read:
            return ret
        addr = base_address
        for command, resp in zip(self.commands, self.responses):
            _offset = addr % bus_byte_width
            for j in range(2**command[0].hSize):
                ret.append((resp.hRData >> ((_offset + j)*8)) & 0xFF)
            addr += 2**command[0].hSize
        return ret

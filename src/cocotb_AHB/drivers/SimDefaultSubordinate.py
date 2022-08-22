# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Tuple, Dict, Any, List, TypeVar

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly, Event  # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface

T = TypeVar('T')

class SimDefaultSubordinate(SubordinateInterface, MonitorableInterface, SimulationInterface):
    def __init__(self, length: int, bus_width: int):

        assert length > 0, "Length must be greater than 0"
        assert length % 1024 == 0, "Address space is not aligned to 1KiB"\
                                   ", but AHB requires such alignment"

        bus_byte_width = bus_width//8
        assert bus_byte_width*8 == bus_width, "bus_width must be multiple of 8"
        assert bus_byte_width in [1, 2, 4, 8, 16, 32, 64, 128], \
                                    "Bus byte width must be power of 2 from 1 to 128 bytes wide"
        self.length: int = length
        self.bus_width: int = bus_width
        self.bus_byte_width: int = bus_byte_width
        self.temp: Dict[Any, Any] = {}
        self.resp: SRESP = SRESP(*self._reset_value)
        self.old_resp: SRESP = SRESP(*self._reset_value)
        self.wait_cycles: int  = 0
        self.error: bool = False
        self.input: ICMD = ICMD()
        self.command: ICMD = ICMD()
        self.eval_done: Event = Event()
        self.wdata: int = 0

        self.bursting: bool = False
        self.bursting_address: List[int]
        self.incr_burst_size : HSIZE


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


    def put_cmd(self, cmd: ICMD) -> None:
        temp: Dict[Any, Any] = {}
        temp['hAddr']  = cmd.hAddr
        temp['hSize']  = cmd.hSize
        temp['hTrans'] = cmd.hTrans
        temp['hWrite'] = cmd.hWrite
        temp['hSel']   = cmd.hSel
        self.input = ICMD(**temp)
        if not self.is_ready():
            return
        temp['hAddr']  %= self.length
        self.command = ICMD(*self.input)
        if cmd.hSel == HSEL.Sel:
            if cmd.hAddr % 2**cmd.hSize != 0:
                raise Exception("Unaligned address is not permited")
            if self.bus_byte_width < 2**cmd.hSize:
                raise Exception(f"HSIZE:{2**cmd.hSize} greater then bus width: {self.bus_byte_width}")


    def put_data(self, data: IDATA) -> None:
        self.wdata = data.hWData


    async def monitor_get_status(self) ->  HMONITOR:
        await self.eval_done.wait()
        self.eval_done.clear()
        monit = HMONITOR(False)
        for signal, value in zip(self.input._fields, self.input):
            monit.command[signal] = value

        for signal, value in zip(self.old_resp._fields, self.old_resp):
            monit.resp[signal] = value

        monit.wdata= self.wdata
        monit.ready = self.is_ready()
        return monit


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        self.error = False
        self.wait_cycles = 0
        self.resp = SRESP(*self._reset_value)


    def process(self) -> None:
        self.error = False
        self.temp["hRData"] = 0
        self.temp["hResp"] = HRESP.Successful
        if self.command.hTrans in [HTRANS.Idle, HTRANS.Busy]:
            self.wait_cycles = 0
        else:
            self.temp["hResp"] = HRESP.Failed
            self.wait_cycles = 1


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        self.temp = {}
        while True:
            await readonly
            self.old_resp = SRESP(*self.resp)
            if self.is_reset():
                self.do_reset()
            elif self.is_ready() and self.command.hSel == HSEL.Sel:
                self.process()

            if self.wait_cycles == 0: # mark response as avlid
                self.temp['hReadyOut'] = HREADYOUT.Ready
            else:
                self.temp['hReadyOut'] = HREADYOUT.NotReady

            self.resp = SRESP(**self.temp)
            self.wait_cycles -= 1
            self.eval_done.set()
            await clock_edge

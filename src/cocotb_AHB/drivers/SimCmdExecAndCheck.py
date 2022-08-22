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

class SimCmdExecAndCheck(SimulationInterface, ManagerInterface, MonitorableInterface):
    def __init__(self, commands: List[Tuple[MCMD, MDATA]], responds: List[IRESP]) -> None:
        self.commands = commands
        self.responds = responds
        self.ready: HREADY
        self.cnt: int = 0
        self.r_cnt: int = 0
        self.eval_done: Event = Event()
        self.send_command: MCMD = MCMD(*self._reset_value)
        self.resp: Dict[Any, Any] = {}
        self.valid_cmd: bool = False
        self.bus_width: int = 32
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
        if self.cnt < len(self.commands):
            self.to_be_delayed = self.commands[self.cnt][1]
            self.send_command = self.commands[self.cnt][0]
            return self.commands[self.cnt][0]
        self.to_be_delayed = MDATA(0)
        return MCMD()


    def get_data(self) -> MDATA:
        return self.delayed


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        self.cnt = 0
        self.r_cnt = 0


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while self.r_cnt != len(self.responds):
            await readonly
            if self.is_reset():
                self.do_reset()
            elif self.is_ready() or self.resp["hResp"] == HRESP.Failed:
                if self.cnt > 0 and self.is_ready():
                    try:
                        assert self.responds[self.r_cnt] == IRESP(**self.resp), f'{self.r_cnt} {self.responds[self.r_cnt]} , {IRESP(**self.resp)}'
                    except Exception:
                        await clock_edge
                        raise
                    self.r_cnt += 1
                self.cnt += 1
            self.eval_done.set()
            await clock_edge
            self.delayed = self.to_be_delayed

# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Type, Dict, Any, TypeVar

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly # type: ignore
from cocotb.log import SimLog # type: ignore

from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface
from cocotb_AHB.AHB_common.MonitorInterface import SimMonitorInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface

T = TypeVar('T')

class AHBSignalMonitor(SimMonitorInterface):
    def __init__(self, name: str =""):
        self.log: SimLog = SimLog(f"cocotb.{name}")


    def register_device(self: T, device: MonitorableInterface) -> T:
        self.device = device
        return self


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def parse_cmd(self, cmd: Dict[Any,Any]) -> str:
        _ret: str = "Command: "
        for key, val in cmd.items():
            if type(val) is not int:
                _ret += key.capitalize() + ": " + str(val) + "; "
            else:
                _ret += key.capitalize() + ": " + str(hex(val)) + "; "
        return _ret


    def parse_resp(self, rsp: Dict[Any,Any]) -> str:
        _ret: str = "Response: "
        for key, val in rsp.items():
            if type(val) is not int:
                _ret += key.capitalize() + ": " + str(val) + "; "
            else:
                _ret += key.capitalize() + ": " + str(hex(val)) + "; "
        return _ret


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while True:
            await readonly
            status = await self.device.monitor_get_status()
            self.log.info(f"Bus ready signal: {status.ready}\n"
                          f"Bus reset signal: {self.is_reset()}\n"
                          + self.parse_resp(status.resp) + "\n"
                          + self.parse_cmd(status.command) + "\n"
                          + f"Hwdata: {status.wdata}")
            await clock_edge

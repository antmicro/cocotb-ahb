# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Type, Dict, Any, TypeVar

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly # type: ignore
from cocotb.log import SimLog # type: ignore

from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface
from cocotb_AHB.AHB_common.MonitorInterface import SimMonitorInterface, Packet

T = TypeVar('T')

class AHBPacketMonitor(SimMonitorInterface):
    def __init__(self, name: str ="") -> None:
        self.log: SimLog = SimLog(f"cocotb.{name}")
        self.packet_in_address_phase: Packet = Packet()
        self.packet_in_data_phase: Packet = Packet()


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


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        while True:
            await readonly
            status = await self.device.monitor_get_status()
            if not self.is_reset():
                if status.ready:
                    self.packet_in_address_phase.cmd(status.command)
                    self.packet_in_data_phase.rsp(status.resp)
                    self.packet_in_data_phase.wdata(status.wdata)
                    self.log.info(self.packet_in_data_phase)
                    self.packet_in_data_phase = self.packet_in_address_phase
                    self.packet_in_address_phase = Packet()
                self.packet_in_address_phase.age()
                self.packet_in_data_phase.age()
            await clock_edge

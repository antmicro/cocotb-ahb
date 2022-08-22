# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar, Optional
from abc import ABC

from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadWrite # type: ignore

from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface

T = TypeVar('T')
S = TypeVar('S', bound='InterconnectWrapper')

class InterconnectInterface(ABC):
    def register_manager(self: T, manager: ManagerInterface,
                         interconnect_id: Optional[int] = None,
                         name: Optional[str] = None) -> T:
        raise Exception("Unimplemented")
    def register_subordinate(self: T, subordinate: SubordinateInterface,
                             name: Optional[str] = None) -> T:
        raise Exception("Unimplemented")
    async def process(self: T) -> None:
        raise Exception("Unimplemented")


class InterconnectWrapper(SimulationInterface):
    def __init__(self) -> None:
        self.interconnect: Optional[InterconnectInterface] = None


    def register_interconnect(self: S, interconnect: InterconnectInterface) -> S:
        self.interconnect = interconnect
        return self


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    async def start(self) -> None:
        assert self.interconnect is not None, "Interconnect not defined"
        clock_edge = RisingEdge(self.clock)
        readwrite = ReadWrite()
        while True:
            await readwrite
            await self.interconnect.process()
            await clock_edge

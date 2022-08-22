# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Tuple, TypeVar

from abc import ABC
from cocotb.handle import SimHandleBase # type: ignore

T = TypeVar('T')

class SimulationInterface(ABC):
    def register_clock(self: T, clock: SimHandleBase) -> T:
        raise Exception("Unimplemented")
    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        raise Exception("Unimplemented")
    async def start(self) -> None:
        raise Exception("Unimplemented")

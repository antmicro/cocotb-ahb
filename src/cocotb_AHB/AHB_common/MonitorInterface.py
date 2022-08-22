# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Dict, Any, TypeVar

from abc import ABC
from cocotb.handle import SimHandleBase # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface

T = TypeVar('T')

class MonitorInterface(ABC):
    def register_device(self: T, device: MonitorableInterface) -> T:
        raise Exception("Unimplemented")


class SimMonitorInterface(MonitorInterface, SimulationInterface):
    pass


class Packet:
    def __init__(self) -> None:
        self.part_of_burst: bool = False
        self.command: Dict[Any, Any] = {}
        self._wdata: int = 0
        self.resp: Dict[Any, Any] = {}
        self._age: int = 0


    def age(self) -> None:
        self._age += 1


    def cmd(self, command: Dict[Any, Any]) -> None:
        if "hburst" in command.keys() and \
            command["hburst"] != HBURST.Single:
            self.part_of_burst = True
        self.command = command


    def wdata(self, wdata: int) -> None:
        self._wdata = wdata


    def rsp(self, resp: Dict[Any, Any]) -> None:
        self.resp = resp


    def __str__(self) -> str:
        _cmd = "Command:\n\t"
        if self.part_of_burst:
            _cmd = "Part of Burst;\n\t"
        for key, value in self.command.items():
            _cmd += " " + key.capitalize() + ": "
            if type(value) is not int:
                _cmd += str(value) + ";"
            else:
                _cmd += str(hex(value)) + ";"
        _cmd += f"WData: {self._wdata}"
        _resp = "Response:\n\t"
        for key, value in self.resp.items():
            _resp += " " + key.capitalize() + ": "
            if type(value) is not int:
                _resp += str(value) + ";"
            else:
                _resp += str(hex(value)) + ";"
        if len(self.command) == 0:
            return "Response to reset command;\n" + _resp
        return _cmd + "\n" + _resp + "\n" + f"Took {self._age} cycles"

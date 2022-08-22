# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Tuple, List
from math import log2

from cocotb.handle import SimHandleBase # type: ignore
from cocotb_bus.bus import Bus # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.MonitorableInterface import MonitorableInterface


class DUTManager(ManagerInterface, MonitorableInterface):
    def __init__(self, entity: SimHandleBase, bus_width: int, name: str ="", **kwargs: Any):
        self.bus_width = bus_width
        self.bus = Bus(entity, name, self._signals, self._optional_signals, **kwargs)
        for name in self._optional_signals:
            setattr(self, "has_" + name, True)
            if getattr(self.bus, name) is None:
                setattr(self, "has_" + name, False)
                setattr(self, "default_" + name, self._default_opt[name])


    def set_ready(self, hReady: HREADY) -> None:
        self.bus.hready.value = hReady


    def is_ready(self) -> bool:
        return HREADY(self.bus.hready.value) == HREADY.Working


    def put_rsp(self, resp: IRESP) -> None:
        self.bus.hresp.value = resp.hResp
        self.bus.hrdata.value = resp.hRData
        if getattr(self, "has_hexokay"):
            self.bus.hexokay = resp.hExOkay
        else:
            self.default_exokay = resp.hExOkay


    def get_cmd(self) -> MCMD:
        _temp = []
        for i, out_signal in enumerate(self._command_signals):
            if out_signal in self._optional_signals and \
               getattr(self, "has_" + out_signal) or \
               out_signal not in self._optional_signals:
                _temp.append(getattr(self.bus, out_signal).value)
            else:
                _temp.append(getattr(self, "default_" + out_signal))
        return MCMD(int(_temp[0]), HBURST(_temp[1]), HMASTLOCK(_temp[2]),
                    HPROT(_temp[3]), HSIZE(_temp[4]), HNONSEC(_temp[5]),
                    HEXCL(_temp[6]), int(_temp[7]), HTRANS(_temp[8]),
                    int(_temp[10]), HWRITE(_temp[11]))


    def get_data(self) -> MDATA:
        return MDATA(int(self.bus.hwdata.value))


    async def monitor_get_status(self) -> HMONITOR:
        monit = HMONITOR()
        monit.ready = self.is_ready()
        for signal in self._command_signals:
            if signal in self._signals or \
               getattr(self, "has_" + signal):
                monit.command[signal] = hex(getattr(self.bus, signal).value)

        for signal in self._resp_signals:
            if signal in self._signals or \
               getattr(self, "has_" + signal):
                monit.resp[signal] = hex(getattr(self.bus, signal).value)

        monit.wdata = int(self.bus.hwdata.value)
        return monit

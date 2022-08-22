# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Tuple

from cocotb.handle import SimHandleBase # type: ignore
from cocotb_bus.bus import Bus # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface


class DUTSubordinate(SubordinateInterface):
    def __init__(self, entity: SimHandleBase, bus_width: int, name: str = "", **kwargs: Any):
        self.bus_width = bus_width
        self.bus = Bus(entity, name, self._signals, self._optional_signals, **kwargs)
        for name in self._optional_signals:
            setattr(self, "has_" + name, True)
            if not hasattr(self.bus, name):
                setattr(self, "has_" + name, False)


    def set_ready(self, hReady: HREADY) -> None:
        self.bus.hready.value = hReady


    def is_ready(self) -> bool:
        return HREADY(self.bus.hready.value) == HREADY.Working


    def get_rsp(self) -> SRESP:
        exokay = HEXOKAY.Failed
        if getattr(self, "has_hexokay"):
            exokay = HEXOKAY(self.bus.hexokay.value)
        return SRESP(hRData=int(self.bus.hrdata.value),
                     hReadyOut=HREADYOUT(self.bus.hreadyout.value),
                     hResp=HRESP(self.bus.hresp.value),
                     hExOkay=exokay)


    def put_cmd(self, cmd: ICMD) -> None:
        self.bus.haddr.value  = cmd.hAddr
        self.bus.hsize.value  = cmd.hSize
        self.bus.htrans.value = cmd.hTrans
        self.bus.hwrite.value = cmd.hWrite
        self.bus.hsel.value   = cmd.hSel
        if getattr(self, "has_hburst"):
            self.bus.hburst.value = cmd.hBurst
        if getattr(self, "has_hmastlock"):
            self.bus.hmastlock.value = cmd.hMastlock
        if getattr(self, "has_hprot"):
            self.bus.hprot.value = hProt_to_int(cmd.hProt)
        if getattr(self, "has_hnonsec"):
            self.bus.hnonsec.value = cmd.hNonsec
        if getattr(self, "has_hexcl"):
            self.bus.hexcl.value = cmd.hExcl
        if getattr(self, "has_hmaster"):
            self.bus.hmaster.value = cmd.hMaster
        if getattr(self, "has_hwstrb"):
            self.bus.hwstrb.value = cmd.hWstrb


    def put_data(self, data: IDATA) -> None:
        self.bus.hwdata.value = data.hWData


    async def monitor_get_status(self) ->  HMONITOR:
        monit = HMONITOR(False)
        for signal in self._command_signals:
            if signal in self._signals or \
               getattr(self, "has_" + signal):
                monit.command[signal] = getattr(self.bus, signal).value

        for signal in self._resp_signals:
            if signal in self._signals or \
               getattr(self, "has_" + signal):
                monit.command[signal] = getattr(self.bus, signal).value

        monit.wdata = int(self.bus.hwdata.value)
        monit.ready = self.is_ready()
        return monit



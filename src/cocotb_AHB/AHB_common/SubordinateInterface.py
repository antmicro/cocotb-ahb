# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Tuple

from abc import ABC
from cocotb_AHB.AHB_common.AHB_types import *

class SubordinateInterface(ABC):
    _signals = ["haddr", "hsize", "htrans", "hwdata",
                "hwrite", "hrdata", "hready", "hreadyout",
                "hresp", "hsel"]
    _optional_signals = ["hburst", "hmastlock", "hprot", "hnonsec",
                         "hexcl", "hmaster", "hwstrb", "hexokay"]
    _command_signals = ["haddr", "hbrust", "hmastlock", "hprot",
                        "hsize", "hnonsec", "hexcl", "hmaster",
                        "htrans", "hwdata", "hwstrb", "hwrite",
                        "hsel"]
    _resp_signals = ["hrdata", "hreadyout", "hresp", "hexokay"]
    _reset_value = SRESP()
    _bus_width: int = -1

    @property
    def bus_width(self) -> int:
        if self._bus_width == -1:
            raise Exception("Bus Width must be defined")
        return self._bus_width


    @bus_width.setter
    def bus_width(self, value: int) -> None:
        self._bus_width = value


    def set_ready(self, hReady: HREADY) -> None:
        raise Exception("Unimplemented")
    def is_ready(self) -> bool:
        raise Exception("Unimplemented")
    def get_rsp(self) -> SRESP:
        raise Exception("Unimplemented")
    def put_cmd(self, cmd: ICMD) -> None:
        raise Exception("Unimplemented")
    def put_data(self, data: IDATA) -> None:
        raise Exception("Unimplemented")

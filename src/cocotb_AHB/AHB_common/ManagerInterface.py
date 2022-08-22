# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Tuple, Dict, Any

from abc import ABC
from cocotb_AHB.AHB_common.AHB_types import *

class ManagerInterface(ABC):
    _signals = ["haddr", "hsize", "htrans", "hwdata",
                "hwrite", "hrdata", "hready", "hresp"]
    _optional_signals = ["hburst", "hmastlock","hprot", "hnonsec",
                         "hexcl", "hmaster", "hwstrb", "hexokay"]
    _command_signals = ["haddr", "hburst", "hmastlock", "hprot",
                        "hsize", "hnonsec", "hexcl", "hmaster",
                        "htrans", "hwdata", "hwstrb", "hwrite"]
    _resp_signals = ["hrdata", "hresp", "hexokay"]
    _reset_value = MCMD()
    _bus_width: int = -1

    @property
    def bus_width(self) -> int:
        if self._bus_width == -1:
            raise Exception("Bus Width must be defined")
        return self._bus_width


    @bus_width.setter
    def bus_width(self, value: int) -> None:
        self._bus_width = value


    @property
    def _default_opt(self) -> Dict[Any, Any]:
        return {"hburst": HBURST.Incr,
                "hnonsec": HNONSEC.Secure,
                "hexcl": HEXCL.NonExcl,
                "hmaster": 0,
                "hwstrb": (2**self.bus_width) - 1,
                "hexokay": HEXOKAY.Failed}

    def set_ready(self, hReady: HREADY) -> None:
        raise Exception("Unimplemented")
    def is_ready(self) -> bool:
        raise Exception("Unimplemented")
    def put_rsp(self, resp: IRESP) -> None:
        raise Exception("Unimplemented")
    def get_cmd(self) -> MCMD:
        raise Exception("Unimplemented")
    def get_data(self) -> MDATA:
        raise Exception("Unimplemented")

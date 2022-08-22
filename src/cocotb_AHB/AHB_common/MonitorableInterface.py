# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import Type

from abc import ABC
from cocotb_AHB.AHB_common.AHB_types import HMONITOR

class MonitorableInterface(ABC):
    async def monitor_get_status(self) ->  HMONITOR:
        raise Exception("Unimplemented")

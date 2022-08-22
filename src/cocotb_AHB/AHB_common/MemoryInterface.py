# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from abc import ABC
from typing import List

class MemoryInterface(ABC):
    def init_memory(self, init_array: List[int], start_address: int) -> None:
        raise Exception("Unimplemented")

    def memory_dump(self) -> List[int]:
        raise Exception("Unimplemented")

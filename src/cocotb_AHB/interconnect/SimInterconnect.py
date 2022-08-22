# Copyright 2022 Antmicro
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from random import randint

from typing import Any, Tuple, Dict, List, Set, Optional, TypeVar, Type
from copy import copy
from math import log2

import cocotb # type: ignore
from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import ReadOnly, ReadWrite # type: ignore
from cocotb.log import SimLog # type: ignore
from cocotb_bus.bus import Bus # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.InterconnectInterface import InterconnectInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.drivers.SimDefaultSubordinate import SimDefaultSubordinate

T = TypeVar('T', bound='SimInterconnect')

class SimInterconnect(InterconnectInterface, SimulationInterface):
    class Arbiter():
        def __init__(self) -> None:
            self.command_queue: List[Tuple[ICMD, ManagerInterface]] = []
            self.interface: Optional[ManagerInterface] = None


        def queue_cmd(self, cmd: ICMD, manager: ManagerInterface) -> None:
            self.command_queue.append((cmd, manager))


        def get_cmd(self) -> Tuple[ICMD, Optional[ManagerInterface]]:
            if len(self.command_queue):
                cmd, manager = self.command_queue[0]
                self.command_queue = self.command_queue[1:]
                self.interface = manager
                return cmd, manager
            else:
                self.interface = None
                return ICMD(0, HBURST.Incr, HMASTLOCK.UnLocked, HPROT(),
                            HSIZE.Byte, HNONSEC.Secure, HEXCL.NonExcl, 0,
                            HTRANS.Idle, 0, HWRITE.Read, HSEL.NotSel), None


        def get_data(self) -> IDATA:
            if self.interface is None:
                return IDATA(0)
            return IDATA(self.interface.get_data().hWData)

    def __init__(self) -> None:
        self.managers_ready: Set[ManagerInterface] = set()
        self.managers_waiting: Set[ManagerInterface] = set()
        self.manager_cnt: int = 0
        self.manager_used_id: Set[int] = set()
        self.manager_to_id: Dict[ManagerInterface, int] = {}
        self.id_to_manager: Dict[int, ManagerInterface] = {}
        self.manager_address_map: Dict[ManagerInterface, List[Tuple[int, int]]] = {}
        self.manager_id_subordinate_map: Dict[Tuple[ManagerInterface, int], SubordinateInterface] = {}
        self.manager_default_subordinate: Dict[ManagerInterface, SimDefaultSubordinate] = {}

        self.subordinates_ready: Set[SubordinateInterface] = set()
        self.subordinates_waiting: Set[SubordinateInterface] = set()
        self.subordinates_manager_resp: Dict[SubordinateInterface,
                                             Optional[ManagerInterface]] = {}

        self.arbiters: Dict[SubordinateInterface, SimInterconnect.Arbiter] = {}
        self.rsp: Dict[ManagerInterface, Tuple[IRESP, HREADY]] = {}
        self.bus_width: Optional[int] = None
        self.first_process: bool = True


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def register_manager(self: T, manager: ManagerInterface,
                         interconnect_id: Optional[int] = None,
                         name: Optional[str] = None) -> T:
        assert manager not in self.manager_address_map, "Manager already registered"
        assert interconnect_id not in self.manager_used_id, \
                "2 Managers where given same interconnect_id"
        if interconnect_id is not None:
            self.manager_used_id.add(interconnect_id)
        self.managers_waiting.add(manager)
        self.manager_address_map[manager] = []
        manager.set_ready(HREADY.WaitState)
        next_valid: int = 0
        while next_valid in self.id_to_manager:
            next_valid += 1
        if interconnect_id in self.id_to_manager:
            _manager = self.id_to_manager[interconnect_id]
            self.manager_to_id[_manager] = next_valid
            self.id_to_manager[next_valid] = _manager
        if interconnect_id is not None:
            next_valid = interconnect_id
        self.manager_to_id[manager] = next_valid
        self.id_to_manager[next_valid] = manager
        if self.bus_width is None:
            self.bus_width = manager.bus_width
        else:
            assert self.bus_width == manager.bus_width, f"{self.bus_width} != {manager.bus_width}"
        self.manager_default_subordinate[manager] = SimDefaultSubordinate(0x400, self.bus_width)
        return self


    def register_manager_subordinate_addr(self, manager: ManagerInterface,
                                          subordinate: SubordinateInterface,
                                          address: int, size: int) -> None:
        assert manager in self.manager_address_map, "Manager not registered"
        assert subordinate in self.arbiters, "Subordinate not registered"
        assert address % 1024 == 0, "Subordinate base address must be alligned to 1KiB boundry"
        cnt = len(self.manager_address_map[manager])
        for _address, _size in self.manager_address_map[manager]:
            assert address not in range(_address, _address + _size) and \
                    _address not in range(address, address + size), \
                    f"Subordinates memory regions overlap 0x{_address:x}:0x{_address+_size:x} and 0x{address:x}:0x{address+size:x}"
        self.manager_id_subordinate_map[(manager, cnt)] = subordinate
        self.manager_address_map[manager].append((address, size))


    def get_subordinate_from_manager_cmd(self, manager: ManagerInterface, cmd: MCMD) -> SubordinateInterface:
        for i, (addr, length) in enumerate(self.manager_address_map[manager]):
            if cmd.hAddr in range(addr, addr + length):
                return self.manager_id_subordinate_map[(manager, i)]
        return self.manager_default_subordinate[manager]


    def change_manager_id(self, cmd: MCMD, manager: ManagerInterface) -> MCMD:
        m_id = self.manager_to_id[manager]
        new_id = m_id << 4 | cmd.hMaster
        return MCMD(hAddr=cmd.hAddr, hBurst=cmd.hBurst, hMastlock=cmd.hMastlock,
                    hProt=cmd.hProt, hSize=cmd.hSize, hNonsec=cmd.hNonsec,
                    hExcl=cmd.hExcl, hMaster=new_id, hTrans=cmd.hTrans,
                    hWstrb=cmd.hWstrb, hWrite=cmd.hWrite)


    def register_subordinate(self: T, subordinate: SubordinateInterface,
                             name: Optional[str] = None) -> T:
        assert subordinate not in self.arbiters, "Subordinate already registered"
        self.subordinates_waiting.add(subordinate)
        subordinate.set_ready(HREADY.WaitState)
        self.arbiters[subordinate] = SimInterconnect.Arbiter()
        if self.bus_width is None:
            self.bus_width = subordinate.bus_width
        else:
            assert self.bus_width == subordinate.bus_width
        return self


    def prep_default(self) -> None:
        for _, subordinate in self.manager_default_subordinate.items():
            cocotb.fork(subordinate.register_clock(self.clock).register_reset(self.reset, self.inverted).start())
            self.subordinates_waiting.add(subordinate)
            subordinate.set_ready(HREADY.WaitState)
            self.arbiters[subordinate] = SimInterconnect.Arbiter()


    def do_reset(self) -> None:
        for manager in self.managers_waiting:
            manager.set_ready(HREADY.Working)
            manager.put_rsp(IRESP())
            self.managers_ready.add(manager)

        self.managers_waiting -= self.managers_ready

        for subordinate in self.subordinates_waiting:
            subordinate.set_ready(HREADY.Working)
            subordinate.put_cmd(ICMD())
            self.subordinates_ready.add(subordinate)

        self.subordinates_waiting -= self.subordinates_ready

        self.subordinates_manager_resp = {}
        self.rsp = {}


    def proc_data(self) -> None:
        for subordinate, arbiter in self.arbiters.items():
            subordinate.put_data(arbiter.get_data())


    def proc_rsp(self) -> None:
        for subordinate in self.subordinates_waiting:
            rsp = subordinate.get_rsp()
            manager = self.subordinates_manager_resp[subordinate]
            assert manager is not None
            self.rsp[manager] = (IRESP(hRData=rsp.hRData,
                                       hResp=rsp.hResp,
                                       hExOkay=rsp.hExOkay),
        HREADY.Working if rsp.hReadyOut == HREADYOUT.Ready else HREADY.WaitState)
            if rsp.hReadyOut == HREADYOUT.Ready:
                subordinate.set_ready(HREADY.Working)
                self.subordinates_manager_resp[subordinate] = None
                self.subordinates_ready.add(subordinate)

        self.subordinates_waiting -= self.subordinates_ready

        for imanager, (irsp, ready) in self.rsp.items():
            imanager.put_rsp(irsp)
            if ready == HREADY.Working:
                imanager.set_ready(ready)
                self.managers_ready.add(imanager)

        self.managers_waiting -= self.managers_ready
        self.rsp = {}


    def proc_cmd(self) -> None:
        for manager in self.managers_ready:
            cmd = manager.get_cmd()
            subordinate = self.get_subordinate_from_manager_cmd(manager, cmd)
            cmd = self.change_manager_id(cmd, manager)
            sub_cmd = ICMD(*cmd, HSEL.Sel)
            arbiter = self.arbiters[subordinate]
            arbiter.queue_cmd(sub_cmd, manager)
            self.managers_waiting.add(manager)

        self.managers_ready -= self.managers_waiting

        for subordinate in self.subordinates_ready:
            arbiter = self.arbiters[subordinate]
            icmd, imanager = arbiter.get_cmd()
            subordinate.put_cmd(icmd)
            if imanager is not None:
                self.subordinates_manager_resp[subordinate] = imanager
                self.subordinates_waiting.add(subordinate)

        self.subordinates_ready -= self.subordinates_waiting


    async def start(self) -> None:
        raise Exception("SimInterconnect must be registered in InterconnectWrapper")


    async def process(self) -> None:
        if self.first_process:
            self.prep_default()
            self.first_process=False
            await ReadWrite()
            if self.is_reset():
                self.do_reset()
            await ReadOnly()
            return

        if self.is_reset():
            self.do_reset()
        else:
            for manager in self.managers_waiting:
                manager.set_ready(HREADY.WaitState)

            for subordinate in self.subordinates_waiting:
                subordinate.set_ready(HREADY.WaitState)

            self.proc_data()
            self.proc_rsp()
            self.proc_cmd()

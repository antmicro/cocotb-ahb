# Copyright (c) 2022, Antmicro
# SPDX-License-Identifier: Apache-2.0

from typing import List, TypeVar, Tuple, Dict, Set, Any, Optional
import random

import cocotb # type: ignore
from cocotb.handle import SimHandleBase # type: ignore
from cocotb.triggers import RisingEdge, ReadOnly, Event, Combine # type: ignore

from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.InterconnectInterface import InterconnectInterface

T = TypeVar('T')
S = TypeVar('S')
R = TypeVar('R')

class SimTrafficTester(SimulationInterface):
    class manager_stub(ManagerInterface, SimulationInterface):
        def __init__(self, num_transactions: int, wait: Event, bus_width: int = 32):
            self.bus_width = bus_width
            self.bus_byte_width = bus_width//8
            self.command: MCMD = MCMD()
            self.sub_id: Optional[int] = None
            self.old_command: MCMD = MCMD()
            self.old_sub_id: Optional[int] = None
            self.response: IRESP = IRESP()
            self.num_transactions: int = num_transactions
            self.addr_map: Dict[int, Tuple[int, int]] = {}
            self.running: bool = True
            self.waiting_for_rsp: int = -1
            self.done_processing: Event = Event()
            self.wait: Event = wait
            self.to_be_delayed: MDATA = MDATA(0)
            self.delayed: MDATA = MDATA(0)


        def set_ready(self, hReady: HREADY) -> None:
            self.ready = hReady


        def is_ready(self) -> bool:
            return self.ready == HREADY.Working


        def get_cmd(self) -> MCMD:
            return self.command


        def get_data(self) -> MDATA:
            return self.delayed


        def put_rsp(self, resp: IRESP) -> None:
            self.response = resp


        def register_clock(self: S, clock: SimHandleBase) -> S:
            self.clock = clock
            return self


        def register_reset(self: S, reset: SimHandleBase, inverted: bool = False) -> S:
            self.reset = reset
            self.inverted = inverted
            return self


        def register_subordinate_addr(self, sub_id: int, address: int, length: int) -> None:
            self.addr_map[sub_id] = (address, length)


        def random_command(self) -> MCMD:
            self.sub_id = random.randint(0, len(self.addr_map)-1)
            temp: Dict[Any, Any] = {}
            temp["hBurst"] = HBURST(random.randint(0, 7))
            temp["hSize"] = HSIZE(random.randint(0, 2))
            temp["hNonsec"] = HNONSEC(random.randint(0, 1))
            temp["hExcl"] = HEXCL(random.randint(0, 1))
            temp["hTrans"] = HTRANS(random.randint(0, 3))
            temp["hWstrb"] = random.randint(0, 15)
            temp["hWrite"] = HWRITE(random.randint(0, 1))
            (addr, length) = self.addr_map[self.sub_id]
            temp["hAddr"] = random.randrange(addr, addr+length, 2**temp["hSize"])
            self.to_be_delayed = MDATA(random.randint(0, 2*32-1)) if temp["hWrite"] == HWRITE.Write else MDATA(0)
            return MCMD(**temp)


        def is_reset(self) -> bool:
            return bool(self.reset.value ^ self.inverted)


        def do_reset(self) -> None:
            self.command = MCMD()
            self.sub_id = None


        async def start(self) -> None:
            clock_edge = RisingEdge(self.clock)
            readonly = ReadOnly()
            _loop = True
            while _loop:
                await readonly
                self.old_command = MCMD(*self.command)
                self.old_sub_id = self.sub_id
                if self.is_reset():
                    self.do_reset()
                elif self.is_ready():
                    self.waiting_for_rsp += 1
                    self.command = self.random_command()
                    self.num_transactions -= 1
                if self.num_transactions == 0:
                    _loop = False
                    self.do_reset()
                await self.wait.wait()
                self.done_processing.set()

                self.valid_address_stage = False
                if not self.is_reset() and self.is_ready():
                    self.valid_address_stage = True
                if self.valid_address_stage:
                    self.delayed = self.to_be_delayed

                await clock_edge
            self.running = False
            while True:
                await readonly
                self.done_processing.set()
                self.old_command = MCMD(*self.command)
                self.old_sub_id = self.sub_id
                await clock_edge



    class subordinate_stub(SubordinateInterface, SimulationInterface):
        def __init__(self, wait: Event, bus_width: int = 32):
            self.bus_width = 32
            self.bus_byte_width = bus_width//8
            self.command: ICMD = ICMD()
            self.response: SRESP = SRESP()
            self.old_response: SRESP
            self.manager_id: int = -1
            self.done_processing: Event = Event()
            self.wait_for: int = 0
            self.active_cmd: bool = False
            self.wait: Event = wait
            self.wdata: int = 0


        def set_ready(self, hReady: HREADY) -> None:
            self.ready = hReady


        def is_ready(self) -> bool:
            return self.ready == HREADY.Working


        def put_cmd(self, cmd: ICMD) -> None:
            self.command = cmd
            self.active_cmd = cmd.hSel == HSEL.Sel


        def put_data(self, data: IDATA) -> None:
            self.wdata = data.hWData


        def get_rsp(self) -> SRESP:
            return self.response


        def register_clock(self: R, clock: SimHandleBase) -> R:
            self.clock = clock
            return self


        def register_reset(self: S, reset: SimHandleBase, inverted: bool = False) -> S:
            self.reset = reset
            self.inverted = inverted
            return self


        def random_rsp(self) -> SRESP:
            temp: Dict[Any, Any] = {}
            temp["hResp"] = HRESP(random.randint(0, 1)) if self.wait_for > 0 else HRESP.Successful
            temp["hReadyOut"] = HREADYOUT.NotReady if self.wait_for > 0 else HREADYOUT.Ready
            temp["hExOkay"] = HEXOKAY(random.randint(0, 1)) if self.wait_for > 0 else HEXOKAY.Failed
            temp["hRData"] = random.randint(0, 2**32-1) if self.wait_for > 0 else 0
            return SRESP(**temp)


        def is_reset(self) -> bool:
            return bool(self.reset.value ^ self.inverted)


        def do_reset(self) -> None:
            self.response = SRESP()


        async def start(self) -> None:
            clock_edge = RisingEdge(self.clock)
            readonly = ReadOnly()
            while True:
                await readonly
                self.old_response = SRESP(*self.response)
                if self.is_reset():
                    self.do_reset()
                elif self.is_ready() and self.command.hSel == HSEL.Sel:
                    self.wait_for = random.randint(0, 3)
                    self.manager_id = self.command.hMaster>>4
                self.response = self.random_rsp()
                self.wait_for -= 1
                await self.wait.wait()
                self.done_processing.set()
                await clock_edge



    def __init__(self, num_managers: int, num_subordinates: int,
                 interconnect: InterconnectInterface, num_of_transactions: int = 100):
        self.prep: Event = Event()
        self.managers: List[SimTrafficTester.manager_stub] = \
            [SimTrafficTester.manager_stub(num_of_transactions, self.prep) for i in range(num_managers)]
        self.num_subordinates = num_subordinates
        self.subordinates: List[SimTrafficTester.subordinate_stub] = \
            [SimTrafficTester.subordinate_stub(self.prep) for i in range(num_subordinates)]
        self.manager_sub_addr_map: Dict[Tuple[ManagerInterface, \
                                              SubordinateInterface], \
                                        Tuple[int, int]] = {}
        self.subordinate_cmd: Dict[SimTrafficTester.subordinate_stub, Set[ICMD]] = {}
        self.manager_rsp: Dict[SimTrafficTester.manager_stub, List[IRESP]] = {}

        for i, manager in enumerate(self.managers):
            interconnect.register_manager(manager, i)
            self.manager_rsp[manager] = [IRESP()]
        for subordinate in self.subordinates:
            interconnect.register_subordinate(subordinate)
            self.subordinate_cmd[subordinate] = set()
        for i, manager in enumerate(self.managers):
            addresses = random.sample(range(2*8, 2**22, 4), num_subordinates)
            for j, subordinate in enumerate(self.subordinates):
                length = random.sample([1,2,4], 1)[0]
                self.manager_sub_addr_map[(manager, subordinate)] = (addresses[j]<<10, length<<10)
                manager.register_subordinate_addr(j, addresses[j]<<10, length)


    def manager_subordinate_addr_map(self) -> Dict[Tuple[ManagerInterface, SubordinateInterface], Tuple[int, int]]:
        return self.manager_sub_addr_map


    def register_clock(self: T, clock: SimHandleBase) -> T:
        self.clock = clock
        return self


    def register_reset(self: T, reset: SimHandleBase, inverted: bool = False) -> T:
        self.reset = reset
        self.inverted = inverted
        return self


    def is_reset(self) -> bool:
        return bool(self.reset.value ^ self.inverted)


    def do_reset(self) -> None:
        for subordinate in self.subordinates:
            self.subordinate_cmd[subordinate] = set()


    def icmd_from_mcmd(self, cmd: MCMD, manager_id: int) -> ICMD:
        temp: Dict[Any, Any] = cmd._asdict()
        temp["hMaster"] = manager_id << 4 | temp["hMaster"]
        temp["hSel"] = HSEL.Sel
        return ICMD(**temp)


    def iresp_from_sresp(self, rsp: SRESP) -> IRESP:
        return IRESP(hRData=rsp.hRData, hResp=rsp.hResp, hExOkay=rsp.hExOkay)


    async def start(self) -> None:
        clock_edge = RisingEdge(self.clock)
        readonly = ReadOnly()
        list_of_triggers: List[Event] = [i.done_processing for i in self.managers]
        list_of_triggers += [i.done_processing for i in self.subordinates]

        for manager in self.managers:
            manager.register_clock(self.clock)
            manager.register_reset(self.reset, self.inverted)
            cocotb.fork(manager.start())

        for subordinate in self.subordinates:
            subordinate.register_clock(self.clock)
            subordinate.register_reset(self.reset, self.inverted)
            cocotb.fork(subordinate.start())

        _loop = True
        while _loop:
            await readonly
            self.prep.set()
            await Combine(*[i.wait() for i in list_of_triggers])
            self.prep.clear()
            for t in list_of_triggers:
                t.clear()
            for i, manager in enumerate(self.managers):
                if manager.is_ready():
                    if manager.old_sub_id is not None:
                        subordinate = self.subordinates[manager.old_sub_id]
                        icmd = self.icmd_from_mcmd(manager.old_command, i)
                        self.subordinate_cmd[subordinate].add(icmd)

            for i, subordinate in enumerate(self.subordinates):
                if subordinate.is_ready():
                    manager = self.managers[subordinate.manager_id]
                    if subordinate.old_response.hReadyOut != HREADYOUT.Ready:
                        continue
                    iresp = self.iresp_from_sresp(subordinate.old_response)
                    self.manager_rsp[manager].append(iresp)

            for manager in self.managers:
                if manager.is_ready() and manager.running and manager.waiting_for_rsp > 0:
                    assert manager.response == self.manager_rsp[manager][0], \
                                f"got: {manager.response} expected:{self.manager_rsp[manager][0]}"
                    self.manager_rsp[manager] = self.manager_rsp[manager][1:]

            for subordinate in self.subordinates:
                if subordinate.is_ready() and subordinate.active_cmd:
                    assert subordinate.command in self.subordinate_cmd[subordinate], \
                                f"got: {subordinate.command} " \
                                f"expected:{self.subordinate_cmd[subordinate]}"
                    assert len(self.subordinate_cmd[subordinate]) <= len(self.managers), \
                            f"{self.subordinate_cmd[subordinate]} {len(self.managers)}"
                    self.subordinate_cmd[subordinate].remove(subordinate.command)

            _loop = False
            for manager in self.managers:
                if manager.running:
                    _loop = True
            await clock_edge

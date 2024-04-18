from typing import List, Dict, Tuple

import cocotb # type: ignore
from cocotb.clock import Clock # type: ignore
from cocotb.regression import TestFactory # type: ignore
from cocotb.handle import SimHandle, SimHandleBase # type: ignore
from cocotb.log import SimLog # type: ignore
from cocotb.triggers import ClockCycles, Combine, Join, RisingEdge, ReadOnly, ReadWrite, Timer # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.InterconnectInterface import InterconnectWrapper

from cocotb_AHB.interconnect.SimInterconnect import SimInterconnect

from cocotb_AHB.drivers.SimMem1PSubordinate import SimMem1PSubordinate
from cocotb_AHB.drivers.SimDefaultSubordinate import SimDefaultSubordinate

from cocotb_AHB.monitors.AHBSignalMonitor import AHBSignalMonitor
from cocotb_AHB.monitors.AHBPacketMonitor import AHBPacketMonitor
from cocotb_AHB.drivers.SimCmdExecAndCheck import SimCmdExecAndCheck
from cocotb_AHB.drivers.SimTrafficTester import SimTrafficTester

CLK_PERIOD = (10, "ns")

async def setup_dut(dut: SimHandle) -> None:
    await cocotb.start(Clock(dut.clk, *CLK_PERIOD).start())
    dut.rstn.value = 0
    await ClockCycles(dut.clk, 10)
    await RisingEdge(dut.clk)
    await Timer(1, units='ns')
    dut.rstn.value = 1
    await ClockCycles(dut.clk, 1)


async def _test(dut: SimHandle, managers: List[ManagerInterface],
                managers_proc: List[Join],
                subordinates: List[SubordinateInterface],
                manager_subordinate_addr_map: List[Tuple[ManagerInterface, SubordinateInterface, int, int]]) -> None:
    interconnect = SimInterconnect()
    interconnect.register_clock(dut.clk)
    interconnect.register_reset(dut.rstn, True)
    for manager in managers:
        interconnect.register_manager(manager)
    for subordinate in subordinates:
        interconnect.register_subordinate(subordinate)
    for mapping in manager_subordinate_addr_map:
        interconnect.register_manager_subordinate_addr(*mapping)

    interconnect_wrapper = InterconnectWrapper()
    interconnect_wrapper.register_clock(dut.clk)
    interconnect_wrapper.register_reset(dut.rstn, True)
    interconnect_wrapper.register_interconnect(interconnect)

    await cocotb.start(interconnect_wrapper.start())

    await cocotb.start(setup_dut(dut))
    try:
        await Combine(*managers_proc)
    except Exception:
        await RisingEdge(dut.clk)
        raise


@cocotb.test() # type: ignore
async def should_fail_manager_not_registered(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    subD = SimDefaultSubordinate(0x4000, 32)
    manager = SimCmdExecAndCheck([],[])
    interconnect = SimInterconnect().register_subordinate(subD)
    try:
        interconnect.register_manager_subordinate_addr(manager, subD, 0x400, 0x1000)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_manager_reregistered(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    manager = SimCmdExecAndCheck([],[])
    try:
        interconnect = SimInterconnect().register_manager(manager).register_manager(manager)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_subordinate_not_registered(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    subD = SimDefaultSubordinate(0x4000, 32)
    manager = SimCmdExecAndCheck([],[])
    interconnect = SimInterconnect().register_manager(manager)
    try:
        interconnect.register_manager_subordinate_addr(manager, subD, 0x400, 0x1000)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_subordinate_reregistered(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    subD = SimDefaultSubordinate(0x4000, 32)
    try:
        interconnect = SimInterconnect().register_subordinate(subD).register_subordinate(subD)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_address_aligment(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    subD = SimDefaultSubordinate(0x4000, 32)
    manager = SimCmdExecAndCheck([],[])
    interconnect = SimInterconnect().register_manager(manager).register_subordinate(subD)
    try:
        interconnect.register_manager_subordinate_addr(manager, subD, 0x498, 0x1000)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_overlap(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    sub1 = SimDefaultSubordinate(0x4000, 32)
    sub2 = SimDefaultSubordinate(0x4000, 32)
    manager = SimCmdExecAndCheck([],[])
    interconnect = SimInterconnect().register_manager(manager).register_subordinate(sub1).register_subordinate(sub2)
    try:
        interconnect.register_manager_subordinate_addr(manager, sub1, 0x400, 0x1000)
        interconnect.register_manager_subordinate_addr(manager, sub2, 0x800, 0x1000)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def should_fail_managers_id(dut: SimHandle) -> None:
    log = SimLog("cocotb.should_fail")
    manager1 = SimCmdExecAndCheck([],[])
    manager2 = SimCmdExecAndCheck([],[])
    interconnect = SimInterconnect()
    try:
        interconnect.register_manager(manager1, 0).register_manager(manager2, 0)
    except Exception as e:
        log.info(e)
        return
    assert False


@cocotb.test() # type: ignore
async def test_simple(dut: SimHandle) -> None:
    subD = SimDefaultSubordinate(0x4000, 32)
    subD.register_clock(dut.clk)
    subD.register_reset(dut.rstn, True)
    await cocotb.start(subD.start())

    sub0 = SimMem1PSubordinate(0x4000, 32)
    sub0.register_clock(dut.clk)
    sub0.register_reset(dut.rstn, True)
    await cocotb.start(sub0.start())

    sub1 = SimMem1PSubordinate(0x4000, 32, exclusive_transfers=True)
    sub1.register_clock(dut.clk)
    sub1.register_reset(dut.rstn, True)
    await cocotb.start(sub1.start())

    manager = SimCmdExecAndCheck([
                        (MCMD(hAddr=0x4004, hSize=HSIZE.Word, hWrite=HWRITE.Write, hTrans=HTRANS.NonSeq), MDATA(0x87654321)),
                        (MCMD(hAddr=0x4004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0x4, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0x6, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),# Command that will not be executed due to prewious failure
                        (MCMD(hAddr=0x4, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.Idle), MDATA()),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq, hExcl=HEXCL.Excl), MDATA()),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Write, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq, hExcl=HEXCL.Excl), MDATA(0x1234)),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq), MDATA()),
                        ],
                       [IRESP(hResp=HRESP.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x4321),
                        IRESP(hResp=HRESP.Failed),
                        IRESP(hResp=HRESP.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x0, hExOkay=HEXOKAY.Successful),
                        IRESP(hResp=HRESP.Successful, hExOkay=HEXOKAY.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x1234),
                        ])
    manager.register_clock(dut.clk)
    manager.register_reset(dut.rstn, True)

    await _test(dut, [manager], [Join(await cocotb.start(manager.start()))],
                [subD, sub0, sub1],
                [(manager, subD, 0, 0x4000),
                 (manager, sub0, 0x4000, 0x4000),
                 (manager, sub1, 0x8000, 0x4000)])


@cocotb.test() # type: ignore
async def test_default_subordinate(dut: SimHandle) -> None:
    sub0 = SimMem1PSubordinate(0x4000, 32)
    sub0.register_clock(dut.clk)
    sub0.register_reset(dut.rstn, True)
    await cocotb.start(sub0.start())

    sub1 = SimMem1PSubordinate(0x4000, 32, exclusive_transfers=True)
    sub1.register_clock(dut.clk)
    sub1.register_reset(dut.rstn, True)
    await cocotb.start(sub1.start())

    manager = SimCmdExecAndCheck([
                        (MCMD(hAddr=0x4004, hSize=HSIZE.Word, hWrite=HWRITE.Write, hTrans=HTRANS.NonSeq), MDATA(0x87654321)),
                        (MCMD(hAddr=0x4004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0x4, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0x6, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        # ^Command that will not be executed due to prewious failure
                        (MCMD(hAddr=0x4, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.Idle), MDATA()),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq, hExcl=HEXCL.Excl), MDATA()),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Write, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq, hExcl=HEXCL.Excl), MDATA(0x1234)),
                        (MCMD(hAddr=0x8004, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0xFFFFFFF4, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0xFFFFFFF6, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        # ^Command that will not be executed due to prewious failure
                        (MCMD(hAddr=0xFFFFFFF4, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.Idle), MDATA()),
                        (MCMD(hAddr=0x7FFFFFF4, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        (MCMD(hAddr=0x7FFFFFF6, hWrite=HWRITE.Write, hSize=HSIZE.Byte, hTrans=HTRANS.NonSeq), MDATA()),
                        # ^Command that will not be executed due to prewious failure
                        (MCMD(hAddr=0x7FFFFFF4, hWrite=HWRITE.Read, hSize=HSIZE.Halfword, hTrans=HTRANS.Idle), MDATA()),
                        ],
                       [IRESP(hResp=HRESP.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x4321),
                        IRESP(hResp=HRESP.Failed),
                        IRESP(hResp=HRESP.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x0, hExOkay=HEXOKAY.Successful),
                        IRESP(hResp=HRESP.Successful, hExOkay=HEXOKAY.Successful),
                        IRESP(hResp=HRESP.Successful, hRData=0x1234),
                        IRESP(hResp=HRESP.Failed),
                        IRESP(hResp=HRESP.Successful),
                        IRESP(hResp=HRESP.Failed),
                        IRESP(hResp=HRESP.Successful),
                        ])
    manager.register_clock(dut.clk)
    manager.register_reset(dut.rstn, True)

    await _test(dut, [manager], [Join(await cocotb.start(manager.start()))],
                [sub0, sub1],
                [(manager, sub0, 0x4000, 0x4000),
                 (manager, sub1, 0x8000, 0x4000)])


async def test_factory(dut: SimHandle, num_managers: int, num_subordinates: int,
                       num_of_transactions: int = 100) -> None:
    if num_managers * num_of_transactions * num_subordinates > 204800 or num_managers * num_of_transactions > 5000:
        return
    print(f"{num_managers=}, {num_of_transactions=}, {num_subordinates=}")
    interconnect = SimInterconnect()
    interconnect.register_clock(dut.clk)
    interconnect.register_reset(dut.rstn, True)

    trafic_gen = SimTrafficTester(num_managers, num_subordinates, interconnect, num_of_transactions)
    trafic_gen.register_clock(dut.clk).register_reset(dut.rstn, True)
    for (man, sub), (addr, length) in trafic_gen.manager_subordinate_addr_map().items():
        interconnect.register_manager_subordinate_addr(man, sub, addr, length)

    interconnect_wrapper = InterconnectWrapper()
    interconnect_wrapper.register_clock(dut.clk)
    interconnect_wrapper.register_reset(dut.rstn, True)
    interconnect_wrapper.register_interconnect(interconnect)

    await cocotb.start(interconnect_wrapper.start())

    await cocotb.start(setup_dut(dut))
    runner = Join(await cocotb.start(trafic_gen.start()))
    try:
        await runner
    except Exception:
        await RisingEdge(dut.clk)
        raise


test_ans = TestFactory(test_factory)
test_ans.add_option('num_managers', (1, 2, 4, 8, 16, 32))
test_ans.add_option('num_subordinates', (1, 2, 4, 8, 16, 32, 64))
test_ans.add_option('num_of_transactions', (100, 1000, 2000, 5000))
test_ans.generate_tests()

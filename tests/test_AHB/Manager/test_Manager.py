from random import randint
from typing import List, Type, Optional

import cocotb # type: ignore
from cocotb.clock import Clock # type: ignore
from cocotb.regression import TestFactory # type: ignore
from cocotb.handle import SimHandle # type: ignore
from cocotb.log import SimLog # type: ignore
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly, ReadWrite, Timer # type: ignore
from numpy.random import default_rng # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.ManagerInterface import ManagerInterface
from cocotb_AHB.AHB_common.MonitorInterface import SimMonitorInterface
from cocotb_AHB.AHB_common.SimulationInterface import SimulationInterface
from cocotb_AHB.drivers.SimTrafficGenerator import SimTrafficGenerator

from cocotb_AHB.monitors.AHBSignalMonitor import AHBSignalMonitor
from cocotb_AHB.monitors.AHBPacketMonitor import AHBPacketMonitor

CLK_PERIOD = (10, "ns")

async def setup_dut(dut: SimHandle) -> None:
    await cocotb.start(Clock(dut.clk, *CLK_PERIOD).start())
    dut.rstn.value = 0
    await ClockCycles(dut.clk, 10)
    await RisingEdge(dut.clk)
    await Timer(1, units='ns')
    dut.rstn.value = 1
    await ClockCycles(dut.clk, 1)


async def reset_AHB(dut: SimHandle,
                    managers: List[ManagerInterface]) -> None:
    for manager in managers:
        manager.set_ready(HREADY.WaitState)
        manager.put_rsp(IRESP(HRESP.Failed, HEXOKAY.Failed, 0))

    await ReadOnly()
    while dut.rstn.value == 0:
        await RisingEdge(dut.clk)
        await ReadWrite()
        for manager in managers:
            manager.put_rsp(IRESP(HRESP.Failed, HEXOKAY.Failed, 0))


async def _test(dut: SimHandle, address_width: int, bus_width: int,
                burst: bool = False, exclusive_transfers: bool = False,
                secure_transfer: bool = False, nonsec_read: bool = False, nonsec_write: bool = False,
                write_strobe: bool = False, locking: bool = False,
                Monitor: Optional[Type[SimMonitorInterface]] = None) -> None:
    bus_byte_width = bus_width//8
    manager = SimTrafficGenerator(address_width, bus_width, burst=burst,
                                  exclusive_transfers=exclusive_transfers,
                                  write_strobe=write_strobe, secure_transfer=secure_transfer,
                                  nonsec_read=nonsec_read, nonsec_write=nonsec_write)
    manager.register_clock(dut.clk)
    manager.register_reset(dut.rstn, True)
    manager.set_ready(HREADY.Working)
    await cocotb.start(manager.start())

    if Monitor is not None:
        monitor = Monitor()
        monitor.register_device(manager)
        monitor.register_clock(dut.clk)
        monitor.register_reset(dut.rstn, True)
        await cocotb.start(monitor.start())

    random_gen = default_rng()

    await cocotb.start(setup_dut(dut))
    await reset_AHB(dut, [manager])
    risingedge = RisingEdge(dut.clk)
    command: MCMD
    was_in_rst = True
    for i in range(0, 10000):
        manager.set_ready(HREADY.Working)
        command = manager.get_cmd()
        assert command.hAddr in range(0, 2**address_width), \
            "Address out of range"
        assert command.hBurst == HBURST.Incr or burst, \
            "Burst command from non bursting Manager"
        assert command.hMastlock == HMASTLOCK.UnLocked or locking, \
            "Lock from non locking Manager"
        assert 2**command.hSize <= bus_byte_width, \
            "Transfer szie greater than data bus width"
        assert command.hNonsec == HNONSEC.Secure or secure_transfer, \
            "Non secure transfer from Manager without secure transfers"
        assert command.hExcl != HEXCL.Excl or exclusive_transfers, \
            "Exclusive packet from Manager without exclusive transfers"
        assert command.hTrans in [HTRANS.Idle, HTRANS.NonSeq] or burst, \
            "Non bursting Manager send burst type transfer"
        assert command.hTrans in [HTRANS.Idle, HTRANS.Busy] or command.hWrite != HWRITE.Write or \
            command.hWstrb == 2**bus_byte_width - 1 or write_strobe, \
            f"Manager without write strobe support send non full mask {command.hWstrb}"
        assert command.hWrite != HWRITE.Write or 2**command.hSize <= bus_byte_width, \
            "Packet size greater than bus width"
        await risingedge
        wdata = manager.get_data()
        assert wdata.hWData in range(0, 2**bus_width), \
            "Transfer data not in integer range of data bus"
        await ReadWrite()
        if randint(0, 99) in range(0,25): # stall
            wait_for = min(random_gen.poisson(5), 60)
            last_command: Optional[MCMD] = None
            manager.put_rsp(IRESP(HRESP.Successful, HEXOKAY.Failed, 0))
            manager.set_ready(HREADY.WaitState)
            for i in range(0, wait_for):
                new_command = manager.get_cmd()
                assert last_command is None or (last_command[8] == HTRANS.Idle or new_command[8] == HTRANS.NonSeq) \
                       or burst and (last_command[8] == HTRANS.Busy or new_command[8] == HTRANS.Seq), \
                    f"Manager changed command during wait state from HTRANS.Idle to {last_command[8].__str__()}" \
                    f" to {new_command[8].__str__()}, only HTRANS.NonSeq is allowed"
                if last_command is not None and last_command[8] not in [HTRANS.Idle, HTRANS.Busy]:
                    assert last_command == new_command, f"\n{last_command}\n{new_command}"
                last_command = new_command
                await risingedge
                new_wdata = manager.get_data()
                assert wdata.hWData == new_wdata.hWData, "WData mustn't change during wait state"
                await ReadWrite()
        excl = HEXOKAY.Failed
        if command[6] == HEXCL.Excl and randint(0, 9) not in [0,1]:
            excl = HEXOKAY.Successful
        resp = HRESP.Successful
        if randint(0,5) in [4,5]:
            resp = HRESP.Failed
        data = 0
        if command[10] == HWRITE.Read:
            data = randint(0, 2**bus_byte_width-1)
        manager.put_rsp(IRESP(resp, excl, data))
        if resp == HRESP.Failed:
            manager.set_ready(HREADY.WaitState)
            await risingedge
            await ReadWrite()


async def test_simple(dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width)


async def test_burst(dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width, burst=True)


async def test_exclusive_transfer(dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width, exclusive_transfers=True)


async def test_burst_and_exclusive_transfer(
                dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width, burst=True, exclusive_transfers=True)


async def test_secure_transfer(dut: SimHandle, address_width: int, bus_width: int,
                               nonsec_read: bool, nonsec_write: bool) -> None:
    await _test(dut, address_width, bus_width, secure_transfer=True,
                nonsec_read=nonsec_read, nonsec_write=nonsec_write)


async def test_write_strobe(dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width, write_strobe=True)


async def test_Packet_monitor(dut: SimHandle, address_width: int, bus_width: int) -> None:
    await _test(dut, address_width, bus_width, secure_transfer=True,
                nonsec_read=True, nonsec_write=True, write_strobe=True, burst=True,
                exclusive_transfers=True, Monitor=AHBPacketMonitor)


test_ans = TestFactory(test_simple)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()


test_ans = TestFactory(test_burst)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()


test_ans = TestFactory(test_exclusive_transfer)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()


test_ans = TestFactory(test_burst_and_exclusive_transfer)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()


test_ans = TestFactory(test_secure_transfer)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('nonsec_read', (True, False))
test_ans.add_option('nonsec_write', (True, False))
test_ans.generate_tests()


test_ans = TestFactory(test_write_strobe)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()


test_ans = TestFactory(test_Packet_monitor)
test_ans.add_option('address_width', (32,))
test_ans.add_option('bus_width', (32,))
test_ans.generate_tests()

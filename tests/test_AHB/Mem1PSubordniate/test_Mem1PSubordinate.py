from typing import List, Tuple

import cocotb # type: ignore
from cocotb.clock import Clock # type: ignore
from cocotb.regression import TestFactory # type: ignore
from cocotb.handle import SimHandle # type: ignore
from cocotb.log import SimLog # type: ignore
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly, ReadWrite, Timer # type: ignore
from cocotb_AHB.AHB_common.AHB_types import *
from cocotb_AHB.AHB_common.SubordinateInterface import SubordinateInterface
from cocotb_AHB.AHB_common.MonitorInterface import MonitorInterface
from cocotb_AHB.drivers.SimMem1PSubordinate import SimMem1PSubordinate

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
                    subordinates: List[SubordinateInterface]) -> None:
    for subordinate in subordinates:
        subordinate.set_ready(HREADY.WaitState)
        subordinate.put_cmd(ICMD())
    await ReadOnly()
    while dut.rstn.value == 0:
        await RisingEdge(dut.clk)
        await ReadWrite()
        for subordinate in subordinates:
            subordinate.put_cmd(ICMD())


async def test_incorrect_args(dut: SimHandle, length: int, bus_width: int) -> None:
    if length > 0 and length % 1024 == 0 and bus_width in [8*2**i for i in range(8)]:
        return
    log = SimLog("cocotb.test_incorrect")
    try:
        subordinate = SimMem1PSubordinate(length, bus_width)
    except Exception as e:
        log.info(e)
        return
    assert False


async def _test_incorrect(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                          commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL]],
                          log: SimLog, burst: bool = False, exclusive_transfers: bool = False) -> None:
    subordinate = SimMem1PSubordinate(length, bus_width,
                                      burst=burst,exclusive_transfers=exclusive_transfers)
    subordinate.register_clock(dut.clk)
    subordinate.register_reset(dut.rstn, True)
    await cocotb.start(setup_dut(dut))
    sub_task = await cocotb.start(subordinate.start())

    await reset_AHB(dut, [subordinate])
    risingedge = RisingEdge(dut.clk)
    try:
        for command in commands:
            subordinate.set_ready(HREADY.Working)
            subordinate.put_cmd(ICMD(command[0], command[2], HMASTLOCK.Locked, HPROT(),
                                     command[1], HNONSEC.Secure, command[5], 0, command[3],
                                     0xf, command[4], sel))
            await risingedge
            subordinate.put_data(IDATA(0x12345678))
            await ReadWrite()
            rdata, readyout, resp, exokay = subordinate.get_rsp()
            while readyout == HREADYOUT.NotReady and sel == HSEL.Sel:
                subordinate.set_ready(HREADY.WaitState)
                subordinate.put_cmd(ICMD(0x0, HBURST.Single, HMASTLOCK.Locked, HPROT(),
                                         HSIZE.Word, HNONSEC.Secure, HEXCL.NonExcl, 0, HTRANS.Idle,
                                         0xf, HWRITE.Write, sel))
                await risingedge
                subordinate.put_data(IDATA(0x12345678))
                await ReadWrite()
                rdata, readyout, resp, exokay = subordinate.get_rsp()
    except Exception as e:
        sub_task.kill()
        raise e


async def test_incorrect_simple(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                                commands: List[Tuple[int, HSIZE, HTRANS]]) -> None:
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL]] = []
    for command in commands:
        new_commands.append((command[0], command[1], HBURST.Single, command[2], HWRITE.Write, HEXCL.NonExcl))
    log = SimLog("cocotb.test_incorrect_simple")
    try:
        await _test_incorrect(dut, length, bus_width, sel, new_commands, log)
    except Exception as e:
        await RisingEdge(dut.clk)
        log.info(e)
        return
    assert sel == HSEL.NotSel, "Should have failed"


async def test_incorrect_burst(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                               commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE]]) -> None:
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL]] = []
    for command in commands:
        new_commands.append((command[0], command[1], command[2], command[3], command[4], HEXCL.NonExcl))
    log = SimLog("cocotb.test_incorrect_burst")
    try:
        await _test_incorrect(dut, length, bus_width, sel, new_commands, log, burst=True)
    except Exception as e:
        await RisingEdge(dut.clk)
        log.info(e)
        return
    assert sel == HSEL.NotSel, "Should have failed"


async def test_incorrect_exclusive_transfers(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                                              commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL]]) -> None:
    log = SimLog("cocotb.test_incorrect_exclusive_transfers")
    try:
        await _test_incorrect(dut, length, bus_width, sel, commands, log, exclusive_transfers=True)
    except Exception as e:
        await RisingEdge(dut.clk)
        log.info(e)
        return
    assert sel == HSEL.NotSel, "Should have failed"


async def test_incorrect_burst_and_exclusive_transfers(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                                              commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL]]) -> None:
    log = SimLog("cocotb.test_incorrect_exclusive_transfers")
    try:
        await _test_incorrect(dut, length, bus_width, sel, commands, log, burst=True, exclusive_transfers=True)
    except Exception as e:
        await RisingEdge(dut.clk)
        log.info(e)
        return
    assert sel == HSEL.NotSel, "Should have failed"


async def _test(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL, HNONSEC, int, int]],
                answers: List[Tuple[int, HRESP, HEXOKAY]],
                burst: bool = False, exclusive_transfers: bool = False,
                secure_transfer: bool = False, nonsec_read: bool = False, nonsec_write: bool = False,
                write_strobe: bool = False) -> None:
    subordinate = SimMem1PSubordinate(length, bus_width,
                                      burst=burst,exclusive_transfers=exclusive_transfers,
                                      secure_transfer=secure_transfer, nonsec_read=nonsec_read,
                                      nonsec_write=nonsec_write, write_strobe=write_strobe)
    subordinate.register_clock(dut.clk)
    subordinate.register_reset(dut.rstn, True)

    await cocotb.start(setup_dut(dut))
    sub_task = await cocotb.start(subordinate.start())

    await reset_AHB(dut, [subordinate])
    risingedge = RisingEdge(dut.clk)
    for command, answer in zip(commands, answers):
        subordinate.set_ready(HREADY.Working)
        subordinate.put_cmd(ICMD(command[0], command[2], HMASTLOCK.Locked, HPROT(),
                                 command[1], command[6], command[5], 0, command[3],
                                 command[8], command[4], sel))
        await risingedge
        subordinate.put_data(IDATA(command[7]))
        await ReadWrite()
        rsp: SRESP = subordinate.get_rsp()
        while rsp.hReadyOut == HREADYOUT.NotReady:
            subordinate.set_ready(HREADY.WaitState)
            subordinate.put_cmd(ICMD(0x0, HBURST.Single, HMASTLOCK.Locked, HPROT(),
                                     HSIZE.Word, HNONSEC.Secure, HEXCL.NonExcl, 0, HTRANS.Idle,
                                     0xf, HWRITE.Write, sel))
            await risingedge
            subordinate.put_data(IDATA(command[7]))
            await ReadWrite()
            rsp = subordinate.get_rsp()
        assert (rsp.hRData, rsp.hResp, rsp.hExOkay) == answer, f"({rsp.hRData}, {rsp.hResp}, {rsp.hExOkay}) != {answer}"
    subordinate.set_ready(HREADY.Working)
    await risingedge


async def test_simple(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                      commands_answers: List[Tuple[Tuple[int, HSIZE, HTRANS, HWRITE, int], int]]) -> None:
    bus_byte_width = bus_width//8
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL, HNONSEC, int, int]] = []
    new_answers: List[Tuple[int, HRESP, HEXOKAY]] = []
    for command, answer in commands_answers:
        new_commands.append((command[0], command[1], HBURST.Single,
                             command[2], command[3], HEXCL.NonExcl,
                             HNONSEC.Secure, command[4], (2**bus_byte_width-1)))
        new_answers.append((answer, HRESP.Successful, HEXOKAY.Failed))
    await _test(dut, length, bus_width, sel, new_commands, new_answers)


async def test_write_strobe(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                            commands_answers: List[Tuple[Tuple[int, HSIZE, HTRANS, HWRITE, int, int], int]]) -> None:
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL, HNONSEC, int, int]] = []
    new_answers: List[Tuple[int, HRESP, HEXOKAY]] = []
    for command, answer in commands_answers:
        new_commands.append((command[0], command[1], HBURST.Single,
                             command[2], command[3], HEXCL.NonExcl,
                             HNONSEC.Secure, command[4], command[5]))
        new_answers.append((answer, HRESP.Successful, HEXOKAY.Failed))
    await _test(dut, length, bus_width, sel, new_commands, new_answers, write_strobe=True)


async def test_secure_transfer(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                               write_nonsec: bool, read_nonsec: bool,
                               commands_answers: List[Tuple[Tuple[int, HSIZE, HTRANS, HWRITE, int, HNONSEC], Tuple[int, HRESP]]]) -> None:
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL, HNONSEC, int, int]] = []
    new_answers: List[Tuple[int, HRESP, HEXOKAY]] = []
    for command, answer in commands_answers:
        new_commands.append((command[0], command[1], HBURST.Single,
                             command[2], command[3], HEXCL.NonExcl,
                             command[5], command[4], 0))

        new_answers.append((answer[0], answer[1], HEXOKAY.Failed))
    try:
        await _test(dut, length, bus_width, sel, new_commands,
                    new_answers, secure_transfer=True, nonsec_write=write_nonsec, nonsec_read=read_nonsec)
    except Exception:
        await RisingEdge(dut.clk)
        raise


async def test_exclusive_transfer(dut: SimHandle, length: int, bus_width: int, sel: HSEL,
                                  commands_answers: List[Tuple[Tuple[int, HSIZE, HTRANS, HWRITE, int, HEXCL], Tuple[int, HEXOKAY]]]) -> None:
    new_commands: List[Tuple[int, HSIZE, HBURST, HTRANS, HWRITE, HEXCL, HNONSEC, int, int]] = []
    new_answers: List[Tuple[int, HRESP, HEXOKAY]] = []
    for command, answer in commands_answers:
        new_commands.append((command[0], command[1], HBURST.Single,
                             command[2], command[3], command[5],
                             HNONSEC.Secure, command[4], 0))

        new_answers.append((answer[0], HRESP.Successful, answer[1]))
    await _test(dut, length, bus_width, sel, new_commands,
                new_answers, exclusive_transfers=True)


# Should fail is selected, but must not if unselected

should_fail = TestFactory(test_incorrect_args)
should_fail.add_option('length', (0, 4095, 1023, 1024, 4096))
should_fail.add_option('bus_width', (1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128))
should_fail.generate_tests()

should_fail = TestFactory(test_incorrect_simple)
should_fail.add_option('length', (1024,))
should_fail.add_option('bus_width', (32,))
should_fail.add_option('sel', (HSEL.Sel, HSEL.NotSel))
should_fail.add_option('commands', ([(0x201, HSIZE.Halfword, HTRANS.Idle)],
                                    [(0x201, HSIZE.Halfword, HTRANS.Busy)],
                                    [(0x201, HSIZE.Halfword, HTRANS.Seq)],
                                    [(0x201, HSIZE.Halfword, HTRANS.NonSeq)],
                                    [(0x201, HSIZE.Word, HTRANS.Idle)],
                                    [(0x201, HSIZE.Word, HTRANS.Busy)],
                                    [(0x201, HSIZE.Word, HTRANS.Seq)],
                                    [(0x201, HSIZE.Word, HTRANS.NonSeq)],
                                    [(0x200, HSIZE.Doubleword, HTRANS.Idle)],
                                    [(0x200, HSIZE.Doubleword, HTRANS.Busy)],
                                    [(0x200, HSIZE.Doubleword, HTRANS.Seq)],
                                    [(0x200, HSIZE.Doubleword, HTRANS.NonSeq)],

))
should_fail.generate_tests()

should_fail = TestFactory(test_incorrect_burst)
should_fail.add_option('length', (1024,))
should_fail.add_option('bus_width', (32,))
should_fail.add_option('sel', (HSEL.Sel, HSEL.NotSel))
should_fail.add_option('commands', ([(0x3F4, HSIZE.Word, HBURST.Incr4, HTRANS.NonSeq, HWRITE.Write)],
                                    [(0x3E4, HSIZE.Word, HBURST.Incr8, HTRANS.NonSeq, HWRITE.Write)],
                                    [(0x3C4, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Write)],
                                    [(0x380, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Write),
                                     (0x380, HSIZE.Word, HBURST.Incr16, HTRANS.Seq, HWRITE.Write)],
                                    [(0x380, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Write),
                                     (0x384, HSIZE.Halfword, HBURST.Incr16, HTRANS.Seq, HWRITE.Write)],
                                    [(0x380, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Write),
                                     (0x384, HSIZE.Word, HBURST.Wrap16, HTRANS.Seq, HWRITE.Write)],
                                    [(0x380, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Write),
                                     (0x384, HSIZE.Word, HBURST.Incr16, HTRANS.Seq, HWRITE.Read)],
                                    [(0x380, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Write),
                                     (0x383, HSIZE.Word, HBURST.Incr, HTRANS.Seq, HWRITE.Read)],
                                    [(0x380, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Write),
                                     (0x380, HSIZE.Halfword, HBURST.Incr, HTRANS.Seq, HWRITE.Read)],
                                    [(0x380, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Write),
                                     (0x384, HSIZE.Word, HBURST.Wrap4, HTRANS.Seq, HWRITE.Write)],
                                    [(0x380, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Write),
                                     (0x384, HSIZE.Word, HBURST.Incr, HTRANS.Seq, HWRITE.Read)],

))
should_fail.generate_tests()

should_fail = TestFactory(test_incorrect_exclusive_transfers)
should_fail.add_option('length', (1024,))
should_fail.add_option('bus_width', (32,))
should_fail.add_option('sel', (HSEL.Sel, HSEL.NotSel))
should_fail.add_option('commands', ([(0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.Busy, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl),
                                     (0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
))
should_fail.generate_tests()

should_fail = TestFactory(test_incorrect_burst_and_exclusive_transfers)
should_fail.add_option('length', (1024,))
should_fail.add_option('bus_width', (32,))
should_fail.add_option('sel', (HSEL.Sel, HSEL.NotSel))
should_fail.add_option('commands', ([(0x3F4, HSIZE.Word, HBURST.Incr4, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3E4, HSIZE.Word, HBURST.Incr8, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3C4, HSIZE.Word, HBURST.Incr16, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3F4, HSIZE.Word, HBURST.Wrap4, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3E4, HSIZE.Word, HBURST.Wrap8, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3C4, HSIZE.Word, HBURST.Wrap16, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.Busy, HWRITE.Read, HEXCL.Excl)],
                                    [(0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl),
                                     (0x3C4, HSIZE.Word, HBURST.Incr, HTRANS.NonSeq, HWRITE.Read, HEXCL.Excl)],
))
should_fail.generate_tests()

test_ans = TestFactory(test_simple)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA), 0),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0x5500), 0),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000), 0),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0x55000000), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0), 0x55AA55AA)
    ],
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA), 0),
        ((0x1, HSIZE.Byte, HTRANS.Idle, HWRITE.Write, 0x5500), 0),
        ((0x2, HSIZE.Byte, HTRANS.Idle, HWRITE.Write, 0xAA0000), 0),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0x55000000), 0),
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Read, 0x0), 0x00AA),
        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Read, 0x0), 0x55000000)
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x12345678), 0),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xBB00), 0),
        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAACC0000), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0), 0xAACCBB78),
    ],
))
test_ans.generate_tests()

test_ans = TestFactory(test_write_strobe)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, 0), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, 0), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, 0), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, 0), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0),
    ],
    [
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, 3), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0x55AA),
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAA00, 2), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0xAAAA),
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55, 1), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0xAA55),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, 0xf), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0x55AA55AA),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0xAA55AA55, 0xA), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0xAAAAAAAA),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0xFF00FF, 0x5), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0xAAFFAAFF)
    ],
    [
        ((0x2, HSIZE.Halfword, HTRANS.Idle, HWRITE.Write, 0, 0xC), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0),
        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA0000, 0xC), 0),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, 0), 0x55AA0000),
        ((0x0, HSIZE.Halfword, HTRANS.Idle, HWRITE.Read, 0, 0), 0),
    ],
))
test_ans.generate_tests()

test_ans = TestFactory(test_secure_transfer)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('write_nonsec', (True,))
test_ans.add_option('read_nonsec', (True,))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAA, HRESP.Successful)),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAA, HRESP.Successful)),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAAAA, HRESP.Successful)),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAAAAAA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x55AA, HRESP.Successful)),

        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAAFF0000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAFF55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x55AA55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
    ],
))
test_ans.generate_tests(prefix="NonSecure_RW_allowed_")

test_ans = TestFactory(test_secure_transfer)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('write_nonsec', (False,))
test_ans.add_option('read_nonsec', (True,))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Successful)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAA, HRESP.Successful)),

        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAA, HRESP.Successful)),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAA, HRESP.Successful)),

        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAA, HRESP.Successful)),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAAAA, HRESP.Successful)),

        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAAAA, HRESP.Successful)),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAAAAAAA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x55AA, HRESP.Successful)),

        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAAFF0000, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x55AA, HRESP.Successful)),
        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAAFF0000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0xAAFF55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x55AA55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
    ],
))
test_ans.generate_tests(prefix="NonSecure_R_allowed_")

test_ans = TestFactory(test_secure_transfer)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('write_nonsec', (True,))
test_ans.add_option('read_nonsec', (False,))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAA, HRESP.Successful)),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAA, HRESP.Successful)),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAAAA, HRESP.Successful)),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAAAAAA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0x55AA, HRESP.Successful)),

        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAAFF0000, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0x0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAFF55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0x55AA55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
    ],
))
test_ans.generate_tests(prefix="NonSecure_W_allowed_")

test_ans = TestFactory(test_secure_transfer)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('write_nonsec', (False,))
test_ans.add_option('read_nonsec', (False,))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAA, HRESP.Successful)),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA00, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAA, HRESP.Successful)),
        ((0x2, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA0000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAAAA, HRESP.Successful)),
        ((0x3, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA000000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAAAAAAA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x0, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0x55AA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0x55AA, HRESP.Successful)),
        ((0x2, HSIZE.Halfword, HTRANS.NonSeq, HWRITE.Write, 0xAAFF0000, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0xAAFF55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Failed)),

        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0x55AA55AA, HRESP.Successful)),
    ],
    [
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Write, 0x55AA55AA, HNONSEC.NonSecure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Write, 0x55AA55AA, HNONSEC.Secure), (0, HRESP.Successful)),
        ((0x0, HSIZE.Word, HTRANS.Idle, HWRITE.Read, 0x0, HNONSEC.NonSecure), (0, HRESP.Successful)),
    ],
))
test_ans.generate_tests(prefix="NonSecure_not_allowed_")

test_ans = TestFactory(test_exclusive_transfer)
test_ans.add_option('length', (1024,))
test_ans.add_option('bus_width', (32,))
test_ans.add_option('sel', (HSEL.Sel, ))
test_ans.add_option('commands_answers', (
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.Excl), (0, HEXOKAY.Failed)),
    ],
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.NonExcl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Read, 0, HEXCL.Excl), (0xAA, HEXOKAY.Successful)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xBB, HEXCL.NonExcl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.Excl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HEXCL.NonExcl), (0xBB, HEXOKAY.Failed)),
    ],
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.NonExcl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Read, 0, HEXCL.Excl), (0xAA, HEXOKAY.Successful)),
        ((0x1, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xBB00, HEXCL.NonExcl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.Excl), (0, HEXOKAY.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HEXCL.NonExcl), (0xBBAA, HEXOKAY.Failed)),
    ],
    [
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.NonExcl), (0, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Read, 0, HEXCL.Excl), (0xAA, HEXOKAY.Successful)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Read, 0, HEXCL.NonExcl), (0xAA, HEXOKAY.Failed)),
        ((0x0, HSIZE.Byte, HTRANS.NonSeq, HWRITE.Write, 0xAA, HEXCL.Excl), (0, HEXOKAY.Successful)),
        ((0x0, HSIZE.Word, HTRANS.NonSeq, HWRITE.Read, 0x0, HEXCL.NonExcl), (0xAA, HEXOKAY.Failed)),
    ],
))
test_ans.generate_tests()

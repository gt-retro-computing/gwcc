from collections import defaultdict

from gwcc.backend.util import BackendError
from gwcc.exceptions import UnsupportedFeatureError
from .. import cfg
from .. import il
from ..abi.lc3 import LC3 as ABI
from ..optimization.dataflow import LivenessAnalysis


class ImmRange(object):
    def __init__(self, bits):
        self.max_value = 2 ** (bits - 1) - 1
        self.min_value = -(2 ** (bits - 1))

    def holds(self, value):
        return self.min_value <= value <= self.max_value


IMM5 = ImmRange(5)


class Relocation(object):
    def __init__(self, asm_idx, asm_len, gen_func, *gen_args):
        self.asm_idx = asm_idx
        self.asm_len = asm_len
        self.gen_func = gen_func
        self.gen_args = gen_args

    def __str__(self):
        return 'relocation<idx=%d len=%d func=%d, args=%s>' % (
            self.asm_idx, self.asm_idx, self.gen_func, self.gen_args)

    class Resolved(object):
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return 'r!' + self.name


class StackLocation(object):
    def __init__(self, bp_offset):
        assert type(bp_offset) == int
        self.bp_offset = bp_offset

    def __repr__(self):
        if self.bp_offset >= 0:
            return '@[bp-%xh]' % (self.bp_offset,)
        else:
            return '@[bp+%xh]' % (self.bp_offset,)

    def __eq__(self, other):
        return type(other) == StackLocation and other.bp_offset == self.bp_offset

    def __hash__(self):
        return hash((1, self.bp_offset))


class RegisterLocation(object):
    def __init__(self, reg):
        assert type(reg) == str
        self.reg = reg

    def __repr__(self):
        return '@%s' % (self.reg,)

    def __eq__(self, other):
        return type(other) == RegisterLocation and other.reg == self.reg

    def __hash__(self):
        return hash((2, self.reg))


class MemoryLocation(object):
    def __init__(self, name):
        assert type(name) == str
        self.name = name

    def __repr__(self):
        return repr(self.name)

    def __eq__(self, other):
        return type(other) == MemoryLocation and other.var == self.name

    def __hash__(self):
        return hash((3, self.name))


class RegisterAllocator(object):
    register_set = ['r0', 'r1', 'r2', 'r3', 'r4', 'r7']

    def __init__(self, spill_callback):
        self.spill_callback = spill_callback

        # all registers is available to us except bp and sp.
        self.register_desc = {}  # maps from registers to what temps it stores.
        for reg in self.register_set:
            self.register_desc[reg] = set()

        self.address_desc = defaultdict(set)  # maps from temps to where it is stored (reg or mcem).

        self.stack_slots = [1] # reserve a slot for saved bp, because bp points to saved bp

    @property
    def cur_bp_offset(self):
        return len(self.stack_slots)

    def alloc_stack(self, local):
        assert type(local) == il.Variable
        size = ABI.sizeof(local.type)
        for i in range(len(self.stack_slots) + 1 - size):
            for j in range(size):
                if self.stack_slots[i + j] != 0:
                    break
            else:
                slot_index = i
                break
        else:
            slot_index = len(self.stack_slots)
            self.stack_slots.extend([0] * size)

        stack_loc = StackLocation(slot_index)
        self.address_desc[local].add(stack_loc)
        for j in range(size):
            self.stack_slots[slot_index + j] += 1
        print '%s is now at %s' % (local, stack_loc)
        return stack_loc

    def free_stack(self, stack_address, size):
        if stack_address < 0:  # don't free params
            return
        print 'freeing %d stack slots at %d' % (size, stack_address)
        for j in range(size):
            self.stack_slots[stack_address + j] -= 1
        while self.stack_slots and self.stack_slots[-1] == 0:
            self.stack_slots = self.stack_slots[:-1]
            print 'stack spill heap has shrunken'

    def free_local(self, local, free_stack=True):
        print 'local %s is now dead' % (local,)
        size = ABI.sizeof(local.type)
        to_remove = set()
        for location in self.address_desc[local]:
            if type(location) == StackLocation:
                if not free_stack:
                    free_stack = True
                else:
                    stack_address = location.bp_offset
                    self.free_stack(stack_address, size)
            elif type(location) == RegisterLocation:
                # if type(location) == RegisterLocation:
                self.register_desc[location.reg].remove(local)
                print 'reg %s is no longer storing %s' % (location.reg, local)
                to_remove.add(location)
        # del self.address_desc[local]
        self.address_desc[local].difference_update(to_remove)

    def free_local_reg(self, local, reg):
        self.register_desc[reg].remove(local)
        self.address_desc[local].remove(RegisterLocation(reg))

    def spill_reg(self, reg):
        """
        Free up a register by spilling all locals currently stored in it to the stack.
        :param reg: register to spill
        :return: spill destination that the register's old contents must be copied to
        """
        assert reg in self.register_set

        if not self.register_desc[reg]:
            raise RuntimeError('attempting to spill empty register ' + reg)

        first_local = next(iter(self.register_desc[reg]))
        spill_dst = self.alloc_stack(first_local)
        size = ABI.sizeof(first_local)
        # spill all locals stored in this register, if they have not been spilled already.
        for local in self.register_desc[reg]:
            self.address_desc[local].remove(RegisterLocation(reg))
            if not self.has_been_spilled(local):
                assert size == ABI.sizeof(local)
                self.address_desc[local].add(spill_dst)

        # this register is now free
        self.register_desc[reg].clear()

        return spill_dst

    def has_been_spilled(self, local):
        return any(map(lambda location: type(location) == StackLocation, self.address_desc[local]))

    def get_loc(self, local):
        # prefer register
        for location in self.address_desc[local]:
            if type(location) == RegisterLocation:
                return location
        for location in self.address_desc[local]:
            if type(location) == StackLocation:
                return location
        for location in self.address_desc[local]:
            return location
        raise RuntimeError('local %s has not been scheduled' % (local,))

    def getreg(self, live_out, src_local, no_spill):
        """
        Register allocator
        :param live_out: statement-level live-out sets
        :param src_local: local whose register we will prefer to overwrite
        :param no_spill: registers to not spill
        :return: new available register
        """
        # 1. if the name B is in a register that holds the value of no other names,
        # and B is not live out of the statement, then return that register B for L.
        if src_local:
            src_regs = filter(lambda add_desc: type(add_desc) == RegisterLocation, self.address_desc[src_local])
            for src_reg in src_regs:
                if len(self.register_desc[src_reg.reg]) == 1:
                    assert next(iter(self.register_desc[src_reg.reg])) == src_local
                    if src_local not in live_out:
                        return src_reg.reg

        # 2. failing (1), return an empty register for L if there is one.
        for reg in self.register_set:
            if reg not in no_spill:
                if not self.register_desc[reg]:
                    return reg

        # 3. failing (2), spill some other register variable to memory to make room.
        # prefer register where, for all temporaries currently stored in the register, have been spilled already
        for reg in self.register_set:
            if reg not in no_spill:
                if all(map(self.has_been_spilled, self.register_desc[reg])):
                    print 'spilling %s, but no copy is required.' % (reg,)
                    for local in self.register_desc[reg]:
                        self.address_desc[local].remove(RegisterLocation(reg))
                    self.register_desc[reg].clear()
                    return reg

        # ok, we have to emit a spill copy. but still, avoid spilling src_var.
        for reg in self.register_set:
            if reg not in no_spill:
                if self.register_desc[reg]:
                    spill_dst = self.spill_reg(reg)
                    print 'spilling contents of %s to %s' % (reg, spill_dst)
                    self.spill_callback(spill_dst, reg)
                    return reg

        raise RuntimeError("couldn't allocate register")

    def store_reg(self, reg, local):
        """
        Updates metadata to reflect that 'local' is stored in 'reg'.
        """
        assert type(reg) == RegisterLocation
        assert type(local) == il.Variable
        self.address_desc[local].add(reg)
        self.register_desc[reg.reg].add(local)
        print '%s is now stored in %s' % (local, reg.reg)

    def add_global(self, global_name, memory_loc):
        assert type(global_name) == il.GlobalName
        assert type(memory_loc) == MemoryLocation
        if type(global_name.value) == il.Variable:
            self.address_desc[global_name.value].add(memory_loc)
        elif type(global_name.value) == il.Function:
            pass
        else:
            print global_name.value
            assert False


class LC3(object):
    """
    --- The LC3 GANGWEED C BINARY ABI ---
    Basically, imagine you're on a __stdcall compiler in 16 bits.

    For word-size arguments:
        Return value in r0.
        Registers pushed on the stack right-to-left.
    For larger-than-word-size aruguments:
        Passed as pointer to the stack using protocol described above.

    r5 is the frame pointer and r6 is the stack pointer. Stack cleanup is callee.
    r1, r2, r3, r4, r5, and r6 are all callee-saved registers.
    r0 is not saved because it holds the return value.
    r7 is not saved because it holds the return address.

    Stack starts at 0xEFFF and grows toward lower addresses.
    """

    bp = 'r5'  # basepointer basepointer basepointer basepointer
    sp = 'r6'  # stack pointer
    rp = 'r7'  # return pointer
    retval_reg = 'r0'

    def __init__(self, names, with_symbols=True):
        assert all(map(lambda e: type(e) == il.GlobalName, names))

        # input
        self.enable_symbols = with_symbols
        self._global_names = names
        self._global_vars = {glob.value: glob for glob in self._global_names if type(glob.value) == il.Variable}

        # state
        self._mappings = {}  # where all the global vars are gettin allocated
        self._deferred_relocations = []
        self._cur_binary_loc = None
        self._cur_orig = None
        self._label_cache = {}
        self._cur_sp = None

        # output
        self._compiled = False
        self._asm = []

    def get_output(self):
        if not self._compiled:
            raise RuntimeError('input has not been compiled')
        return self._asm

    def mangle_globalname(self, global_name):
        if global_name.linkage == 'C':
            return self.mangle_name_c(global_name.name)
        elif global_name.linkage == 'asm':
            return global_name.name
        else:
            raise BackendError('unsupported linkage declaration ' + global_name.linkage)

    def mangle_name_c(self, name):
        if name in self._label_cache:
            return self._label_cache[name]

        result = '_' + str(len(self._label_cache)) + '_' + name
        self._label_cache[name] = result
        return result

    def name_basic_block(self, fn, bb):
        return self.mangle_name_c(fn.name + '_' + bb.name)

    def name_return_block(self, fn):
        return self.mangle_name_c(fn.name + '_return')

    def place_relocation(self, name):
        self.emit_newline()
        self.emit_comment('------- symbol: %s' % (name,) + ' --------')
        self._mappings[name] = self._cur_binary_loc

    def is_name_mapped(self, name):
        return name in self._mappings

    def get_binary_location(self, name):
        return self._mappings[name]

    def make_reloc(self, gen_func, *args):
        asm_idx_start = len(self._asm)
        unwrapped_args = list(args)
        for i in range(len(unwrapped_args)):
            if type(unwrapped_args[i]) == Relocation.Resolved:
                unwrapped_args[i] = 0
        gen_func(*unwrapped_args)
        asm_idx_end = len(self._asm)
        reloc = Relocation(asm_idx_start, asm_idx_end - asm_idx_start, gen_func, *args)
        self._deferred_relocations.append(reloc)

    def _apply_reloc(self, reloc):
        asm_bak = self._asm
        cur_binary_loc_bak = self._cur_binary_loc
        self._asm = []

        gen_args = list(reloc.gen_args)
        for i in range(len(gen_args)):
            if type(gen_args[i]) == Relocation.Resolved:
                gen_args[i] = self._mappings[gen_args[i].name]
        reloc.gen_func(*gen_args)
        if len(self._asm) != reloc.asm_len:
            raise RuntimeError('Relocation asm changed length! Was: %d , now is: %d' % (reloc.asm_len, len(self._asm)))

        asm_bak[reloc.asm_idx:reloc.asm_idx + reloc.asm_len] = self._asm
        self._asm = asm_bak
        self._cur_binary_loc = cur_binary_loc_bak

    def apply_relocations(self):
        for reloc in self._deferred_relocations:
            self._apply_reloc(reloc)

    def _emit_line(self, line, binary_len):
        line += (' ' * max(0, 40 - len(line))) + '; loc=%02x' % (self._cur_binary_loc,)
        self._asm.append(line)
        self._cur_binary_loc += binary_len

    def emit_newline(self):
        if self.enable_symbols:
            self._asm.append('')

    def emit_comment(self, line):
        if self.enable_symbols:
            self._asm.append('; ' + line)

    def emit_insn(self, insn):
        self._emit_line(insn, 1)

    def emit_orig(self, to):
        self._emit_line('.orig x%x' % (to,), 0)

    def emit_section_end(self):
        self._emit_line('.end', 0)

    def emit_label(self, name):
        self._emit_line(name, 0)

    def emit_fill(self, value, name=''):
        if name:
            self._emit_line('%s .fill x%x' % (name, value), 1)
        else:
            self._emit_line('.fill x%x' % (value,), 1)

    def emit_blkw(self, name, size):
        self._emit_line('%s .blkw %d' % (name, size), size)

    def cl_zero_reg(self, reg):
        """
        Zero a register using a constant length of code.
        """
        self.emit_insn('AND %s, %s, #0' % (reg, reg))

    def cl_ones(self, reg):
        self.emit_insn('NOT %s, %s' % (reg, reg))

    def cl_twos(self, reg):
        self.cl_ones(reg)
        self.emit_insn('add %s, %s, #1' % (reg, reg))

    def cl_logical_not(self, reg):
        self.cl_ones(reg)
        self.emit_insn('AND %s, %s, #1' % (reg, reg))

    def cl_push(self, src_reg):
        self.emit_comment('push ' + src_reg)
        self.emit_insn('add %s, %s, #-1' % (self.sp, self.sp))
        self.emit_insn('STR %s, %s, #0' % (src_reg, self.sp))

    def cl_pop(self, dst_reg):
        self.emit_comment('pop ' + dst_reg)
        self.emit_insn('LDR %s, %s, #0' % (dst_reg, self.sp))
        self.emit_insn('add %s, %s, #1' % (self.sp, self.sp))

    def cl_move(self, dst_reg, src_reg):
        self.emit_comment('mov ' + dst_reg + ', ' + src_reg)
        self.emit_insn('add %s, %s, #0' % (dst_reg, src_reg))

    def cl_sub(self, dst_reg, src_reg):
        # self.emit_comment('sub ' + dst_reg + ', ' + src_reg)
        self.cl_twos(src_reg)
        self.emit_insn('add %s, %s, %s' % (dst_reg, dst_reg, src_reg))
        self.cl_twos(src_reg)

    def cl_test(self, src_reg):
        self.emit_insn('add %s, %s, #0' % (src_reg, src_reg))

    def cl_nand(self, dst_reg, srcA, srcB):
        self.emit_insn('AND %s, %s, %s' % (dst_reg, srcA, srcB))
        self.cl_ones(dst_reg)

    def cl_or(self, dst_reg, src_reg):
        self.emit_comment('or ' + dst_reg + ', ' + src_reg)
        self.cl_ones(dst_reg)
        self.cl_ones(src_reg)
        self.cl_nand(dst_reg, dst_reg, src_reg)
        self.cl_ones(src_reg)

    def cl_load_reg(self, reg, value):
        if IMM5.holds(value):
            self.emit_comment('load short: %s <- %d (0x%02x)' % (reg, value, value))
            self.cl_zero_reg(reg)
            if value != 0:
                self.emit_insn('add %s, %s, #%d' % (reg, reg, value))
        else:
            self.emit_comment('load long: %s <- %d (0x%02x)' % (reg, value, value))
            self.emit_insn('LD %s, #1' % (reg,))
            self.emit_insn('BR #1')
            self.emit_fill(value)

    def cl_load_reg_funny(self, reg, value):
        """
        Set a register to a 16-bit value using a constant length of code.
        """
        self.emit_comment('load: %s <- %d (0x%02x)' % (reg, value, value))
        self.cl_zero_reg(reg)
        value %= 0x10000
        for bit in range(15, -1, -1):
            self.emit_insn('add %s, %s, %s' % (reg, reg, reg))
            self.emit_insn('add %s, %s, #%d' % (reg, reg, (value >> bit) & 1))

    def cl_eq(self, dst_reg, src_reg):
        self.cl_sub(dst_reg, src_reg)
        self.cl_test(dst_reg)
        self.emit_insn('BRz #2')  # branch to TRUE
        self.cl_zero_reg(dst_reg)
        self.emit_insn('BR #2')  # branch over TRUE
        self.cl_zero_reg(dst_reg)
        self.emit_insn('ADD %s, %s, #1' % (dst_reg, dst_reg))

    def cl_lt_unsigned(self, dst_reg, src_reg):  # dst_reg = dst_reg < src_reg
        self.cl_test(dst_reg)
        self.emit_insn('BRn #3')  # branch to A_NEGATIVE
        self.cl_test(src_reg)  # A_NONNEGATIVE
        self.emit_insn('BRn #12')  # if b negative, branch to TRUE
        self.emit_insn('BR #2')  # jump to COMPARE
        self.cl_test(src_reg)  # A_NEGATIVE
        self.emit_insn('BRzp #9')  # if b non-negative, branch to FALSE
        self.cl_sub(dst_reg, src_reg)  # COMPARE: (THIS IS 5 INSTRUCTIONS.)
        self.cl_test(dst_reg)
        self.emit_insn('BRn #2')  # branch to TRUE
        self.cl_zero_reg(dst_reg)  # FALSE:
        self.emit_insn('BR #2')  # jump to END:
        self.cl_zero_reg(dst_reg)  # TRUE:
        self.emit_insn('add %s, %s, #1' % (dst_reg, dst_reg))

    def cl_lt_signed(self, dst_reg, src_reg):  # dst_reg = dst_reg < src_reg
        self.cl_test(dst_reg)
        self.emit_insn('BRn #3')  # branch to A_NEGATIVE
        self.cl_test(src_reg)  # A_NONNEGATIVE
        self.emit_insn('BRn #10')  # branch to FALSE
        self.emit_insn('BR #2')  # jump to COMPARE
        self.cl_test(src_reg)  # A_NEGATIVE
        self.emit_insn('BRzp #9')  # if b non-negative, branch to TRUE
        self.cl_sub(dst_reg, src_reg)  # COMPARE: (THIS IS 5 INSTRUCTIONS.)
        self.cl_test(dst_reg)
        self.emit_insn('BRn #2')  # branch to TRUE
        self.cl_zero_reg(dst_reg)  # FALSE:
        self.emit_insn('BR #2')  # jump to END:
        self.cl_zero_reg(dst_reg)  # TRUE:
        self.emit_insn('add %s, %s, #1' % (dst_reg, dst_reg))
        # END:

    def reloc_load_address(self, reg, name):
        if self.is_name_mapped(name):
            self.emit_comment('load: ' + name)
            self.cl_load_reg(reg, self.get_binary_location(name))
        else:
            self.emit_comment('relocated load: %s <- %s' % (reg, name))
            self.make_reloc(self.cl_load_reg, reg, Relocation.Resolved(name))

    def reloc_dump_address(self, name, asm_label=''):
        if self.is_name_mapped(name):
            self.emit_comment('address: ' + name)
            self.emit_fill(self.get_binary_location(name), asm_label)
        else:
            self.emit_comment('relocated address: ' + name)
            self.make_reloc(self.emit_fill, Relocation.Resolved(name), asm_label)

    def emit_stub(self):
        """
        Emits a compiler-generated stub to setup the stack and shit
        """
        self.cl_load_reg(LC3.bp, 0xbfff)
        self.cl_move(LC3.sp, LC3.bp)
        self.emit_insn('LD %s, #2' % (self.rp,))
        self.emit_insn('JSRR %s' % (self.rp,))
        self.emit_insn('HALT')
        self.reloc_dump_address('main')

    def emit_global_variable(self, glob):
        self.place_relocation(glob.name)

        var = glob.value
        init = glob.init
        asm_name = self.mangle_globalname(glob)

        if init:
            if init.type == il.CompiledValueType.Integer:
                self.emit_fill(init.value, asm_name)
            elif init.type == il.CompiledValueType.WordArray:
                self.emit_fill(init.value[0], asm_name)
                for i in range(1, len(init.value)):
                    self.emit_fill(init.value[i])
            elif init.type == il.CompiledValueType.Pointer:
                self.reloc_dump_address(init.value, asm_name)
            else:
                raise RuntimeError('type %s not supported by this backend' % (init.type,))
        else:
            self.emit_blkw(asm_name, 1)

    def vl_shift_bp(self, bp_offset, callback):
        bp_delta = 0  # how much the bp moved, so how much we have to unshift it by
        while bp_offset < -32:
            self.emit_insn('add %s, %s, #-16' % (self.bp, self.bp))
            bp_offset -= -16
            bp_delta -= 16
        while bp_offset > 31:
            self.emit_insn('add %s, %s, #15' % (self.bp, self.bp))
            bp_offset -= 15
            bp_delta += 15

        callback(bp_offset)

        # move bp back
        while bp_delta > 16:
            self.emit_insn('add %s, %s, #-16' % (self.bp, self.bp))
            bp_delta -= 16
        while bp_delta < -15:
            self.emit_insn('add %s, %s, #15' % (self.bp, self.bp))
            bp_delta += 15
        if bp_delta:
            self.emit_insn('add %s, %s, #-%d' % (self.bp, self.bp, bp_delta))

    def vl_load_local(self, dst_reg, bp_offset):
        self.emit_comment('mov %s, [bp-%d]' % (dst_reg, bp_offset))
        self.vl_shift_bp(bp_offset, lambda offset: self.emit_insn('LDR %s, %s, #%d' % (dst_reg, self.bp, -offset)))

    def vl_store_local(self, src_reg, bp_offset):
        self.emit_comment('mov [bp-%d], %s' % (bp_offset, src_reg))
        self.vl_shift_bp(bp_offset, lambda offset: self.emit_insn('STR %s, %s, #%d' % (src_reg, self.bp, -offset)))

    def spill_callback(self, spill_loc, src_reg):
        self.vl_store_local(src_reg, spill_loc.bp_offset)
        if self._cur_sp != spill_loc.bp_offset:
            self.emit_insn('ADD %s, %s, #%d' % (self.sp, self.sp, self._cur_sp - spill_loc.bp_offset))
            self._cur_sp = spill_loc.bp_offset

    def emit_function(self, glob):
        self.place_relocation(glob.name)

        asm_name = self.mangle_globalname(glob)
        self.emit_label(asm_name)

        func = glob.value

        # print func.pretty_print()
        # with open('tmp_cfg_func_%s.dot' % func.name, 'w') as f:
        #     func.dump_graph(fd=f)
        def liveness_set_to_str(live):
            return '(' + ', '.join(map(lambda v: v.name, live)) + ')'

        spill_callback = self.spill_callback
        reg_alloc = RegisterAllocator(spill_callback)

        for global_name in self._global_names:
            reg_alloc.add_global(global_name, MemoryLocation(global_name.name))

        for i, param in enumerate(func.params):
            reg_alloc.address_desc[param].add(StackLocation(-i - 8))

        for local in func.locals:
            if local not in func.params:
                reg_alloc.alloc_stack(local)

        # function prologue
        self.emit_func_prologue(reg_alloc.cur_bp_offset)
        self._cur_sp = reg_alloc.cur_bp_offset

        # linearize the cfg
        blocks = cfg.topoorder(func.cfg)

        # let's cop liveness
        liveness = LivenessAnalysis(func).compute_liveness()

        # debug print the statement liveness
        fd = open('tmp_liveness_debug.dot', 'w')
        print >> fd, "digraph \"%s\" {" % ('CFG',)
        for bb in blocks:
            stmt_liveness = [set() for _ in range(len(bb.stmts))]
            stmt_liveness[-1].update(liveness.live_out(bb))
            for i in range(len(bb.stmts) - 1, 0, -1):
                stmt = bb.stmts[i]
                stmt_liveness[i - 1].update(stmt_liveness[i])
                stmt_liveness[i - 1].discard(il.defed_var(stmt))
                stmt_liveness[i - 1].update(il.used_vars(stmt))
                if type(stmt) == il.ReturnStmt:
                    stmt_liveness[i - 1].add(func.retval)
            label = "== Block %s ==" % bb.name + '\\l'
            label += 'LIVE IN: ' + liveness_set_to_str(liveness.live_in(bb)) + '\\l'
            for i in range(len(bb.stmts)):
                label += str(bb.stmts[i]) + '\\l'
                # label += '    ' + liveness_set_to_str(stmt_liveness[i]) + '\\l'
            label += 'LIVE OUT: ' + liveness_set_to_str(liveness.live_out(bb)) + '\\l'
            print >> fd, "    %s [shape=box, label=\"%s\"]" % (bb.name, label)
        for bb in func.cfg.basic_blocks:
            for edge in func.cfg.get_edges(bb):
                print >> fd, "%s -> %s;" % (edge.src, edge.dst)
        print >> fd, "}\n"
        fd.close()

        for bb in cfg.topoorder(func.cfg):
            self.emit_basic_block(bb, func, liveness, reg_alloc)

        self.place_relocation(self.name_return_block(func))
        self.emit_func_epilogue()

    def emit_basic_block(self, bb, func, liveness, reg_alloc):
        print '\nemitting ' + str(bb)
        # place this block's label
        self.place_relocation(self.name_basic_block(func, bb))

        def liveness_set_to_str(live):
            return '(' + ', '.join(map(lambda v: v.name, live)) + ')'

        # statement-level live-out sets
        stmt_liveness = [set() for _ in range(len(bb.stmts))]
        stmt_liveness[-1].update(liveness.live_out(bb))
        for i in range(len(bb.stmts) - 1, 0, -1):
            stmt = bb.stmts[i]
            stmt_liveness[i - 1].update(stmt_liveness[i])
            stmt_liveness[i - 1].discard(il.defed_var(stmt))
            stmt_liveness[i - 1].update(il.used_vars(stmt))
            if type(stmt) == il.ReturnStmt:
                stmt_liveness[i - 1].add(func.retval)

        def load_reg_from_loc(dst_reg, src_loc):
            print 'loading %s from %s' % (dst_reg, src_loc)
            if type(src_loc) == StackLocation:
                self.vl_load_local(dst_reg, src_loc.bp_offset)
            elif type(src_loc) == RegisterLocation:
                if dst_reg != src_loc.reg:
                    self.cl_move(dst_reg, src_loc.reg)
            elif type(src_loc) == MemoryLocation:
                self.reloc_load_address(dst_reg, src_loc.name)
                self.emit_insn('LDR %s, %s, #0' % (dst_reg, dst_reg))
            else:
                assert False

        for i, stmt in enumerate(bb.stmts):
            live_out = stmt_liveness[i]
            print '\nSCHEDULING ' + str(stmt)
            print 'Live out: ' + liveness_set_to_str(live_out)
            self.emit_comment(str(stmt))

            # Register scheduling
            dst_local = il.defed_var(stmt)
            src_locals = il.used_vars(stmt)

            if dst_local or src_locals:
                if len(src_locals) > 0:
                    b_local = src_locals[0]
                    dst_reg = reg_alloc.getreg(live_out, b_local, [])
                    b_loc = reg_alloc.get_loc(b_local)
                    load_reg_from_loc(dst_reg, b_loc)
                    if b_local not in live_out:
                        reg_alloc.free_local(b_local, free_stack=b_local not in func.locals)
                else:
                    dst_reg = reg_alloc.getreg(live_out, None, [])
                if dst_local in live_out:
                    reg_alloc.store_reg(RegisterLocation(dst_reg), dst_local)
            else:
                dst_reg = None

            if len(src_locals) > 1:
                c_local = src_locals[1]
                c_loc = reg_alloc.get_loc(c_local)
                c_reg = reg_alloc.getreg(live_out, None, [dst_reg])
                load_reg_from_loc(c_reg, c_loc)
                if c_local in live_out:
                    reg_alloc.store_reg(RegisterLocation(c_reg), c_local)
                else:
                    reg_alloc.free_local(c_local, free_stack=c_local not in func.locals)
            else:
                c_reg = None

            print 'dst = %s, operand = %s' % (dst_reg, c_reg if c_reg else 'None')
            self.emit_comment('    dst = %s, operand = %s' % (dst_reg, c_reg if c_reg else 'None'))

            typ = type(stmt)
            if typ == il.BinaryStmt:
                dst_local = reg_alloc
                if stmt.op == il.BinaryOp.Add:
                    self.emit_insn("add %s, %s, %s" % (dst_reg, dst_reg, c_reg))
                elif stmt.op == il.BinaryOp.Sub:
                    self.cl_sub(dst_reg, c_reg)
                elif stmt.op == il.BinaryOp.And:
                    self.emit_insn("AND %s, %s, %s" % (dst_reg, dst_reg, c_reg))
                elif stmt.op == il.BinaryOp.Or:
                    self.cl_or(dst_reg, c_reg)
                elif stmt.op == il.BinaryOp.Xor:
                    tmp_reg = reg_alloc.getreg(live_out, None, [dst_reg, c_reg])
                    self.cl_or(dst_reg, c_reg)
                    self.cl_nand(tmp_reg, dst_reg, c_reg)
                    self.emit_insn("AND %s, %s, %s" % (dst_reg, dst_reg, tmp_reg))
                elif stmt.op == il.BinaryOp.Lt:
                    if il.Types.is_unsigned(stmt.srcA.type):
                        self.cl_lt_unsigned(dst_reg, c_reg)
                    else:
                        self.cl_lt_signed(dst_reg, c_reg)
                elif stmt.op == il.BinaryOp.Gt:
                    tmp_reg = reg_alloc.getreg(live_out, None, [dst_reg, c_reg])
                    print 'tmpreg = ' + tmp_reg
                    self.cl_move(tmp_reg, dst_reg)
                    if il.Types.is_unsigned(stmt.srcA.type):
                        self.cl_lt_unsigned(dst_reg, c_reg)
                    else:
                        self.cl_lt_signed(dst_reg, c_reg)
                    self.cl_logical_not(dst_reg)
                    self.cl_sub(tmp_reg, c_reg)
                    self.cl_test(tmp_reg)
                    self.emit_insn('BRnp #1')
                    self.cl_zero_reg(dst_reg)
                elif stmt.op == il.BinaryOp.LogicalAnd:
                    self.cl_test(dst_reg)
                    self.emit_insn('BRz #5')  # branch to FALSE
                    self.cl_test(c_reg)
                    self.emit_insn('BRz #3')
                    self.cl_zero_reg(dst_reg)  # TRUE
                    self.emit_insn('ADD %s, %s, #1' % (dst_reg, dst_reg))
                    self.emit_insn('BR #1')
                    self.cl_zero_reg(dst_reg)  # FALSE
                elif stmt.op == il.BinaryOp.LogicalOr:
                    self.cl_test(dst_reg)
                    self.emit_insn('BRnp #2')  # branch to TRUE
                    self.cl_test(c_reg)
                    self.emit_insn('BRz #3')  # branch to FALSE
                    self.cl_zero_reg(dst_reg)  # TRUE
                    self.emit_insn('ADD %s, %s, #1' % (dst_reg, dst_reg))
                    self.emit_insn('BR #1')
                    self.cl_zero_reg(dst_reg)  # FALSE
                elif stmt.op == il.BinaryOp.Equ:
                    self.cl_eq(dst_reg, c_reg)
                elif stmt.op == il.BinaryOp.Neq:
                    self.cl_eq(dst_reg, c_reg)
                    self.cl_logical_not(dst_reg)
                elif stmt.op == il.BinaryOp.Mul:
                    tmp_mask = reg_alloc.getreg(live_out, None, [dst_reg, c_reg])
                    tmp_multiplicand = reg_alloc.getreg(live_out, None, [dst_reg, c_reg, tmp_mask])
                    self.cl_move(tmp_multiplicand, dst_reg)
                    self.cl_zero_reg(dst_reg)
                    self.cl_push(c_reg) # save operand value
                    self.cl_zero_reg(tmp_mask)
                    self.emit_insn('ADD %s, %s, #1' % (tmp_mask, tmp_mask))

                    for bit in range(0,16):
                        self.cl_push(tmp_mask) # save mask value
                        self.emit_insn('AND %s, %s, %s' % (tmp_mask, tmp_mask, tmp_multiplicand))
                        self.cl_twos(tmp_mask)
                        self.emit_insn('AND %s, %s, %s' % (tmp_mask, tmp_mask, c_reg)) # mask addend if 0
                        self.emit_insn('ADD %s, %s, %s' % (dst_reg, dst_reg, tmp_mask)) # add
                        self.cl_pop(tmp_mask) # restore mask

                        # shift left
                        self.emit_insn('ADD %s, %s, %s' % (tmp_mask, tmp_mask, tmp_mask))
                        self.emit_insn('ADD %s, %s, %s' % (c_reg, c_reg, c_reg))

                    self.cl_pop(c_reg)
                else:
                    raise UnsupportedFeatureError('unsupported binary operation ' + str(stmt.op))
            elif typ == il.UnaryStmt:
                if stmt.op == il.UnaryOp.Identity:  # this is a MOVE!!!!!
                    if dst_local in live_out and stmt.src not in func.locals:
                        reg_alloc.store_reg(RegisterLocation(dst_reg), stmt.src)  # THIS MOVE HAS SPECIAL SEMANTIC
                elif stmt.op == il.UnaryOp.Minus:
                    self.cl_twos(dst_reg)
                elif stmt.op == il.UnaryOp.Negate:
                    self.cl_ones(dst_reg)
                elif stmt.op == il.UnaryOp.LogicalNot:
                    self.cl_test(dst_reg)
                    self.emit_insn('BRnp #3')
                    self.emit_insn('AND %s, %s, #0' % (dst_reg, dst_reg))
                    self.emit_insn('ADD %s, %s, #1' % (dst_reg, dst_reg))
                    self.emit_insn('BRnzp #1')
                    self.emit_insn('AND %s, %s, #0' % (dst_reg, dst_reg))
                else:
                    raise UnsupportedFeatureError('unsupported unary operation ' + str(stmt.op))
            elif typ == il.ConstantStmt:
                if stmt.imm.value.type == il.CompiledValueType.Integer:
                    self.cl_load_reg(dst_reg, stmt.imm.value.value)
                elif stmt.imm.value.type == il.CompiledValueType.Pointer:
                    self.emit_insn('LD %s, #1' % (dst_reg,))
                    self.emit_insn('BR #1')
                    self.reloc_dump_address(stmt.imm.value.value)
                else:
                    raise RuntimeError('unsupported compiled constant type')

            elif typ == il.ReturnStmt:
                retvar_loc = reg_alloc.get_loc(func.retval)
                load_reg_from_loc(self.retval_reg, retvar_loc)
                tmp_reg = reg_alloc.getreg(live_out, None, [self.retval_reg])
                self.emit_insn('LD %s, #1' % (tmp_reg,))
                self.emit_insn('JMP %s' % (tmp_reg,))
                self.reloc_dump_address(self.name_return_block(func))
                reg_alloc.free_local(func.retval)
            elif typ == il.GotoStmt:
                tmp_reg = reg_alloc.getreg(live_out, None, [])
                self.emit_insn('LD %s, #1' % (tmp_reg,))
                self.emit_insn('JMP %s' % (tmp_reg,))
                dst_label = self.name_basic_block(func, stmt.dst_block)
                self.reloc_dump_address(dst_label)
            elif typ == il.CondJumpStmt:
                if stmt.imm.value.value != 0:
                    raise RuntimeError('unsupported (nonzero) comparison constant ' + str(stmt.imm.value.value))

                # set cc flags
                self.cl_test(dst_reg)

                # load destination pc-relative after the two jumps
                # layout:
                # CMP
                # BR #3
                # LD tmp, #1
                # JMP false
                # false_addr
                # LD tmp, #1
                # JMP true
                # true_addr
                tmp_reg = reg_alloc.getreg(live_out, None, [dst_reg])

                # true branch insn
                if stmt.op == il.ComparisonOp.Equ:
                    self.emit_insn('BRz #3')
                elif stmt.op == il.ComparisonOp.Neq:
                    self.emit_insn('BRnp #3')
                else:
                    raise UnsupportedFeatureError('unsupported comparison operator ' + str(stmt.op))

                # false branch load and jump
                self.emit_insn('LD %s, #1' % (tmp_reg,))
                self.emit_insn('JMP %s' % (tmp_reg,))
                false_label = self.name_basic_block(func, stmt.false_block)
                self.reloc_dump_address(false_label)

                # true branch load and jump
                self.emit_insn('LD %s, #1' % (tmp_reg,))
                self.emit_insn('JMP %s' % (tmp_reg,))
                true_label = self.name_basic_block(func, stmt.true_block)
                self.reloc_dump_address(true_label)
            elif typ == il.CastStmt:
                from_type = stmt.src.type
                to_type = stmt.dst.type
                if ABI.sizeof(from_type) == ABI.sizeof(to_type):
                    pass
                else:
                    raise UnsupportedFeatureError('unsupported cast %s to %s' % (from_type, to_type))
            elif typ == il.DerefReadStmt:
                self.emit_insn('LDR %s, %s, #0' % (dst_reg, dst_reg))
            elif typ == il.DerefWriteStmt:
                self.emit_insn('STR %s, %s, #0' % (c_reg, dst_reg))
            elif typ == il.CommentStmt:
                pass
            elif typ == il.ParamStmt:
                self.cl_push(dst_reg)
            elif typ == il.CallStmt:
                self.emit_insn('JSRR %s' % (dst_reg,))
                self.cl_pop(dst_reg)
                # pop args
                for i in range(stmt.nargs):
                    self.emit_insn('add %s, %s, #1' % (self.sp, self.sp))
            else:
                raise UnsupportedFeatureError('unsupported statement ' + str(stmt))

            if dst_local in func.locals and dst_local in live_out:
                print 'spilling %s back to stack' % (str(dst_local),)
                reg_alloc.free_local_reg(dst_local, dst_reg)
                self.vl_store_local(dst_reg, reg_alloc.get_loc(dst_local).bp_offset)

            if c_reg and c_local in self._global_vars:
                reg_alloc.free_local(c_local)

            if dst_local in self._global_vars:
                print 'writing %s back to global' % (str(dst_local),)
                tmp_reg = reg_alloc.getreg(live_out, None, [dst_reg, c_reg])
                reg_alloc.free_local(dst_local)
                self.emit_insn('LD %s, #2' % (tmp_reg,))
                self.emit_insn('STR %s, %s, #0' % (dst_reg, tmp_reg))
                self.emit_insn('BR #1')
                self.reloc_dump_address(self.mangle_globalname(self._global_vars[dst_local]))
            self.emit_newline()

    def emit_func_prologue(self, locals_size):
        self.emit_insn('add %s, %s, #-1' % (self.sp, self.sp))  # save space for ret val
        self.cl_push(self.rp)
        self.cl_push(self.bp)
        self.cl_push('r0')
        self.cl_push('r1')
        self.cl_push('r2')
        self.cl_push('r3')
        self.cl_push('r4')
        self.cl_move(self.bp, self.sp)

        self.emit_comment('sub sp, %d' % (locals_size,))
        while locals_size > 16:
            self.emit_insn('add %s, %s, #-16' % (self.bp, self.bp))
            locals_size -= 16
        self.emit_insn('add %s, %s, #-%d' % (self.sp, self.sp, locals_size))

    def emit_func_epilogue(self):
        self.emit_comment('leave')
        self.cl_move(self.sp, self.bp)
        self.emit_insn('STR %s, %s, 7' % (self.retval_reg, self.sp))
        self.cl_pop('r4')
        self.cl_pop('r3')
        self.cl_pop('r2')
        self.cl_pop('r1')
        self.cl_pop('r0')
        self.cl_pop(self.bp)
        self.cl_pop(self.rp)
        self.emit_insn('RET')

    def emit_global_name(self, global_name):
        if global_name.location > 0 and self._cur_orig != global_name.location:
            if global_name.location < 0x3000 or global_name.location > 0xbfff:
                raise BackendError('pragma location 0x%x not in range 0x3000-0xbfff' % (global_name.location,))
            self.emit_section_end()
            self.emit_newline()
            self.emit_orig(global_name.location)
            self._cur_binary_loc = global_name.location
            self._cur_orig = global_name.location

        if type(global_name.value) == il.Variable:
            self.emit_global_variable(global_name)
        elif type(global_name.value) == il.Function:
            self.emit_function(global_name)
        else:
            raise RuntimeError('invalid GlobalName: ' + str(global_name.value))

    def compile(self):
        self._asm.append('; This code was compiled with the Gangweed Retargetable C Compiler')
        self._asm.append(';')
        self._asm.append(';')
        self._asm.append('')

        self._cur_binary_loc = 0x3000
        self._cur_orig = 0x3000

        self.emit_orig(self._cur_binary_loc)
        self.emit_stub()

        # emit globals then funcs
        for name in self._global_names:
            self.emit_global_name(name)

        self.emit_section_end()

        self.apply_relocations()

        self._compiled = True

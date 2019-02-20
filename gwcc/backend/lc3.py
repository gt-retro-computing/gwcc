from collections import defaultdict
from ..optimization.dataflow import LivenessAnalysis
from .. import il
from .. import cfg
from ..abi.lc3 import LC3 as ABI

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
        self.bp_offset = bp_offset

    def __repr__(self):
        if self.bp_offset >= 0:
            return '@[bp+%xh]' % (self.bp_offset,)
        else:
            return '@[bp-%xh]' % (self.bp_offset,)

    def __eq__(self, other):
        return type(other) == StackLocation and other.bp_offset == self.bp_offset

    def __hash__(self):
        return hash((1, self.bp_offset))

class RegisterLocation(object):
    def __init__(self, reg):
        self.reg = reg

    def __repr__(self):
        return '@%s' % (self.reg,)

    def __eq__(self, other):
        return type(other) == RegisterLocation and other.reg == self.reg

    def __hash__(self):
        return hash((2, self.reg))

class RegisterAllocator(object):
    register_set = ['r0', 'r1', 'r2', 'r3', 'r4', 'r7']

    def __init__(self, spill_callback):
        self.spill_callback = spill_callback

        # all registers is available to us except bp and sp.
        self.register_desc = {}  # maps from registers to what temps it stores.
        for reg in self.register_set:
            self.register_desc[reg] = set()

        self.address_desc = defaultdict(set)  # maps from temps to where it is stored (reg or mem).

        self.stack_slots = []

    @property
    def cur_bp_offset(self):
        return len(self.stack_slots)

    def alloc_stack(self, local):
        assert type(local) == il.Variable
        size = ABI.sizeof(local.type)
        for i in range(len(self.stack_slots)-size):
            for j in range(size):
                if self.stack_slots[i+j] is not None:
                    break
            else:
                slot_index = i
                break
        else:
            slot_index = len(self.stack_slots)
            self.stack_slots.extend([None] * size)

        self.stack_slots[slot_index:slot_index+size] = [1] * size
        return StackLocation(slot_index)

    def dealloc_stack(self, stack_address, size):
        self.stack_slots[stack_address:stack_address+size] = [None] * size

    def spill_reg(self, reg):
        """
        Free up a register by spilling all locals currently stored in it to the stack.
        :param reg: register to spill
        :return: spill destination that the register's old contents must be copied to
        """
        assert type(reg) == RegisterLocation

        spill_dst = None
        size = 0
        # spill all locals stored in this register, if they have not been spilled already.
        for local in self.register_desc[reg]:
            if not self.has_been_spilled(local):
                if not spill_dst:
                    spill_dst = self.alloc_stack(local)
                    size = ABI.sizeof(local)
                else:
                    assert size == ABI.sizeof(local)
                self.address_desc[local].add(spill_dst)
                self.address_desc[local].remove(reg)

        if not spill_dst:
            raise RuntimeError('tried to spill a register that did not require spilling')

        # this register is now free
        self.register_desc[reg].clear()

        return spill_dst

    def has_been_spilled(self, local):
        return any(map(lambda location: type(location) == StackLocation, self.address_desc[local]))

    def getreg(self, live_out, dst_var, src_var):
        # 1. if the name B is in a register that holds the value of no other names,
        # and B is not live out of the statement, then return that register B for L.
        src_regs = filter(lambda add_desc: type(add_desc) == RegisterLocation, address_desc[src_var])
        for src_reg in src_regs:
            if len(self.register_desc[src_reg]) == 1:
                assert self.register_desc[src_reg] == src_var
                if src_var not in live_out:
                    return src_reg

        # 2. failing (1), return an empty register for L if there is one.
        for reg in self.register_set:
            if not self.register_desc[reg]:
                return reg

        # 3. failing (2), spill some other register variable to memory to make room.
        # prefer register where, for all temporaries currently stored in the register, have been spilled already
        for reg in self.register_set:
            if all(map(self.has_been_spilled, self.register_desc[reg])):
                return reg

        # ok, we have to emit a spill copy. but still, avoid spilling src_var.
        for reg in self.register_set:
            if src_var not in self.register_desc[reg]:
                spill_dst = self.spill_reg(reg)
                self.spill_callback(spill_dst, reg)
                return reg

        raise RuntimeError("couldn't allocate register for variable " + dst_var)

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

    bp = 'r5' # basepointer basepointer basepointer basepointer
    sp = 'r6' # stack pointer
    rp = 'r7' # return pointer

    def __init__(self, names):
        assert all(map(lambda e: type(e) == il.GlobalName, names))

        # input
        self._names = names

        # state
        self._mappings = {} # where all the global vars are gettin allocated
        self._deferred_relocations = []
        self._cur_binary_loc = None

        # output
        self._compiled = False
        self._asm = []

    def get_output(self):
        if not self._compiled:
            raise RuntimeError('input has not been compiled')
        return self._asm

    def mangle_name(self, name):
        return '_' + name




    def place_relocation(self, name):
        self.emit_newline()
        self.emit_comment('symbol: %s' % (name,))
        self._mappings[self.mangle_name(name)] = self._cur_binary_loc

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
        line += '\t; loc=%02x' % (self._cur_binary_loc,)
        self._asm.append(line)
        self._cur_binary_loc += binary_len

    def emit_newline(self):
        self._asm.append('')

    def emit_comment(self, line):
        self._asm.append('; ' + line)

    def emit_insn(self, insn):
        self._emit_line(insn, 1)

    def emit_orig(self, to):
        self._emit_line('.orig x%x' % (to,), 0)

    def emit_section_end(self):
        self._emit_line('.end', 0)

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

    def cl_twos(self, reg):
        self.emit_insn('NOT %s, %s' % (reg, reg))
        self.emit_insn('ADD %s, %s, #1' % (reg, reg))

    def cl_push(self, src_reg):
        self.emit_comment('push ' + src_reg)
        self.emit_insn('ADD %s, %s, #-1' % (self.sp, self.sp))
        self.emit_insn('STR %s, %s, #0' % (src_reg, self.sp))

    def cl_pop(self, dst_reg):
        self.emit_comment('pop ' + dst_reg)
        self.emit_insn('LDR %s, %s, #0' % (dst_reg, self.sp))
        self.emit_insn('ADD %s, %s, #1' % (self.sp, self.sp))

    def cl_move(self, dst_reg, src_reg):
        self.emit_comment('mov ' + dst_reg + ', ' + src_reg)
        self.cl_zero_reg(dst_reg)
        self.emit_insn('ADD %s, %s, %s' % (dst_reg, dst_reg, src_reg))

    def cl_sub(self, dst_reg, src_reg):
        self.emit_comment('sub ' + dst_reg + ', ' + src_reg)
        self.cl_twos(src_reg)
        self.emit_insn('ADD %s, %s, %s' % (dst_reg, dst_reg, src_reg))
        self.cl_twos(src_reg)





    def cl_load_reg(self, reg, value):
        """
        Set a register to a 16-bit value using a constant length of code.
        """
        self.emit_comment('load: %s <- %d (0x%02x)' % (reg, value, value))
        self.cl_zero_reg(reg)
        value %= 0x10000
        for bit in range(15, -1, -1):
            self.emit_insn('ADD %s, %s, %s' % (reg, reg, reg))
            self.emit_insn('ADD %s, %s, #%d' % (reg, reg, (value >> bit) & 1))


    def vl_load_reg(self, reg, value):
        """
        Set a register to a 16-bit value using a variable length of code.
        """
        self.emit_comment('load: %s <- %d (0x%02x)' % (reg, value, value))
        self.cl_zero_reg(reg)
        value %= 0x10000
        while value:
            self.emit_insn('ADD %s, %s, #%d' % (reg, reg, value & 1))
            self.emit_insn('ADD %s, %s, %s' % (reg, reg, reg))
            value >>= 1

    def reloc_load_address(self, reg, name):
        if self.is_name_mapped(name):
            self.vl_load_reg(reg, self.get_binary_location(name))
        else:
            self.emit_comment('relocated load: %s <- %s' % (reg, name))
            self.make_reloc(self.cl_load_reg, reg, Relocation.Resolved(name))

    def reloc_jump_to(self, label):
        self.emit_insn('LD %s, #1' % (self.rp,))
        self.emit_insn('jmp %s' % (self.rp,))
        if self.is_name_mapped(label):
            self.emit_fill(self.get_binary_location(label))
        else:
            self.emit_comment('relocated address: ' + label)
            self.make_reloc(self.emit_fill, Relocation.Resolved(label))





    def emit_stub(self):
        """
        Emits a compiler-generated stub to setup the stack and shit
        """
        self.cl_load_reg(LC3.bp, 0xbfff)
        self.cl_move(LC3.sp, LC3.bp)
        self.reloc_jump_to(self.mangle_name('main'))

    def emit_global_variable(self, glob):
        self.place_relocation(glob.name)

        var = glob.value
        init = glob.init
        asm_name = self.mangle_name(glob.name)

        if var.type in [il.Types.char, il.Types.uchar, il.Types.short, il.Types.ushort,
                        il.Types.int, il.Types.uint]:
            if init:
                assert init.type == il.CompiledValueType.Integer
                self.emit_fill(init.value, asm_name)
            else:
                self.emit_blkw(asm_name, 1)
        else:
            raise RuntimeError('type %s not supported by this backend' % (var.type,))

    def vl_shift_bp(self, bp_offset, callback):
        bp_delta = 0 # how much the bp moved, so how much we have to unshift it by
        while bp_offset < -32:
            self.emit_insn('ADD %s, %s, #-16' % (self.bp, self.bp))
            bp_offset -= -16
            bp_delta -= 16
        while bp_offset > 31:
            self.emit_insn('ADD %s, %s, #15' % (self.bp, self.bp))
            bp_offset -= 15
            bp_delta += 15

        callback()

        # move bp back
        while bp_delta > 16:
            self.emit_insn('ADD %s, %s, #-16' % (self.bp, self.bp))
            bp_delta -= 16
        while bp_delta < -15:
            self.emit_insn('ADD %s, %s, #15' % (self.bp, self.bp))
            bp_delta += 15

    def vl_load_local(self, dst_reg, bp_offset):
        self.vl_shift_bp(bp_offset, lambda: self.emit_insn('LDR %s, %s, #-%d' % (dst_reg, self.bp, bp_offset)))

    def vl_store_local(self, src_reg, bp_offset):
        self.vl_shift_bp(bp_offset, lambda: self.emit_insn('STR %s, %s, #-%d' % (src_reg, self.bp, bp_offset)))

    def emit_function(self, glob):
        self.place_relocation(glob.name)

        func = glob.value
        # print func.pretty_print()
        # with open('tmp_cfg_func_%s.dot' % func.name, 'w') as f:
        #     func.dump_graph(fd=f)
        def liveness_set_to_str(live):
            return '(' + ', '.join(map(lambda v: v.name, live)) + ')'

        spill_callback = lambda spill_loc, src_reg: self.vl_store_local(src_reg, spill_loc.bp_offset)
        reg_alloc = RegisterAllocator(spill_callback)

        for i, param in enumerate(func.params):
            reg_alloc.address_desc[param].add(StackLocation(i - 6))

        for local in func.locals:
            if local not in func.params:
                reg_alloc.alloc_stack(local)

        # function prologue
        self.emit_func_prologue(reg_alloc.cur_bp_offset)

        # linearize the cfg
        blocks = cfg.topoorder(func.cfg)

        # let's cop liveness
        liveness = LivenessAnalysis(func).compute_liveness()

        fd = open('tmp_liveness_debug.dot', 'w')
        print >> fd, "digraph \"%s\" {" % ('CFG',)
        for bb in blocks:
            # statement-level live-out sets
            stmt_liveness = [set() for _ in range(len(bb.stmts))]
            stmt_liveness[-1].update(liveness.live_out(bb))
            for i in range(len(bb.stmts) - 1, 0, -1):
                stmt = bb.stmts[i]
                stmt_liveness[i - 1].update(stmt_liveness[i])
                stmt_liveness[i - 1].discard(il.defed_var(stmt))
                stmt_liveness[i - 1].update(il.used_vars(stmt))
            label = "== Block %s ==" % bb.name + '\\l'
            label += 'LIVE IN: ' + liveness_set_to_str(liveness.live_in(bb)) + '\\l'
            for i in range(len(bb.stmts)):
                label += str(bb.stmts[i]) + '\\l'
                label += '    ' + liveness_set_to_str(stmt_liveness[i]) + '\\l'
            label += 'LIVE OUT: ' + liveness_set_to_str(liveness.live_out(bb)) + '\\l'
            print >> fd, "    %s [shape=box, label=\"%s\"]" % (bb.name, label)
        for bb in func.cfg.basic_blocks:
            for edge in func.cfg.get_edges(bb):
                print >> fd, "%s -> %s;" % (edge.src, edge.dst)
        print >>fd, "}\n"
        fd.close()

        self.emit_func_epilogue()

    def emit_func_prologue(self, locals_size):
        self.cl_push(self.rp)
        self.cl_push(self.bp)
        self.cl_push('r1')
        self.cl_push('r2')
        self.cl_push('r3')
        self.cl_push('r4')
        self.cl_move(self.bp, self.sp)

        self.emit_comment('sub sp, %d' % (locals_size,))
        while locals_size > 16:
            self.emit_insn('ADD %s, %s, #-16' % (self.bp, self.bp))
            locals_size -= 16
        self.emit_insn('ADD %s, %s, #-%d' % (self.sp, self.sp, locals_size))

    def emit_func_epilogue(self):
        self.emit_comment('leave')
        self.cl_move(self.sp, self.bp)
        self.cl_pop('r4')
        self.cl_pop('r3')
        self.cl_pop('r2')
        self.cl_pop('r1')
        self.cl_pop(self.bp)
        self.cl_pop(self.rp)
        self.emit_insn('RET')

    def emit_global_name(self, global_name):
        if global_name.location > 0:
            if global_name.location < 0x3000 or global_name.location > 0xBFFF:
                raise SyntaxError('pragma location 0x%x not in range 0x3000-0xBFFF' % (global_name.location,))
            self.emit_section_end()
            self.emit_orig(global_name.location)
            self._cur_binary_loc = global_name.location

        if type(global_name.value) == il.Variable:
            self.emit_global_variable(global_name)
        elif type(global_name.value) == il.Function:
            self.emit_function(global_name)
        else:
            raise RuntimeError('invalid GlobalName: ' + str(global_name.value))

    def compile(self):
        self._cur_binary_loc = 0x3000
        self.emit_orig(self._cur_binary_loc)
        self.emit_stub()

        # emit globals then funcs
        global_vars = filter(lambda name: type(name.value) == il.Variable, self._names)
        for var in global_vars:
            self.emit_global_name(var)

        functions = filter(lambda name: type(name.value) == il.Function, self._names)
        for func in functions:
            self.emit_global_name(func)

        self.emit_section_end()

        self.apply_relocations()

        self._compiled = True

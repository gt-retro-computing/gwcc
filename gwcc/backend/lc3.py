from ..optimization.dataflow import LivenessAnalysis
from .. import il
from ..util.enum import Enum

class Relocation(object):
    def __init__(self, asm_idx, asm_len, gen_func, *gen_args):
        self.asm_idx = asm_idx
        self.asm_len = asm_len
        self.gen_func = gen_func
        self.gen_args = gen_args

    def __str__(self):
        return 'relocation<idx=%d len=%d func=%d, args=%s>' % (self.asm_idx, self.asm_idx, self.gen_func, self.gen_args)

    class Resolved(object):
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return 'r!' + self.name

class LC3(object):
    """
    --- The LC3 GANGWEED C BINARY ABI ---
    Basically, imagine you're on a __fastcall compiler in 16 bits.

    For word-size arguments:
        Return value in r0.
        Registers passed in r0, r1, r2, r3 then pushed on the stack.
    For larger-than-word-size aruguments:
        Passed as pointer to the stack using protocol described above.

    r4, r5, r6, and r7 are all callee-saved registers. r0, r1, r2, r3 are not saved.
    r5 is the frame pointer and r6 is the stack pointer. Stack cleanup is callee.

    Stack starts at 0xFFFF and grows toward lower addresses.
    """

    bp = 'r5'
    sp = 'r6'
    rp = 'r7'

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

    def _apply_reloc(self, reloc):
        asm_bak = self._asm
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

    def apply_relocations(self):
        for reloc in self._deferred_relocations:
            self._apply_reloc(reloc)

    def place_relocation(self, name):
        self.emit_comment('symbol: %s' % (name,))
        self._mappings[self.mangle_name(name)] = self._cur_binary_loc

    def _emit_line(self, line, binary_len):
        self.emit_comment('loc=%02x' % (self._cur_binary_loc,))
        self._asm.append(line)
        self._cur_binary_loc += binary_len

    def emit_comment(self, line):
        self._asm.append('; ' + line)

    def emit_insn(self, insn):
        self._emit_line(insn, 1)

    def emit_orig(self, to):
        self._emit_line('.orig x%x' % (to,), 0)

    def emit_section_end(self):
        self._emit_line('.end', 0)

    def emit_fill(self, name, value):
        self._emit_line('%s .fill %d' % (name, value), 1)

    def emit_blkw(self, name, size):
        self._emit_line('%s .blkw %d' % (name, size), size)

    def emit_global_variable(self, glob):
        self.place_relocation(glob.name)

        var = glob.value
        init = glob.init
        asm_name = self.mangle_name(glob.name)

        if var.type in [il.Types.char, il.Types.uchar, il.Types.short, il.Types.ushort,
                        il.Types.int, il.Types.uint]:
            if init:
                assert init.type == il.CompiledValueType.Integer
                self.emit_fill(asm_name, init.value)
            else:
                self.emit_blkw(asm_name, 1)
        else:
            raise RuntimeError('type %s not supported by this backend' % (var.type,))


    def emit_function(self, glob):
        self.place_relocation(glob.name)

        func = glob.value
        # print func.pretty_print()
        # with open('tmp_cfg_func_%s.dot' % func.name, 'w') as f:
        #     func.dump_graph(fd=f)
        liveness = LivenessAnalysis(func).compute_liveness()

    def cl_zero_reg(self, reg):
        """
        Zero a register using a constant length of code.
        """
        self.emit_insn('AND %s, %s, #0' % (reg, reg))

    def cl_load_reg(self, reg, value):
        """
        Set a register to a 16-bit value using a constant length of code.
        """
        self.emit_comment('load: %s <- %d (0x02%x)' % (reg, value, value))
        self.cl_zero_reg(reg)
        value %= 0x10000
        for bit in range(0, 16):
            self.emit_insn('ADD %s, %s, #%d' % (reg, reg, value & 1))
            self.emit_insn('ADD %s, %s, %s' % (reg, reg, reg))
            value >>= 1
        assert value == 0

    def reloc_load_address(self, reg, name):
        self.emit_comment('relocated load: %s <- %s' % (reg, name))
        asm_idx_start = len(self._asm)
        self.cl_load_reg(reg, 0)
        asm_idx_end = len(self._asm)
        reloc = Relocation(asm_idx_start, asm_idx_end - asm_idx_start,
                           self.cl_load_reg, reg, Relocation.Resolved(name))
        self._deferred_relocations.append(reloc)

    def jump_to(self, label):
        self.reloc_load_address('r0', label)
        self.emit_insn('jmp #r0')

    def emit_stub(self):
        """
        Emits a compiler-generated stub to setup the stack and shit
        """
        self.cl_load_reg(LC3.bp, 0xffff)
        self.cl_load_reg(LC3.sp, 0xffff)
        self.jump_to(self.mangle_name('main'))

    def compile(self):
        self._cur_binary_loc = 0x3000
        self.emit_orig(self._cur_binary_loc)
        self.emit_stub()

        for global_name in self._names:
            if global_name.location > 0:
                if global_name.location < 0x3000 or global_name.location > 0xFFFF:
                    raise SyntaxError('pragma location 0x%x not in range 0x3000-0xFFFF' % (global_name.location,))
                if global_name.location != self._cur_binary_loc:
                    self.emit_section_end()
                    self.emit_orig(global_name.location)
                    self._cur_binary_loc = global_name.location

            if type(global_name.value) == il.Variable:
                self.emit_global_variable(global_name)
            elif type(global_name.value) == il.Function:
                self.emit_function(global_name)

        self.emit_section_end()

        self.apply_relocations()

        self._compiled = True

from ..optimization.dataflow import LivenessAnalysis
from .. import il

class LC3(object):
    def __init__(self, names):
        assert all(map(lambda e: type(e) == il.GlobalName, names))

        # input
        self._names = names

        # output
        self._compiled = False
        self._asm = []

    def get_output(self):
        if not self._compiled:
            raise RuntimeError('input has not been compiled')
        return self._asm

    def mangle_name(self, name):
        return '_' + name

    def emit_global_variable(self, glob):
        var = glob.value
        init = glob.init
        asm_name = self.mangle_name(glob.name)

        if var.type in [il.Types.char, il.Types.uchar, il.Types.short, il.Types.ushort,
                        il.Types.int, il.Types.uint]:
            if init:
                assert init.type == il.CompiledValueType.Integer
                self.emit_line('%s .fill %d' % (asm_name, init.value))
            else:
                self.emit_line('%s .blkw 1' % (asm_name,))
        else:
            raise RuntimeError('type %s not supported by this backend' % (var.type,))

    def emit_function(self, glob):
        func = glob.value
        # print func.pretty_print()
        with open('tmp_cfg_func_%s.dot' % func.name, 'w') as f:
            func.dump_graph(fd=f)
        liveness = LivenessAnalysis(func).compute_liveness()

    def sorted_names(self):
        # rearrange globals so that they are in ascending order for allocation
        cur_chunk = None
        chunks = []
        for global_name in self._names:
            if not cur_chunk or global_name.location != 0:
                cur_chunk = [global_name]
                chunks.append(cur_chunk)
            else:
                cur_chunk.append(global_name)
        return sorted(chunks, key=lambda c: c[0].location)

    def emit_line(self, line):
        self._asm.append(line)

    def compile(self):
        chunks = self.sorted_names()
        if not chunks or chunks[0][0].location == 0:
            cur_loc = 0x3000
        else:
            cur_loc = chunks[0][0].location
        self.emit_line('.orig x%x' % (cur_loc,))

        for chunk in chunks:
            loc_delta = chunk[0].location - cur_loc
            assert loc_delta >= 0
            if loc_delta > 0:
                self.emit_line('.blkw %d' % (loc_delta,))

            for global_name in chunk:
                if type(global_name.value) == il.Variable:
                    self.emit_global_variable(global_name)
                elif type(global_name.value) == il.Function:
                    self.emit_function(global_name)

        self.emit_line('.end')
        self._compiled = True

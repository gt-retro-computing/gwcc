"""
Computes dataflow analysis such as liveness.
"""

from .. import cfg
from .. import il
from collections import deque, defaultdict

class LivenessAnalysis(object):
    """
    A nice little naive non-SSA Liveness analyser. Brings me back... :)
    Loosely based on my old one.
    """
    def __init__(self, func):
        self.func = func
        self.cfg = func.cfg

        self._use = defaultdict(set) # multimap from bb to list of vars used
        self._def = defaultdict(set) # multimap from bb to list of vars killed

        self._out = defaultdict(set) # live-out sets
        self._in = defaultdict(set) # live-in sets

        self.compute_liveness()

    def live_out(self, bb):
        return self._out[bb]

    def live_in(self, bb):
        return self._in[bb]

    def compute_liveness(self):
        for bb in self.cfg.basic_blocks:
            self.precompute_block(bb)

        queue = deque(cfg.topoorder(self.cfg))
        while queue:
            bb = queue.popleft()

            # out[n] = U(s in succ[n])( in [s])
            cur_out = set()
            for e in self.cfg.get_edges(bb):
                cur_out.update(self._in[e.dst])

            # in[n] = use[n] U(out[n] - def[n])
            cur_in = cur_out.difference(self._def[bb])
            cur_in.update(self._use[bb])

            # update results
            self._out[bb] = cur_out
            old_in = self._in[bb]
            self._in[bb] = cur_in

            # update worklist
            if old_in != cur_in:
                for e in self.cfg.get_edges_to(bb):
                    if not e.src in queue:
                        queue.append(e.src)
        return self

    def precompute_block(self, bb):
        """
        Precompute use and kill sets for the given basicblock
        """
        # "we have to iterate in reverse order because a definition will kill a use in the current block
        # this is so that uses do not escape a block if its def is in the same block. this is basically
        # simulating a statement graph analysis"
        for stmt in reversed(bb.stmts):
            def_var = il.defed_var(stmt)
            if def_var:
                self._def[bb].add(def_var)
                self._use[bb].discard(def_var)

            use_vars = il.used_vars(stmt)
            for use_var in use_vars:
                self._use[bb].add(use_var)
            if type(stmt) == il.ReturnStmt:
                self._use[bb].add(self.func.retval)

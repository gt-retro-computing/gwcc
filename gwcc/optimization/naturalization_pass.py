"""
The purpose of the CFG naturalization pass is to apply simple, trivial reductions to the CFG
to simplify it before later, heavier passes.
"""

from ..cfg import FlowEdge
from .. import il

class NaturalizationPass(object):
    def __init__(self, func):
        self.func = func
        self.cfg = func.cfg

    # merge two blocks into one.
    def merge(self, bb, succ):
        assert bb.stmts[-1].dst_block == succ

        # drop flow statement
        bb.stmts = bb.stmts[:-1]

        # xfer stmts
        for stmt in succ.stmts:
            bb.add_stmt(stmt)

        cfg = self.cfg
        # copy edges
        for e in cfg.get_edges(succ):
            cfg.add_edge(FlowEdge(bb, e.dst))

        # drop merged block and its incident edges
        cfg.remove_block(succ)

    # replace all references of bb_to_inline with bb_inline_as, and drop bb_to_inline.
    # this is good for cleaning up blocks that are just a single jump.
    def inline(self, bb_to_inline, bb_inline_as):
        cfg = self.cfg
        for e in cfg.get_edges_to(bb_to_inline):
            pred = e.src

            # copy edge
            cfg.add_edge(FlowEdge(pred, bb_inline_as))

            # rewrite flow statement
            flow_stmt = pred.stmts[-1]
            if type(flow_stmt) == il.GotoStmt:
                assert flow_stmt.dst_block == bb_to_inline
                flow_stmt.dst_block = bb_inline_as
            elif type(flow_stmt) == il.CondJumpStmt:
                assert flow_stmt.true_block == bb_to_inline or flow_stmt.false_block == bb_to_inline
                if flow_stmt.true_block == bb_to_inline:
                    flow_stmt.true_block = bb_inline_as
                if flow_stmt.false_block == bb_to_inline:
                    flow_stmt.false_block = bb_inline_as
            else:
                raise ValueError('invalid flow statement at end of block: ' + str(flow_stmt))

        cfg.remove_block(bb_to_inline)

    # replace conditional jumps where both branches are the same with just a goto
    def kill_trivial_conditional(self, bb):
        assert len(self.cfg.get_edges(bb)) == 1
        target = bb.stmts[-1].true_block
        bb.stmts[-1] = il.GotoStmt(target)
        # self.cfg.add_edge(FlowEdge(bb, target))

    def process(self):
        cfg = self.cfg
        # iteratively clean up the graph and stop when no more modifications are made.
        while True:
            for bb in cfg.basic_blocks:
                # kill empty blocks
                if not bb.stmts:
                    if cfg.get_edges(bb):
                        raise RuntimeError('empty block has outgoing edges')
                    elif cfg.get_edges_to(bb):
                        raise RuntimeError('empty block has incoming edges')
                    cfg.remove_block(bb)
                    break

                # merge singleton immediate flow siblings
                if len(cfg.get_edges(bb)) == 1:
                    succ = next(iter(cfg.get_edges(bb))).dst
                    if len(cfg.get_edges_to(succ)) == 1 and type(succ.stmts[-1]) == il.GotoStmt:
                        # print 'merging ' + str(succ) + ' into ' + str(bb)
                        self.merge(bb, succ)
                        break

                # blocks that are a single jump may be inlined
                if len(bb.stmts) == 1 and type(bb.stmts[0]) == il.GotoStmt:
                    if bb.stmts[0].dst_block != bb:
                        # print 'inlining ' + str(bb) + ' as ' + str(bb.stmts[0].dst_block)
                        self.inline(bb, bb.stmts[0].dst_block)
                        break

                # replace conditional jumps where both branches are the same with just a goto
                if type(bb.stmts[-1]) == il.CondJumpStmt and bb.stmts[-1].true_block == bb.stmts[-1].false_block:
                    # print 'dropping trivial ' + str(bb)
                    self.kill_trivial_conditional(bb)
                    break
            else:
                break

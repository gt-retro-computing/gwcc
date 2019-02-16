class BasicBlock(object):
    def __init__(self, name):
        self.name = name
        self.stmts = []

    def add_stmt(self, stmt):
        self.stmts.append(stmt)

    def __str__(self):
        return self.name

    def pretty_print(self):
        result = '=== Block %s ===\n' % (self.name,)
        for stmt in self.stmts:
            result += str(stmt) + '\n'
        return result

class FlowEdge(object):
    def __init__(self, src, dst):
        assert type(src) == BasicBlock
        assert type(dst) == BasicBlock
        self.src = src
        self.dst = dst

    def __repr__(self):
        return '%s -> %s' % (self.src, self.dst)

    def __eq__(self, other):
        return self.src == other.src and self.dst == other.dst

    def __hash__(self):
        return hash((self.src, self.dst))

class ControlFlowGraph(object):
    def __init__(self):
        self.basic_blocks = set()
        self._edges = {}
        self._reverse_edges = {}
        self.entry = None

    def new_block(self):
        bb = BasicBlock('L%d' % (len(self.basic_blocks)))
        self.basic_blocks.add(bb)
        self._edges[bb] = set()
        self._reverse_edges[bb] = set()
        if not self.entry:
            self.entry = bb
        return bb

    @property
    def num_blocks(self):
        return len(self.basic_blocks)

    def remove_block(self, bb):
        self.basic_blocks.remove(bb)
        del self._edges[bb]
        del self._reverse_edges[bb]

    def get_edges(self, bb):
        return self._edges[bb]

    def get_edges_to(self, bb):
        return self._reverse_edges[bb]

    def add_edge(self, e):
        assert type(e) == FlowEdge
        self._edges[e.src].add(e)
        self._reverse_edges[e.dst].add(e)

    def remove_edge(self, e):
        self._edges[e.src].remove(e)
        self._reverse_edges[e.dst].remove(e)

    def has_edge(self, src, dst):
        return any(map(lambda e: e.dst == dst, self._edges[src]))

    def pretty_print(self):
        result = ''
        for bb in topoorder(self):
            result += bb.pretty_print()
            for outgoing_edge in self.get_edges(bb):
                result += str(outgoing_edge) + '\n'
            for incoming_edge in self.get_edges_to(bb):
                result += str(incoming_edge) + '\n'
        return result

def postorder(cfg):
    if not cfg.basic_blocks:
        return []

    if not cfg.entry:
        raise ValueError('cfg has no entry')

    result = []
    coloring = {}
    stack = [cfg.entry]
    while stack:
        v = stack[-1]
        if v not in coloring: # white
            coloring[v] = 1 # set to gray
            for e in cfg.get_edges(v):
                stack.append(e.dst)
        elif coloring[v] == 1: # gray
            coloring[v] = 2 # set to black
            result.append(v)
        elif coloring[v] == 2: # black
            stack.pop()
    return result

def topoorder(cfg):
    return list(reversed(postorder(cfg)))

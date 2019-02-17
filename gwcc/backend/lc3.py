from ..optimization.dataflow import LivenessAnalysis
from .. import il

class LC3(object):
    def __init__(self, globals, functions):
        assert all(map(lambda e: type(e) == il.Variable, globals))
        assert all(map(lambda e: type(e) == il.Function, functions))

        # input
        self.globals = globals
        self.functions = functions

    def compile(self):
        for func in self.functions:
            liveness = LivenessAnalysis(func).compute_liveness()

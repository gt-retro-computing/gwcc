from pycparser import parse_file, c_parser
import gwcc
import platform
from gwcc.abi.lc3 import LC3

from gwcc.optimization.dataflow import LivenessAnalysis


def banner():
    print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
    print '(c) 2019 gangweed ganggang. All rights reserved.'
    print


if __name__ == '__main__':
    banner()

    parser = c_parser.CParser()

    if platform.system() == 'Darwin':
        ast = parse_file('testcases/1.c', use_cpp=True, cpp_path='clang', cpp_args='-E')
    else:
        ast = parse_file('testcases/1.c', use_cpp=True)

    frontend = gwcc.Frontend(LC3)
    frontend.compile(ast)

    for func in frontend.functions:
        print func.pretty_print()
        liveness = LivenessAnalysis(func).compute_liveness()

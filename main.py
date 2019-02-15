from pycparser import parse_file, c_parser
import gwcc
from gwcc.abi.lc3 import LC3

print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
print '(c) 2019 gangweed ganggang. All rights resreved.'
print

parser = c_parser.CParser()
ast = parse_file('testcases/1.c', use_cpp=True)
compiler = gwcc.Compiler(LC3)
compiler.compile(ast)

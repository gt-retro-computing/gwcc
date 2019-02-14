from pycparser import parse_file, c_parser
import gwcc

print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
print '(c) 2019 gangweed ganggang. All rights resreved.'
print

parser = c_parser.CParser()
ast = parse_file('testcases/1.c', use_cpp=True)
compiler = gwcc.Compiler()
compiler.compile(ast)

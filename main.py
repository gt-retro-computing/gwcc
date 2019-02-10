from pycparser import parse_file, c_parser
from i8080cc import Compiler

parser = c_parser.CParser()
ast = parse_file('testcases/1.c', use_cpp=True)
compiler = Compiler()
compiler.compile(ast)

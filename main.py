from pycparser import parse_file, c_parser
import gwcc

def banner():
    print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
    print '(c) 2019 gangweed ganggang. All rights reserved.'
    print

if __name__ == '__main__':
    banner()

    parser = c_parser.CParser()
    ast = parse_file('testcases/1.c', use_cpp=True)
    frontend = gwcc.Frontend(gwcc.abi.LC3)
    frontend.compile(ast)

    for func in frontend.functions:
        print func.pretty_print()

    backend = gwcc.backend.LC3(frontend.globals, frontend.functions)
    backend.compile()

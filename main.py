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

    backend = gwcc.backend.LC3(frontend.get_globals())
    backend.compile()
    print '\n'.join(backend.get_output())

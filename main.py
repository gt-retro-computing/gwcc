from pycparser import parse_file, c_parser
import gwcc
import platform
import argparse

def banner():
    print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
    print '(c) 2019 gangweed ganggang. All rights reserved.'
    print


if __name__ == '__main__':
    banner()

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('source_file', default='testcases/1.c', nargs='?')
    args = args_parser.parse_args()

    parser = c_parser.CParser()

    if platform.system() == 'Darwin':
        ast = parse_file(args.source_file, use_cpp=True, cpp_path='clang', cpp_args='-E')
    else:
        ast = parse_file(args.source_file, use_cpp=True)

    frontend = gwcc.Frontend(gwcc.abi.LC3)
    frontend.compile(ast)

    backend = gwcc.backend.LC3(frontend.get_globals())
    backend.compile()
    print '\n'.join(backend.get_output())

from pycparser import parse_file, c_parser
import gwcc
import platform
import argparse
from os import path

def banner():
    print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
    print '(c) 2019 gangweed ganggang. All rights reserved.'
    print

if __name__ == '__main__':
    banner()

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('source_file', default='testcases/1.c', nargs='?')
    args_parser.add_argument('-o', '--output', nargs=1)
    args = args_parser.parse_args()
    if args.output is None:
        args.output = path.splitext(path.basename(args.source_file))[0] + '.asm'

    parser = c_parser.CParser()

    if platform.system() == 'Darwin':
        ast = parse_file(args.source_file, use_cpp=True, cpp_path='clang', cpp_args='-E')
    else:
        ast = parse_file(args.source_file, use_cpp=True)

    frontend = gwcc.Frontend(gwcc.abi.LC3)
    frontend.compile(ast)

    backend = gwcc.backend.LC3(frontend.get_globals(), with_symbols=True)
    backend.compile()
    print '\n\n\n\n\n'
    print '\n'.join(backend.get_output())
    with open(args.output, 'w') as f:
        f.write('\n'.join(backend.get_output()))
    import os
    os.system('scp ' + args.output + ' vm:complx')

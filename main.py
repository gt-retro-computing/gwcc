from colorama import init, Fore

from gwcc.backend.util import BackendError

init()

from pycparser import c_parser, preprocess_file, CParser
import gwcc
import platform
import argparse
from os import path

from gwcc.c_frontend import ParseError


def banner():
    print 'The Gangweed Retargetable C Compiler [Version %s]' % (gwcc.__version__,)
    print '(c) 2019 gangweed ganggang. All rights reserved.'
    print


def parse_file_text(filename, use_cpp=False, cpp_path='cpp', cpp_args=''):
    with open(filename) as f:
        raw_text = f.read()

    if use_cpp:
        text = preprocess_file(filename, cpp_path, cpp_args)
    else:
        text = raw_text

    return raw_text, CParser().parse(text, filename)


def print_error(err):
    assert type(err) == ParseError or type(err) == BackendError
    if hasattr(err, 'coord') and err.coord:
        print e.coord
        print source_code.split('\n')[e.coord.line - 1]
        print ' ' * (e.coord.column - 1) + '^'

    print Fore.RED + 'ERROR: ' + Fore.RESET + e.message


if __name__ == '__main__':
    banner()

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('source_file', default='testcases/1.c', nargs='?')
    args_parser.add_argument('-o', '--output', nargs=1)
    args_parser.add_argument('-g', '--symbols', action='store_true')
    args = args_parser.parse_args()
    if args.output is None:
        args.output = path.splitext(path.basename(args.source_file))[0] + '.asm'

    parser = c_parser.CParser()

    if platform.system() == 'Darwin':
        source_code, ast = parse_file_text(args.source_file, use_cpp=True, cpp_path='clang', cpp_args='-E')
    else:
        source_code, ast = parse_file_text(args.source_file, use_cpp=True)

    frontend = gwcc.Frontend(gwcc.abi.LC3)

    try:
        frontend.compile(ast)
    except ParseError as e:
        print_error(e)
        exit(1)

    backend = gwcc.backend.LC3(frontend.get_globals(), with_symbols=True)

    try:
        backend.compile()
    except BackendError as e:
        print_error(e)
        exit(1)
    print '\n\n\n\n\n'
    print '\n'.join(backend.get_output())
    with open(args.output, 'w') as f:
        f.write('\n'.join(backend.get_output()))


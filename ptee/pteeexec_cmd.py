#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import textwrap
import threading

ERROR_MODES = [
    'warn',
    'warn-nopipe',
    'exit',
    'exit-nopipe',
]


class MockSubprocess:
    def __init__(self, mp: threading.Thread):
        self.mp = mp

    def wait(self):
        self.mp.join()
        return 0


def start_ptee(args, input_fd):
    # build argv from args
    argv = [
        'ptee',
        '--buffer-size', str(args.buffer_size),
        '--output-error', args.output_error,
    ]
    if args.prefix is not None:
        argv += ['--prefix', args.prefix]

    try:
        from ptee import ptee_cmd
        mpargv = argv[1:]  # exclude exe file name

        def wrapper():
            sys.stdin = os.fdopen(input_fd)
            mpargs = ptee_cmd.parse_args(mpargv)
            ptee_cmd.run(args=mpargs, use_signal=False)

        p = threading.Thread(target=wrapper)
        p.start()
        return MockSubprocess(p)
    except ImportError:
        p = subprocess.Popen(
            args=argv,
            stdin=input_fd,
        )
        return p


def start_cmd(args, output_fd):
    popen_args = {
        'args': args.command,
        'stdout': output_fd,
    }
    if args.stderr:
        popen_args['stderr'] = subprocess.STDOUT

    return subprocess.Popen(**popen_args)


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Execute a command with ptee',
        epilog=textwrap.dedent('''
            Example:
                $ ... | ptee
                $ pteeexec ...
                
            Example:
                ### ptee prevent that the terminal to be confused by parallel execution tasks.
                $ ... | xargs -P8 sh -c 'echo "$@" |& ptee --prefix=$$: ' --
                
                ### more easy by using an "pteeexec".
                $ ... | xargs -P8 ptee -e echo
        '''),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    try:
        # Monkey patch for format collapsing issue.
        def get_formatter():
            try:
                return argparse.RawTextHelpFormatter(
                    prog=sys.argv[0],
                    max_help_position=40)
            except:
                return argparse.RawTextHelpFormatter(prog=sys.argv[0])

        p._get_formatter = get_formatter
    except:
        pass

    p.add_argument('-e', '--stderr',
                   action='store_true',
                   help='stderr redirect to stdout')

    p.add_argument('-p', '--prefix',
                   help='add prefix to each lines')
    p.add_argument('-b', '--buffer-size',
                   type=int,
                   default=100000,
                   help='change buffer size (default 100000 lines)',
                   metavar='LINES')
    p.add_argument('--output-error',
                   default='warn-nopipe',
                   choices=ERROR_MODES,
                   help='set behavior on write error (default warn-nopipe)',
                   metavar='MODE')

    p.add_argument('command',
                   nargs='+',
                   help='command name and arguments',
                   metavar='ARGS')
    return p.parse_args(argv)


def main(argv=None):
    return run(parse_args(argv))


def run(args):
    r, w = os.pipe()

    cmd_proc = start_cmd(args, w)
    ptee_proc = start_ptee(args, r)

    ret = cmd_proc.wait()
    os.close(w)
    ptee_proc.wait()
    os.close(r)
    return ret


if __name__ == '__main__':
    exit(main())

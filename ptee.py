#!/usr/bin/env python3
import argparse
import fcntl
import os
import queue
import sys
import textwrap
import threading

def print_error(e):
    print('ptee: {}'.format(str(e)), file=sys.stderr)


def reader(input, q: queue.Queue):
    try:
        for line in input:
            q.put(line)
    except IOError as e:
        print_error(e)
    finally:
        # send shutdown message to writer thread.
        q.put(None)


def writer(outputs: list, q: queue.Queue, prefix: str):
    while True:
        # Wait for receiving a line.
        line = q.get()
        if line is None:
            return

        try:
            # Get exclusive lock on all files.
            for f in outputs:
                fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                if f.seekable():
                    f.seek(os.SEEK_END)

            # Write to all outputs until q is empty. If sender's so very fast,
            # this task will be taking a long time, and another "ptee" processes
            # will be blocked for a long time.
            while True:
                assert line is not None
                data = prefix + line
                for f in outputs:
                    f.write(data)

                line = q.get_nowait()  # might be raised queue.Empty
                if line is None:
                    return
        except queue.Empty:
            continue
        finally:
            # Release exclusive lock on all files.
            for f in outputs:
                f.flush()
                fcntl.lockf(f.fileno(), fcntl.LOCK_UN)


def parse_args():
    p = argparse.ArgumentParser(
        description='Parallelly writable tee command',
        epilog=textwrap.dedent('''
            example:
                $ rsync -av ... |& ptee --prefix='server1: ' --append rsync.log &
                $ rsync -av ... |& ptee --prefix='server2: ' --append rsync.log &
                $ wait
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

    p.add_argument('-a', '--append',
                   action='store_true',
                   help='append to the files')
    p.add_argument('-p', '--prefix',
                   nargs=1,
                   help='add prefix to each lines')
    p.add_argument('-b', '--buffer-size',
                   type=int,
                   default=100000,
                   help='change buffer size (default 100000 lines)',
                   metavar='LINES')
    p.add_argument('file',
                   nargs='*',
                   metavar='FILE')
    return p.parse_args()


def main():
    args = parse_args()
    mode = 'w'
    if args.append:
        mode = 'a'
    files = []
    for f in args.file:
        try:
            files.append(open(f, mode))
        except IOError as e:
            print_error(e)

    input = sys.stdin
    outputs = files + [sys.stdout]
    q = queue.Queue(maxsize=args.buffer_size)

    r = threading.Thread(target=reader, args=(input, q))
    r.start()
    w = threading.Thread(target=writer, args=(outputs, q, args.prefix))
    w.start()

    r.join()
    w.join()

    for f in files:
        try:
            f.close()
        except IOError as e:
            print_error(e)
    return 0


if __name__ == '__main__':
    exit(main())

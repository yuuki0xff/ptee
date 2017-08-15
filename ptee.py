#!/usr/bin/env python3
import argparse
import fcntl
import os
import queue
import sys
import textwrap
import threading
import traceback

ERROR_MODES = [
    'warn',
    'warn-nopipe',
    'exit',
    'exit-nopipe',
]


class StopWorker(Exception): pass

def print_error(e):
    print('ptee: {}'.format(str(e)), file=sys.stderr)


class ReadWorker(threading.Thread):
    def __init__(self, input_, q: queue.Queue):
        super().__init__()
        self.input_ = input_
        self.q = q
        self.return_val = None

    def run(self):
        try:
            for line in self.input_:
                self.q.put(line)
        except OSError as e:
            print_error(e)
            self.return_val = e
        except SystemExit:
            return
        except:
            self.return_val = traceback.format_exc()
        finally:
            # send shutdown message to writer thread.
            self.q.put(None)


class WriteWorker(threading.Thread):
    def __init__(self, outputs: list, q: queue.Queue, prefix: str, error_mode: str):
        super().__init__()
        self.outputs = outputs
        self.q = q
        self.prefix = prefix
        self.error_mode = error_mode
        self.is_broken = [False for _ in outputs]
        self.return_val = None

    def run(self):
        try:
            while True:
                # Wait for receiving a line.
                line = self.q.get()
                if line is None:
                    return

                try:
                    self.lock_all()

                    # Write to all outputs until q is empty. If sender's so very fast,
                    # this task will be taking a long time, and another "ptee" processes
                    # will be blocked for a long time.
                    while True:
                        assert line is not None
                        self.write_all(line)

                        line = self.q.get_nowait()  # might be raised queue.Empty
                        if line is None:
                            return
                except queue.Empty:
                    continue
                finally:
                    self.unlock_all()
        except StopWorker as e:
            self.return_val = e
        except SystemExit:
            return
        except:
            self.return_val = traceback.format_exc()
        finally:
            self.close_all()

    def on_error(self, i: int, e: BaseException):
        is_pipe = self.outputs[i] == sys.stdout

        if self.error_mode == 'warn' or (self.error_mode == 'warn-nopipe' and not is_pipe):
            print_error(e)
        elif self.error_mode == 'exit' or (self.error_mode == 'exit-nopipe' and not is_pipe):
            raise StopWorker(e)

        self.is_broken[i] = True
        if all(self.is_broken):
            raise StopWorker('all outputs is broken')

    def lock_all(self):
        "Get exclusive lock on all files."
        for i, f in enumerate(self.outputs):
            if self.is_broken[i]: continue
            try:
                fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                if f.seekable():
                    f.seek(os.SEEK_END)
            except OSError as e:
                self.on_error(i, e)

    def write_all(self, line: str):
        for i, f in enumerate(self.outputs):
            if self.is_broken[i]: continue
            try:
                if self.prefix:
                    f.write(self.prefix)
                f.write(line)
            except OSError as e:
                self.on_error(i, e)

    def unlock_all(self):
        "Release exclusive lock on all files."
        for i, f in enumerate(self.outputs):
            if self.is_broken[i]: continue
            try:
                f.flush()
                fcntl.lockf(f.fileno(), fcntl.LOCK_UN)
            except OSError as e:
                self.on_error(i, e)

    def close_all(self):
        "Release exclusive lock on all files."
        for i, f in enumerate(self.outputs):
            if self.is_broken[i]: continue
            try:
                f.close()
            except OSError as e:
                self.on_error(i, e)


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
    p.add_argument('--output-error',
                   default='warn-nopipe',
                   choices=ERROR_MODES,
                   help='set behavior on write error')
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

    r = ReadWorker(input, q)
    r.start()
    w = WriteWorker(outputs, q, args.prefix, args.output_error)
    w.start()

    r.join()
    w.join()  # all files will be closed.

    return (r.return_val, w.return_val) != (None, None)


if __name__ == '__main__':
    exit(main())

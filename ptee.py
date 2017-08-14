#!/usr/bin/env python3
import fcntl
import os
import queue
import sys
import threading


def reader(input, q: queue.Queue):
    try:
        for line in input:
            q.put(line)
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


def main():
    prefix = sys.argv[1]
    input = sys.stdin
    files = tuple(open(f, 'a') for f in sys.argv[2:]) + (sys.stdout,)
    q = queue.Queue(maxsize=100000)

    r = threading.Thread(target=reader, args=(input, q))
    r.start()
    w = threading.Thread(target=writer, args=(files, q, prefix))
    w.start()

    r.join()
    w.join()

    for f in files:
        f.close()
    return 0


if __name__ == '__main__':
    exit(main())

import os


def crash_main(q, params):  # runs in the spawned child
    os._exit(7)


def slow_main(q, params):
    import time
    time.sleep(30)

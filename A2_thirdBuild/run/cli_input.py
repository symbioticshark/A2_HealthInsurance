"""Small cross-platform terminal input helpers."""
import getpass
import os
import sys


def masked_input(prompt, mask="*"):
    """Read a secret while echoing one mask character per typed character."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return getpass.getpass(prompt)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if os.name == "nt":
        return _masked_windows(mask)
    return _masked_posix(mask)


def _masked_windows(mask):
    import msvcrt

    chars = []
    while True:
        char = msvcrt.getwch()
        if char in ("\r", "\n"):
            sys.stdout.write("\n")
            return "".join(chars)
        if char == "\x03":
            sys.stdout.write("\n")
            raise KeyboardInterrupt
        if char in ("\b", "\x7f"):
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if char in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue
        if char.isprintable():
            chars.append(char)
            sys.stdout.write(mask)
            sys.stdout.flush()


def _masked_posix(mask):
    import termios
    import tty

    chars = []
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            char = sys.stdin.read(1)
            if char in ("\r", "\n"):
                sys.stdout.write("\n")
                return "".join(chars)
            if char == "\x03":
                sys.stdout.write("\n")
                raise KeyboardInterrupt
            if char in ("\b", "\x7f"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if char.isprintable():
                chars.append(char)
                sys.stdout.write(mask)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)

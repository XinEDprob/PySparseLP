
"""Test based on the example5."""

import os

from pysparselp.examples.example5 import run


__folder__ = os.path.dirname(__file__)


def test_example5():

    cost = run(display=False)
    assert cost == 238.9849948936172


if __name__ == "__main__":
    test_example5()

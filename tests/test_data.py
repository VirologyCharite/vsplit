import os

from .data import data_factory  # noqa: F401


def test_data_factory(data_factory):  # noqa: F811
    filename = data_factory("hello world")

    with open(filename) as f:
        assert f.read(5) == "hello"
        assert f.tell() == 5
        f.seek(6, os.SEEK_SET)
        assert f.read() == "world"
        assert f.tell() == 11

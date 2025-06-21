import os


def test_data_factory(data_factory):
    filename = data_factory("hello world")

    with open(filename) as f:
        assert f.read(5) == "hello"
        assert f.tell() == 5
        f.seek(6, os.SEEK_SET)
        assert f.read() == "world"
        assert f.tell() == 11

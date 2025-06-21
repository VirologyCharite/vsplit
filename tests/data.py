import pytest


@pytest.fixture(scope="session")
def data_factory(tmp_path_factory):
    def data_file(data: str | bytes = "", filename: str | None = None):
        path = tmp_path_factory.mktemp("base") / (filename or "file")
        mode = "wt" if isinstance(data, str) else "wb"
        with open(path, mode) as fp:
            fp.write(data)
        return path

    return data_file

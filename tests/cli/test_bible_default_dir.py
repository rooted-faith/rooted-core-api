"""dump-bible and import-bible must share one default data directory."""

from portal.cli.constants import DEFAULT_BIBLE_DATA_DIR
from portal.cli.main import cli


def _default(command_name: str, option: str):
    params = {p.name: p for p in cli.commands[command_name].params}
    return params[option].default


def test_dump_and_import_share_default_dir():
    assert _default("dump-bible", "out") == DEFAULT_BIBLE_DATA_DIR
    assert _default("import-bible", "data_dir") == DEFAULT_BIBLE_DATA_DIR

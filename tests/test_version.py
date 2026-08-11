from crate_builder.version import get_version


def test_returns_dev_when_no_version_file(tmp_path):
    assert get_version(str(tmp_path)) == "dev"


def test_reads_stamped_version(tmp_path):
    (tmp_path / "VERSION").write_text("v0.6.1\n")
    assert get_version(str(tmp_path)) == "v0.6.1"


def test_blank_file_falls_back_to_dev(tmp_path):
    (tmp_path / "VERSION").write_text("   \n")
    assert get_version(str(tmp_path)) == "dev"

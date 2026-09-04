from pathlib import Path


def test_project_layout_and_package_import():
    project_root = Path(__file__).parents[1]

    assert (project_root / "src" / "portalconnect").is_dir()
    assert (project_root / "tests").is_dir()

    import portalconnect

    assert portalconnect.__version__ == "0.1.0"

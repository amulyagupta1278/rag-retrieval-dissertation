import pytest

from src.evaluation.holdout_lock import create_lock, verify_lock


def test_holdout_lock_detects_configuration_mutation(tmp_path):
    (tmp_path / "src").mkdir()
    code = tmp_path / "src/system.py"
    code.write_text("VALUE = 1\n", encoding="utf-8")
    selection = tmp_path / "selection.json"
    selection.write_text('{"selected":"baseline"}\n', encoding="utf-8")
    lock_path = tmp_path / "lock.json"
    create_lock(tmp_path, ["src"], ["selection.json"], lock_path)
    verify_lock(lock_path, tmp_path)
    code.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="changed: src/system.py"):
        verify_lock(lock_path, tmp_path)


def test_holdout_lock_detects_new_system_file(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/system.py").write_text("VALUE = 1\n", encoding="utf-8")
    selection = tmp_path / "selection.json"
    selection.write_text("{}\n", encoding="utf-8")
    lock_path = tmp_path / "lock.json"
    create_lock(tmp_path, ["src"], ["selection.json"], lock_path)
    (tmp_path / "src/new_retriever.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="new tracked file"):
        verify_lock(lock_path, tmp_path)

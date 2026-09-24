from tools.check_mfw_resources import load_pipeline_nodes


def test_pipeline_loader_ignores_binary_appledouble_sidecar(tmp_path):
    (tmp_path / "entry.json").write_text('{"entry": {"action": "DoNothing"}}')
    (tmp_path / "._entry.json").write_bytes(b"\x00\x05\x16\x07\xff")
    assert load_pipeline_nodes(tmp_path) == {"entry": {"action": "DoNothing"}}

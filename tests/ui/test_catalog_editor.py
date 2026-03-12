from PyQt6.QtCore import Qt

from pmgen.ui.catalog_editor import CanonMappingsTab, CatalogEditorWindow


def test_catalog_editor_is_frameless(qtbot):
    window = CatalogEditorWindow(icon_dir="", parent=None)
    qtbot.addWidget(window)

    assert bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)


class _FakeMappingsDB:
    def __init__(self, mappings):
        self._mappings = mappings

    def get_mappings(self):
        return list(self._mappings)

    def add_mapping(self, pattern, template):
        self._mappings.append((9999, pattern, template))

    def update_mapping(self, mapping_id, pattern, template):
        for index, (mid, _pattern, _template) in enumerate(self._mappings):
            if mid == mapping_id:
                self._mappings[index] = (mid, pattern, template)
                return

    def delete_mapping(self, mapping_id):
        self._mappings = [m for m in self._mappings if m[0] != mapping_id]


def test_canon_mappings_tab_validates_builtin_tokens(qtbot):
    db = _FakeMappingsDB(
        [
            (1, r"^DRUM{SPC}{LP}{COLOR}{RP}$", "DRUM[{chan}]"),
        ]
    )
    tab = CanonMappingsTab(db=db, icon_dir="", parent=None)
    qtbot.addWidget(tab)

    assert tab._validate() is None


def test_canon_mappings_tab_rejects_unknown_token(qtbot):
    db = _FakeMappingsDB(
        [
            (1, r"^DRUM{SPC}{MISSING_TOKEN}$", "DRUM[{chan}]"),
        ]
    )
    tab = CanonMappingsTab(db=db, icon_dir="", parent=None)
    qtbot.addWidget(tab)

    err = tab._validate()
    assert err is not None
    assert "Unknown regex token" in err


def test_canon_mappings_tab_global_tester_finds_first_match(qtbot):
    db = _FakeMappingsDB(
        [
            (1, r"^DRUM{SPC}{LP}{COLOR}{RP}$", "DRUM[{chan}]"),
            (2, r"^DRUM$", "DRUM[K]"),
        ]
    )
    tab = CanonMappingsTab(db=db, icon_dir="", parent=None)
    qtbot.addWidget(tab)

    tab.test_input.setText("DRUM (K)")
    tab._run_global_test()

    out = tab.test_result.toPlainText()
    assert "Matched row: 1" in out
    assert "Output: DRUM[K]" in out

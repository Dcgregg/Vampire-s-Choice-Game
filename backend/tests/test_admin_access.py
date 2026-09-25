import pytest

from admin_access import configured_admin_emails, is_admin_email


def test_admin_allow_list_is_normalised_and_fail_closed():
    allowed = configured_admin_emails(" Admin@Example.com, editor@example.com, invalid ")
    assert allowed == {"admin@example.com", "editor@example.com"}
    assert is_admin_email("ADMIN@example.com", allowed)
    assert not is_admin_email("viewer@example.com", allowed)
    assert not is_admin_email(None, allowed)
    assert not is_admin_email("admin@example.com", configured_admin_emails(None))


def test_server_admin_guard_requires_exact_allow_listed_email(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase7_admin_guard_test")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        server._require_admin({"email": "ADMIN@example.com"})
        with pytest.raises(server.HTTPException) as denied:
            server._require_admin({"email": "viewer@example.com"})
        assert denied.value.status_code == 403
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_admin_draft_validation_is_bounded_and_rejects_unknown_fields(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase8_admin_draft_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        valid = server.AdminDraftInput(
            bookId="book2", title="The Ashen Court", synopsis="A short premise.", branchNotes="Two routes meet at the finale.",
        )
        assert valid.bookId == "book2"
        with pytest.raises(Exception):
            server.AdminDraftInput(bookId="book2", title="x", synopsis="", branchNotes="", unexpected=True)
        with pytest.raises(Exception):
            server.AdminDraftInput(bookId="book2", title="x" * 161, synopsis="", branchNotes="")
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_manual_scenes_reject_duplicate_identifiers(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase11_manual_scenes_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        scene = server.AdminSceneInput(sceneId="arrival", chapterNumber=1, title="Arrival", body="The gate opens.", choices=[])
        with pytest.raises(server.HTTPException) as duplicate_scenes:
            server._validate_manual_scenes([scene, scene])
        assert duplicate_scenes.value.status_code == 422
        duplicate_choices = server.AdminSceneInput(sceneId="hall", chapterNumber=1, title="The hall", body="Candles burn.", choices=[server.AdminChoiceInput(choiceId="go", text="Go", nextSceneId="arrival"), server.AdminChoiceInput(choiceId="go", text="Stay", nextSceneId=None)])
        with pytest.raises(server.HTTPException) as duplicate_choices_error:
            server._validate_manual_scenes([duplicate_choices])
        assert duplicate_choices_error.value.status_code == 422
    finally:
        server.client.close()
        sys.modules.pop("server", None)

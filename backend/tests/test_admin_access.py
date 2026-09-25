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


def test_story_tokens_are_allow_listed_in_manual_drafts(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase20_story_tokens_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        allowed = server.AdminSceneInput(sceneId="arrival", chapterNumber=1, title="Welcome, {{player.name}}", body="{{player.subject}} follows the candlelight.", choices=[server.AdminChoiceInput(choiceId="go", text="Trust {{player.object}} instincts", nextSceneId=None)])
        server._validate_manual_scenes([allowed])
        unknown = server.AdminSceneInput(sceneId="unknown", chapterNumber=1, title="Unknown", body="{{player.secret}}", choices=[])
        with pytest.raises(server.HTTPException) as error:
            server._validate_manual_scenes([unknown])
        assert error.value.status_code == 422
        assert error.value.detail["error"] == "unknown_story_token"
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_generated_draft_normalises_common_free_model_variations(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase13_generation_normalisation_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        raw = {
            "title": "Vamp: To Be or Not to Be?",
            "summary": "A dangerous new science teacher arrives at Blackthorn Academy.",
            "notes": "Two routes lead toward a midnight decision.",
            "scenes": [
                {"id": "arrival scene", "title": "The First Lesson", "content": "A stranger enters the laboratory.", "choices": [{"id": "listen!", "label": "Listen closely.", "destination": "the hall"}]},
                {"id": "the hall", "title": "After the Bell", "text": "He waits in the candlelit hall.", "choices": [{"id": "follow", "text": "Follow him.", "next": "midnight"}]},
                {"id": "midnight", "title": "The Choice", "body": "The final bell sounds.", "choices": []},
            ],
        }
        generated = server.AdminGeneratedDraft.model_validate(server._normalise_generated_draft(raw))
        assert [scene.chapterNumber for scene in generated.scenes] == [1, 1, 1]
        assert generated.scenes[0].sceneId == "arrival-scene"
        assert generated.scenes[0].choices[0].nextSceneId == "the-hall"
        assert generated.synopsis.startswith("A dangerous")
        server._validate_manual_scenes(generated.scenes)
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_review_export_is_explicitly_non_player_facing(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase14_review_export_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        draft = {
            "draftId": "draft_" + "a" * 32, "bookId": "book2", "title": "The Review", "synopsis": "A sufficiently long synopsis for an editorial export test.",
            "branchNotes": "Sufficiently long notes for the editorial export test.", "scenes": [], "revision": 3, "status": "ready_for_review",
            "createdAt": "2026-01-01T00:00:00+00:00", "updatedAt": "2026-01-01T00:00:00+00:00", "updatedBy": "admin@example.com",
        }
        exported = server._review_export(draft)
        assert exported["format"] == "vampires-choice-review-export/v1"
        assert exported["source"] == {"draftId": draft["draftId"], "revision": 3, "status": "ready_for_review"}
        assert exported["publication"]["published"] is False
        assert exported["draft"]["title"] == "The Review"
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_future_book_drafts_are_valid_review_candidates(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase14_future_book_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        draft = {
            "bookId": "book3", "title": "Vamp", "synopsis": "A future-book draft with a suitably complete synopsis for review.",
            "branchNotes": "A future-book draft with sufficiently detailed branching notes for review.", "scenes": [],
        }
        issues = server._admin_draft_validation_issues(draft)
        assert not any(issue["code"] in {"unknown_book", "invalid_book_id"} for issue in issues)
        draft["bookId"] = "future-book"
        assert any(issue["code"] == "invalid_book_id" for issue in server._admin_draft_validation_issues(draft))
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_public_draft_includes_optional_release_approval(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase15_approval_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        draft = {"draftId": "draft_" + "b" * 32, "bookId": "book3", "title": "Vamp", "synopsis": "A suitable synopsis.", "branchNotes": "Suitable notes.", "scenes": [], "status": "approved_for_release", "revision": 4, "createdAt": "now", "updatedAt": "now", "updatedBy": "admin@example.com", "reviewApproval": {"approvedAt": "now", "approvedBy": "admin@example.com", "approvedRevision": 3}}
        public = server._public_admin_draft(draft)
        assert public["status"] == "approved_for_release"
        assert public["reviewApproval"]["approvedRevision"] == 3
        assert public["reviewHistory"] == [draft["reviewApproval"]]
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_draft_graph_finds_unreachable_and_non_terminating_routes(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase17_graph_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        draft = {"scenes": [
            {"sceneId": "start", "choices": [{"nextSceneId": "loop"}]},
            {"sceneId": "loop", "choices": [{"nextSceneId": "start"}]},
            {"sceneId": "orphan", "choices": []},
        ]}
        report = server._draft_graph_report(draft)
        assert report["unreachableSceneIds"] == ["orphan"]
        assert report["terminalSceneIds"] == ["orphan"]
        assert report["nonTerminatingSceneIds"] == ["start", "loop"]
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_approved_release_package_has_stable_checksum(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase19_package_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        draft = {"draftId": "draft_" + "c" * 32, "bookId": "book3", "title": "Vamp", "synopsis": "A suitable synopsis.", "branchNotes": "Suitable notes.", "scenes": [], "status": "approved_for_release", "revision": 3, "createdAt": "now", "updatedAt": "now", "updatedBy": "admin@example.com", "reviewApproval": {"approvedAt": "now", "approvedBy": "admin@example.com", "approvedRevision": 2}}
        package = server._release_package(draft)
        assert package["format"] == "vampires-choice-release-package/v1"
        assert len(package["manifest"]["sha256"]) == 64
        assert package["manifest"]["published"] is False
    finally:
        server.client.close()
        sys.modules.pop("server", None)


def test_book_json_import_converts_engine_scenes_to_private_draft(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "phase17_json_import_test")
    import importlib
    import sys
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    try:
        content = {"book": {"id": "book3", "title": "Imported", "synopsis": "A sufficiently complete imported synopsis for the draft workflow.", "subtitle": "Enough branch notes for this private editorial import."}, "scenes": [
            {"id": "start", "chapterNumber": 1, "sceneTitle": "Start", "paragraphs": ["The story begins."], "choices": [{"id": "go", "text": "Continue", "nextSceneId": "middle"}]},
            {"id": "middle", "chapterNumber": 1, "sceneTitle": "Middle", "paragraphs": ["The story deepens."], "choices": [{"id": "end", "text": "End", "nextSceneId": "ending"}]},
            {"id": "ending", "chapterNumber": 1, "sceneTitle": "End", "paragraphs": ["The route concludes."], "choices": []},
        ]}
        imported = server._import_book_json(content)
        assert imported["bookId"] == "book3"
        assert imported["scenes"][0]["body"] == "The story begins."
        assert imported["scenes"][2]["choices"] == []
    finally:
        server.client.close()
        sys.modules.pop("server", None)

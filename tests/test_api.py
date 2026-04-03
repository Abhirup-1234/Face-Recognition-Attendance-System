"""
API endpoint tests — auth, students, attendance, settings, audit.
"""
import pytest
import json


class TestAuth:

    def test_login_success(self, client):
        resp = client.post("/login", json={
            "username": "admin", "password": "testpass123"
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["ok"] is True

    def test_login_wrong_password(self, client):
        resp = client.post("/login", json={
            "username": "admin", "password": "wrongpass"
        })
        assert resp.status_code == 401

    def test_login_wrong_username(self, client):
        resp = client.post("/login", json={
            "username": "notadmin", "password": "testpass123"
        })
        assert resp.status_code == 401

    def test_protected_route_without_auth(self, client):
        resp = client.get("/api/students")
        assert resp.status_code == 401

    def test_auth_status_logged_in(self, authed_client):
        resp = authed_client.get("/api/auth/status")
        data = resp.get_json()
        assert data["logged_in"] is True
        assert data["username"] == "admin"

    def test_auth_status_not_logged_in(self, client):
        resp = client.get("/api/auth/status")
        data = resp.get_json()
        assert data["logged_in"] is False

    def test_logout(self, authed_client):
        resp = authed_client.get("/logout")
        assert resp.status_code == 200
        # Should be logged out now
        resp2 = authed_client.get("/api/students")
        assert resp2.status_code == 401


class TestStudentAPI:

    def test_list_students_empty(self, authed_client, fresh_db):
        resp = authed_client.get("/api/students")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_students_with_data(self, authed_client, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.add_student("S002", "Priya", "X", "", "A", 2)
        resp = authed_client.get("/api/students")
        data = resp.get_json()
        assert len(data) == 2

    def test_delete_student(self, authed_client, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        resp = authed_client.delete("/api/students/S001")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert fresh_db.get_student("S001") is None


class TestAttendanceAPI:

    def test_get_attendance_empty(self, authed_client, fresh_db):
        resp = authed_client.get("/api/attendance?date=2026-01-01")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_clear_attendance(self, authed_client, fresh_db):
        from datetime import date
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        today_str = date.today().isoformat()
        resp = authed_client.delete(f"/api/attendance/clear?date={today_str}")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_clear_all_attendance(self, authed_client, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        resp = authed_client.delete("/api/attendance/clear_all")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestClassesAPI:

    def test_list_classes(self, authed_client, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("V", "A", "")
        resp = authed_client.get("/api/classes")
        data = resp.get_json()
        assert data == ["V", "X"]  # Canonical order

    def test_add_class(self, authed_client, fresh_db):
        resp = authed_client.post("/api/classes",
                                  json={"name": "VIII"},
                                  content_type="application/json")
        assert resp.status_code == 200
        classes = authed_client.get("/api/classes").get_json()
        assert "VIII" in classes

    def test_delete_class(self, authed_client, fresh_db):
        fresh_db.add_section("X", "A", "")
        resp = authed_client.delete("/api/classes/X")
        assert resp.status_code == 200
        classes = authed_client.get("/api/classes").get_json()
        assert "X" not in classes


class TestSectionsAPI:

    def test_list_sections(self, authed_client, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("X", "B", "")
        resp = authed_client.get("/api/sections?class=X")
        data = resp.get_json()
        assert data == ["A", "B"]

    def test_add_section(self, authed_client, fresh_db):
        resp = authed_client.post("/api/sections",
                                  json={"class_name": "X", "section": "C"},
                                  content_type="application/json")
        assert resp.status_code == 200
        secs = authed_client.get("/api/sections?class=X").get_json()
        assert "C" in secs


class TestSettingsAPI:

    def test_get_settings(self, authed_client):
        resp = authed_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "REC_THRESHOLD" in data
        assert "DET_THRESH" in data

    def test_save_settings(self, authed_client):
        resp = authed_client.post("/api/settings",
                                  json={"REC_THRESHOLD": 0.50},
                                  content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestAuditAPI:

    def test_audit_log_records_login(self, authed_client, fresh_db):
        # Login was already done by authed_client fixture
        resp = authed_client.get("/api/audit")
        data = resp.get_json()
        assert any(log["action"] == "LOGIN" for log in data)

    def test_audit_log_records_delete(self, authed_client, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        authed_client.delete("/api/students/S001")
        resp = authed_client.get("/api/audit")
        data = resp.get_json()
        assert any(log["action"] == "DELETE_STUDENT" for log in data)


class TestPasswordChange:

    def test_password_too_short(self, authed_client):
        resp = authed_client.post("/api/settings/password",
                                  json={"password": "ab"},
                                  content_type="application/json")
        assert resp.status_code == 400

    def test_password_change_success(self, authed_client):
        resp = authed_client.post("/api/settings/password",
                                  json={"password": "newpass123"},
                                  content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

"""
Database layer tests — CRUD for students, attendance, classes, sections, audit log.
"""
import pytest
from datetime import date


class TestStudents:

    def test_add_and_get_student(self, fresh_db):
        fresh_db.add_student("S001", "Arjun Sharma", "X", "", "A", 1, "")
        s = fresh_db.get_student("S001")
        assert s is not None
        assert s["name"] == "Arjun Sharma"
        assert s["class_name"] == "X"
        assert s["section"] == "A"
        assert s["roll_no"] == 1

    def test_list_students(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.add_student("S002", "Priya", "X", "", "A", 2)
        fresh_db.add_student("S003", "Ravi", "IX", "", "A", 1)
        all_students = fresh_db.list_students()
        assert len(all_students) == 3

        class_x = fresh_db.list_students(class_name="X")
        assert len(class_x) == 2

    def test_list_students_by_section(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.add_student("S002", "Priya", "X", "", "B", 1)
        sec_a = fresh_db.list_students(class_name="X", section="A")
        assert len(sec_a) == 1
        assert sec_a[0]["name"] == "Arjun"

    def test_delete_student_soft(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.delete_student("S001")
        # Soft delete — student should not appear in list
        assert fresh_db.get_student("S001") is None
        assert len(fresh_db.list_students()) == 0

    def test_upsert_student(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.add_student("S001", "Arjun Kumar", "XI", "Science", "A", 5)
        s = fresh_db.get_student("S001")
        assert s["name"] == "Arjun Kumar"
        assert s["class_name"] == "XI"
        assert s["stream"] == "Science"

    def test_stream_students(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "XI", "Science", "A", 1)
        fresh_db.add_student("S002", "Priya", "XI", "Commerce", "A", 1)
        sci = fresh_db.list_students(class_name="XI", stream="Science")
        assert len(sci) == 1
        assert sci[0]["name"] == "Arjun"


class TestAttendance:

    def test_mark_and_query(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        ok = fresh_db.mark_attendance("S001", "CAM-101", 0.65)
        assert ok is True
        today_str = date.today().isoformat()
        records = fresh_db.get_attendance_by_date(today_str)
        assert len(records) == 1
        assert records[0]["student_id"] == "S001"
        assert records[0]["confidence"] == pytest.approx(0.65, abs=0.01)

    def test_mark_nonexistent_student(self, fresh_db):
        ok = fresh_db.mark_attendance("GHOST", "CAM-101", 0.5)
        assert ok is False

    def test_was_marked_today(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        assert fresh_db.was_marked_today("S001") is False
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        assert fresh_db.was_marked_today("S001") is True

    def test_clear_attendance_by_date(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        today_str = date.today().isoformat()
        assert len(fresh_db.get_attendance_by_date(today_str)) == 1
        ok = fresh_db.clear_attendance_by_date(today_str)
        assert ok is True
        assert len(fresh_db.get_attendance_by_date(today_str)) == 0

    def test_clear_all_attendance(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        ok = fresh_db.clear_all_attendance()
        assert ok is True
        assert len(fresh_db.get_attendance_by_date(date.today().isoformat())) == 0

    def test_daily_stats(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.add_student("S002", "Priya", "X", "", "A", 2)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        stats = fresh_db.get_daily_stats(date.today().isoformat())
        assert len(stats["classes"]) == 1
        assert stats["classes"][0]["present"] == 1
        assert stats["classes"][0]["total"] == 2
        assert stats["classes"][0]["percentage"] == 50.0

    def test_filter_by_class_and_stream(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "XI", "Science", "A", 1)
        fresh_db.add_student("S002", "Priya", "XI", "Commerce", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        fresh_db.mark_attendance("S002", "CAM-101", 0.5)
        today_str = date.today().isoformat()
        sci = fresh_db.get_attendance_by_date(today_str, class_name="XI", stream="Science")
        assert len(sci) == 1
        assert sci[0]["student_id"] == "S001"


class TestClassSections:

    def test_add_and_list_sections(self, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("X", "B", "")
        secs = fresh_db.list_sections("X", "")
        assert secs == ["A", "B"]

    def test_remove_section(self, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("X", "B", "")
        fresh_db.remove_section("X", "A", "")
        secs = fresh_db.list_sections("X", "")
        assert secs == ["B"]

    def test_stream_sections(self, fresh_db):
        fresh_db.add_section("XI", "A", "Science")
        fresh_db.add_section("XI", "A", "Commerce")
        sci = fresh_db.list_sections("XI", "Science")
        assert sci == ["A"]
        com = fresh_db.list_sections("XI", "Commerce")
        assert com == ["A"]

    def test_duplicate_section_ignored(self, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("X", "A", "")  # Should not error
        secs = fresh_db.list_sections("X", "")
        assert secs == ["A"]

    def test_list_classes(self, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("V", "A", "")
        fresh_db.add_section("I", "A", "")
        classes = fresh_db.list_classes()
        # Should be sorted by canonical school order
        assert classes == ["I", "V", "X"]

    def test_delete_class_sections(self, fresh_db):
        fresh_db.add_section("X", "A", "")
        fresh_db.add_section("X", "B", "")
        ok = fresh_db.delete_class_sections("X")
        assert ok is True
        assert fresh_db.list_sections("X", "") == []

    def test_ensure_default_sections(self, fresh_db):
        fresh_db.ensure_default_sections(["V", "XI"])
        assert fresh_db.list_sections("V", "") == ["A"]
        assert fresh_db.list_sections("XI", "Science") == ["A"]
        assert fresh_db.list_sections("XI", "Commerce") == ["A"]
        assert fresh_db.list_sections("XI", "Humanities") == ["A"]


class TestAuditLog:

    def test_log_and_retrieve(self, fresh_db):
        fresh_db.log_audit("TEST_ACTION", "Some details", "admin")
        logs = fresh_db.get_audit_log(10)
        assert len(logs) == 1
        assert logs[0]["action"] == "TEST_ACTION"
        assert logs[0]["details"] == "Some details"
        assert logs[0]["username"] == "admin"

    def test_audit_ordering(self, fresh_db):
        import time
        fresh_db.log_audit("FIRST", "", "admin")
        time.sleep(0.1)
        fresh_db.log_audit("SECOND", "", "admin")
        logs = fresh_db.get_audit_log(10)
        assert logs[0]["action"] == "SECOND"  # Most recent first
        assert logs[1]["action"] == "FIRST"

    def test_audit_limit(self, fresh_db):
        for i in range(20):
            fresh_db.log_audit(f"ACTION_{i}", "", "admin")
        logs = fresh_db.get_audit_log(5)
        assert len(logs) == 5


class TestResetAll:

    def test_reset_clears_attendance_and_deactivates(self, fresh_db):
        fresh_db.add_student("S001", "Arjun", "X", "", "A", 1)
        fresh_db.mark_attendance("S001", "CAM-101", 0.6)
        ok = fresh_db.reset_all_data()
        assert ok is True
        assert len(fresh_db.get_attendance_by_date(date.today().isoformat())) == 0
        assert fresh_db.get_student("S001") is None  # Deactivated

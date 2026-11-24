"""The app's own login (changedesk_app): it reads the changedesk schema, writes only through the checked functions,
and reaches no other schema. Runs scripts/setup_db.py's own checks; nothing is kept."""
import sys

import pytest
from conftest import REPO, _app_password

sys.path.insert(0, str(REPO / "scripts"))
import setup_db  # noqa: E402


def test_the_app_login_keeps_to_its_reach():
    pw = _app_password()
    if not pw:
        pytest.skip("no local store")
    try:
        results = setup_db.check_limits(setup_db.db_settings(), pw)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local store not reachable ({type(e).__name__})")
    failed = [label for label, ok in results if not ok]
    assert failed == [] and len(results) >= 10


def test_the_password_is_made_safe_for_sql():
    with pytest.raises(ValueError):
        setup_db.role_sql("bad'; drop table x; --")
    sql = setup_db.role_sql("abc_DEF-123")
    assert "grant select on all tables in schema changedesk" in sql and "grant insert" not in sql and "grant update" not in sql

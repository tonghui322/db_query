"""SQL 安全校验的单元测试。不需要数据库和 LLM，只测 sqlglot 校验逻辑。
运行: python -m pytest tests/ -v  或  python tests/test_validator.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.sql_validator import validate_sql, SQLValidationError

ALLOWED = {"customers", "products", "orders", "order_items"}


def _ok(sql, allowed=ALLOWED, limit=1000):
    """应通过，返回规整后 SQL。"""
    return validate_sql(sql, allowed, limit)


def _raises(sql, allowed=ALLOWED):
    """应抛出校验错误。"""
    try:
        validate_sql(sql, allowed, 1000)
    except SQLValidationError as e:
        return e
    raise AssertionError(f"应当被拒绝: {sql}")


def test_select_ok():
    assert "SELECT" in _ok("SELECT * FROM orders WHERE id=1")


def test_limit_appended():
    out = _ok("SELECT * FROM orders WHERE id=1")
    assert "LIMIT 1000" in out


def test_limit_preserved():
    out = _ok("SELECT * FROM orders LIMIT 5")
    assert "LIMIT 5" in out and "LIMIT 1000" not in out


def test_reject_update():
    _raises("UPDATE orders SET status='x' WHERE id=1")


def test_reject_delete():
    _raises("DELETE FROM orders WHERE id=1")


def test_reject_insert():
    _raises("INSERT INTO orders VALUES (1,1,now(),0,'x')")


def test_reject_drop():
    _raises("DROP TABLE orders")


def test_reject_unknown_table():
    _raises("SELECT * FROM secrets")


def test_reject_into_outfile():
    _raises("SELECT * FROM orders INTO OUTFILE '/tmp/x'")


def test_reject_load_file():
    _raises("SELECT LOAD_FILE('/etc/passwd')")


def test_reject_comment_attempt():
    _raises("SELECT * FROM orders -- drop")


def test_markdown_wrapper_stripped():
    # 模型可能返回 ```sql ... ```，校验前已剥离，此处测 validate 本身对裸 SQL 生效
    out = _ok("select count(*) from orders")
    assert out.upper().startswith("SELECT")


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

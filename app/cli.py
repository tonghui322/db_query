"""命令行交互入口：python -m app.cli

启动后直接输入自然语言问题即可查询，Ctrl+C 或输入 exit 退出。
"""
import sys
from tabulate import tabulate

from .config import Config
from .orchestrator import Orchestrator

# Windows 下 stdin 默认按 GBK 解码，管道/某些输入方式读中文会变乱码并混入孤立代理项。
# 强制用 UTF-8，保证所有输入方式（键盘/管道/重定向）读中文都正确。
if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _print_result(q):
    print("\n" + "=" * 60)
    print(f"问题: {q.question}")
    print(f"生成SQL: {q.sql}")
    print("-" * 60)
    if q.exec_result and q.exec_result["columns"]:
        cols = q.exec_result["columns"]
        rows = q.exec_result["rows"]
        print(tabulate(rows, headers=cols, tablefmt="grid"))
        if len(rows) >= 50:
            print(f"(共 {q.exec_result['row_count']} 行，仅展示前 50 行)")
    print("-" * 60)
    print("回答: " + q.answer)
    print("=" * 60 + "\n")


def main():
    try:
        cfg = Config.from_env()
        orch = Orchestrator(cfg)
    except Exception as e:
        print(f"[启动失败] {e}")
        print("提示：请复制 .env.example 为 .env 并填写数据库连接和 LLM API Key。")
        sys.exit(1)

    print(f"已连接数据库 {cfg.db_name}，加载 {len(orch.tables)} 张表。")
    print("请输入自然语言问题（输入 exit 退出）:\n")

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "退出"):
            print("再见。")
            break
        try:
            q = orch.query(question)
            _print_result(q)
        except Exception as e:
            print(f"\n[出错] {e}\n")


if __name__ == "__main__":
    main()

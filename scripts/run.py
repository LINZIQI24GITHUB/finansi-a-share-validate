#!/usr/bin/env python3
"""样本外验证：把区间切成训练/测试段，看策略在没见过的数据上还剩多少。

    python scripts/run.py run --code 300750 --start 2022-01-01 --end 2025-12-31 \
        --signal ma_cross --params fast=5,slow=20 --train 252 --test 63
    python scripts/run.py demo
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
for candidate in (os.getenv("ASHARE_LIB"),
                  SKILL_DIR.parents[1] / "lib" if len(SKILL_DIR.parents) > 1 else None,
                  SKILL_DIR / "lib"):
    if candidate and Path(candidate).is_dir() and (Path(candidate) / "ashare_core").is_dir():
        sys.path.insert(0, str(candidate))
        break

from ashare_core import rulespec, signals, validate  # noqa: E402
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402


def _default_data_dir() -> Path:
    env = os.getenv("ASHARE_DATA")
    if env:
        return Path(env)
    pack_data = SKILL_DIR.parents[1] / "data" if len(SKILL_DIR.parents) > 1 else None
    if pack_data and (pack_data.exists() or (SKILL_DIR.parents[1] / "lib").exists()):
        return pack_data
    return Path.home() / ".ashare" / "data"


DATA = _default_data_dir()


def resolve_code(raw: str, provider=None) -> str:
    s = str(raw).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits and len(digits) <= 6:
        return digits.zfill(6)
    if provider is None:
        raise SystemExit(f"✗ 请用 6 位代码：{raw}")
    lst = provider.stock_list()
    hit = lst[lst["name"] == s]
    if hit.empty or len(hit) > 1:
        raise SystemExit(f"✗ 无法唯一确定「{s}」")
    return str(hit.iloc[0]["code"])


def load(code: str, start: str, end: str):
    with EltdxProvider() as p:
        cache = BarsCache(p, DATA)
        resolved = resolve_code(code, p)
        hfq = cache.get(resolved, start, end, "hfq")
        raw = cache.get(resolved, start, end, "none")
    if hfq.empty or raw.empty:
        raise SystemExit("✗ 取数失败")
    first = str(hfq["date"].iloc[0])
    raw0 = raw[raw["date"] == first]["close"]
    if raw0.empty:
        raise SystemExit("✗ 无法锚定首日真实价")
    scale = float(raw0.iloc[0]) / float(hfq["close"].iloc[0])
    df = hfq.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = (df[col] * scale).round(2)
    return resolved, df, scale


def parse_params(raw: str | None) -> dict:
    out: dict = {}
    for chunk in (raw or "").split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        v = v.strip()
        out[k.strip()] = int(v) if v.lstrip("-").isdigit() else float(v)
    return out


def build_signal(df, args):
    if args.rule:
        spec = rulespec.load(args.rule)
        return rulespec.build_position(df, spec), rulespec.describe(spec)
    params = parse_params(args.params)
    sig = signals.build(args.signal, df, **params)
    return sig, f"{args.signal} {params or '默认参数'}"


def cmd_run(args) -> int:
    code, df, scale = load(args.code, args.start, args.end)
    sig, label = build_signal(df, args)
    folds = validate.walk_forward(df, sig, code, train=args.train, test=args.test, cash=args.cash)
    if not folds:
        raise SystemExit(f"✗ 区间太短：{len(df)} 根，无法切出训练 {args.train} + 测试 {args.test}")

    head = (f"{'段':>3} {'训练区间':<24}{'测试区间':<24}"
            f"{'夏普(内)':>9}{'夏普(外)':>9}{'收益(内)':>9}{'收益(外)':>9}{'笔数(外)':>8}")
    print("─" * 96)
    print(f"  {code} · {label} · 训练 {args.train} 根 / 测试 {args.test} 根 · 共 {len(folds)} 段")
    print("─" * 96)
    print(head)
    for f in folds:
        print(f"{f.index:>3} {f.train_start}~{f.train_end}  {f.test_start}~{f.test_end}  "
              f"{f.is_sharpe:>9.2f}{f.oos_sharpe:>9.2f}{f.is_return*100:>8.1f}%{f.oos_return*100:>8.1f}%"
              f"{f.oos_trades:>8}")
    print("─" * 96)

    conclusion, reason = validate.verdict(folds)
    print(f"  结论：{conclusion}")
    print(f"  理由：{reason}")
    print(f"  口径：后复权 × {scale:.4f}（锚定首日真实价）；每月 21 个交易日约为一「月」")

    if args.json:
        print(json.dumps({"code": code, "label": label, "verdict": conclusion, "reason": reason,
                          "folds": [vars(f) for f in folds]}, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_demo(args) -> int:
    code, df, _ = load("300750", "2022-01-01", "2025-12-31")
    sig = signals.build("ma_cross", df, fast=5, slow=20)
    folds = validate.walk_forward(df, sig, code, train=252, test=63)
    conclusion, reason = validate.verdict(folds)

    checks = [
        ("切出 ≥ 3 段", len(folds) >= 3, f"{len(folds)} 段"),
        ("每段都有测试期交易", all(f.oos_trades >= 0 for f in folds), "是"),
        ("结论非空", bool(conclusion), conclusion),
        ("样本外收益有正有负", any(f.oos_return > 0 for f in folds) and any(f.oos_return <= 0 for f in folds),
         f"{sum(1 for f in folds if f.oos_return > 0)}/{len(folds)} 段为正"),
    ]
    print("离线自检：300750 均线 5/20 滚动验证（2022-2025）")
    passed = 0
    for name, ok, detail in checks:
        passed += ok
        print(f"  {'✓' if ok else '✗'} {name}：{detail}")
    print(f"\n  结论：{conclusion}｜{reason}")
    total = len(checks)
    print(f"\n{'✓ 通过' if passed == total else '✗ 未通过'}（{passed}/{total}）")
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="A 股样本外验证")
    ap.add_argument("--data-dir", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="滚动切分验证")
    r.add_argument("--code", required=True)
    r.add_argument("--start", required=True)
    r.add_argument("--end", required=True)
    r.add_argument("--signal", default="ma_cross", choices=list(signals.SIGNALS))
    r.add_argument("--params", default=None)
    r.add_argument("--rule", default=None, help="规则 JSON（与 backtest 同一套）")
    r.add_argument("--train", type=int, default=252)
    r.add_argument("--test", type=int, default=63)
    r.add_argument("--cash", type=float, default=100_000.0)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("demo", help="离线自检")
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args()
    if args.data_dir:
        global DATA
        DATA = Path(args.data_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

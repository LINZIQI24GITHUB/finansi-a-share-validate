# A股样本外验证

**A股样本外验证**：把历史区间切成连续的训练/测试段滚动回测，比较样本内与样本外的夏普和收益，判断一套参数是真有边际，还是拟合了历史。

## 安装

```bash
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-validate.git
```

放到 Agent 的 skills 目录：

```text
Claude Code   ~/.claude/skills/finansi-a-share-validate/
Codex         ~/.codex/skills/finansi-a-share-validate/
Cursor        ~/.cursor/skills/finansi-a-share-validate/
通用           ~/.agents/skills/finansi-a-share-validate/
```

依赖：

```bash
cd finansi-a-share-validate
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

## 快速开始

```bash
python scripts/run.py run \
  --code 300750 --start 2022-01-01 --end 2025-12-31 \
  --signal ma_cross --params fast=5,slow=20
```

默认训练窗口 252 根、测试窗口 63 根，可以调整：

```bash
python scripts/run.py run --code 300750 --start 2022-01-01 --end 2025-12-31 \
  --signal ma_cross --params fast=5,slow=20 --train 252 --test 63
```

也可以直接用 Agent：

```text
用 finansi-a-share-validate 验证宁德时代 5/20 均线是不是过拟合了，2022 到 2025。
```

## 输出

- 每段训练期/测试期的夏普、收益和交易次数
- 样本内与样本外的对比
- 结论：相对稳健 / 疑似过拟合 / 不稳定 / 样本外失效
- 失败段和有效段的数量

## 判断逻辑

不是看“样本外平均收益是否为正”，而是看：

- 样本外为正的段数比例
- 样本外收益是否被少数大亏段拉负
- 样本内和样本外的夏普是否同向
- 参数在滚动窗口里是否稳定

## 边界

- 只做日频、单标的、多头；不做组合验证。
- 滚动切分不是未来函数，但仍受数据质量和复权口径影响。
- 结果不能证明策略未来会赚钱，只能说明历史样本外是否稳定。
- 不构成投资建议。

## License

MIT. See [LICENSE](LICENSE).

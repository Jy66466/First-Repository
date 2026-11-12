"""BA-CH02-12 核心：桑基图流数据计算。

教材 PBIX（六类分析方法PowerBI-参考答案08.pbix 的“l流向分析-桑基图2”查询）
经 Power BI Desktop 实测验证：

- 模型缓存 15 条“来源 → 目标 → 流量”边，与教材源工作簿
  ``6桑吉图.xlsx`` Sheet1 的 15 行逐边一致（ID、来源、目标、流量均相同）；
- 桑基图视觉对象为第三方自定义视觉（SankeyDiagram.pbiviz），其渲染属于
  Power BI 运行时行为，本实验只迁移**流数据的可验证计算**：
  节点流出、流入、净流量与层级（自来源节点的最短距离）。

口径：

- 边流量为预先给定的聚合值（教材数据本身就是聚合后的边），实验不做
  再聚合，只做按节点的派生汇总与结构校验；
- 层级定义：入度为 0 的节点为第 0 层，其余节点为
  ``max(前驱层级) + 1``；存在环时抛出异常。
"""

from __future__ import annotations

import pandas as pd

__all__ = ["load_flow_edges", "node_flow_summary", "node_levels", "validate_edges"]

_REQUIRED = {"来源", "目标", "流量"}


def load_flow_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """规范化边表：校验必需列与取值，流量转数值。"""
    missing = _REQUIRED - set(frame.columns)
    if missing:
        raise KeyError(f"edges missing columns: {sorted(missing)}")
    frame = frame.copy()
    frame["流量"] = pd.to_numeric(frame["流量"], errors="raise")
    if (frame["流量"] <= 0).any():
        raise ValueError("flow values must be positive")
    if frame["来源"].isna().any() or frame["目标"].isna().any():
        raise ValueError("source/target must not be null")
    if (frame["来源"].astype(str).str.strip() == frame["目标"].astype(str).str.strip()).any():
        raise ValueError("self-loop edges are not allowed")
    frame["来源"] = frame["来源"].astype(str).str.strip()
    frame["目标"] = frame["目标"].astype(str).str.strip()
    return frame.reset_index(drop=True)


def validate_edges(edges: pd.DataFrame) -> dict[str, object]:
    """结构校验摘要：边数、节点数、是否可达所有非源节点、是否存在环。"""
    nodes = set(edges["来源"]) | set(edges["目标"])
    sources = set(edges["来源"]) - set(edges["目标"])
    adjacency: dict[str, list[str]] = {}
    for s, t in zip(edges["来源"], edges["目标"]):
        adjacency.setdefault(s, []).append(t)
    # DFS 检测环
    state: dict[str, int] = {}

    def dfs(n: str) -> bool:
        state[n] = 1
        for nxt in adjacency.get(n, []):
            if state.get(nxt, 0) == 1:
                return True
            if state.get(nxt, 0) == 0 and dfs(nxt):
                return True
        state[n] = 2
        return False

    has_cycle = any(dfs(n) for n in list(adjacency) if state.get(n, 0) == 0)
    return {
        "edges": int(len(edges)),
        "nodes": len(nodes),
        "pure_sources": len(sources),
        "has_cycle": has_cycle,
        "total_flow": float(edges["流量"].sum()),
    }


def node_flow_summary(edges: pd.DataFrame) -> pd.DataFrame:
    """按节点汇总流出、流入与净流量（流出-流入）。

    纯来源节点流入为 0，纯汇节点流出为 0；缺失方向记 0。
    """
    out = edges.groupby("来源")["流量"].sum().rename("流出")
    inn = edges.groupby("目标")["流量"].sum().rename("流入")
    result = pd.concat([out, inn], axis=1).fillna(0.0)
    result["净流量"] = result["流出"] - result["流入"]
    result = result.reset_index().rename(columns={"index": "节点"})
    return result.sort_values("净流量", ascending=False).reset_index(drop=True)


def node_levels(edges: pd.DataFrame) -> dict[str, int]:
    """节点层级：入度为 0 的节点为 0 层，其余为 max(前驱层级)+1。

    存在环时抛出 ValueError。
    """
    check = validate_edges(edges)
    if check["has_cycle"]:
        raise ValueError("edges contain a cycle; levels are undefined")
    nodes = set(edges["来源"]) | set(edges["目标"])
    preds: dict[str, list[str]] = {}
    for s, t in zip(edges["来源"], edges["目标"]):
        preds.setdefault(t, []).append(s)
    levels: dict[str, int] = {}
    remaining = set(nodes)
    while remaining:
        progressed = False
        for n in sorted(remaining):
            ps = preds.get(n, [])
            if not ps:
                levels[n] = 0
                remaining.discard(n)
                progressed = True
            elif all(p in levels for p in ps):
                levels[n] = max(levels[p] for p in ps) + 1
                remaining.discard(n)
                progressed = True
        if not progressed:
            raise ValueError("unable to resolve node levels")
    return dict(sorted(levels.items(), key=lambda kv: (kv[1], kv[0])))

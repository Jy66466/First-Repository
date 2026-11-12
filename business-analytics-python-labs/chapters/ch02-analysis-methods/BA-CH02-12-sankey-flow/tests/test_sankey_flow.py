from __future__ import annotations

import pandas as pd
import pytest

from sankey_flow import (
    load_flow_edges,
    node_flow_summary,
    node_levels,
    validate_edges,
)


@pytest.fixture()
def edges() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID": [2, 3, 4, 5, 6, 7, 8, 9],
            "来源": ["首页", "首页", "首页", "产品页", "产品页", "关于我们", "联系我们", "博客页"],
            "目标": ["产品页", "关于我们", "联系我们", "服务页", "博客页", "常见问题", "表单页", "成功案例"],
            "流量": [800, 700, 300, 300, 250, 200, 100, 150],
        }
    )


def test_load_flow_edges_normalizes_and_validates():
    frame = pd.DataFrame(
        {"来源": [" A ", "A"], "目标": ["B", "B"], "流量": ["10", 5]}
    )
    result = load_flow_edges(frame)
    assert result["流量"].tolist() == [10.0, 5.0]
    assert result["来源"].tolist() == ["A", "A"]


def test_load_flow_edges_rejects_bad_input():
    with pytest.raises(KeyError):
        load_flow_edges(pd.DataFrame({"x": [1]}))
    with pytest.raises(ValueError):
        load_flow_edges(pd.DataFrame({"来源": ["A"], "目标": ["A"], "流量": [5]}))
    with pytest.raises(ValueError):
        load_flow_edges(pd.DataFrame({"来源": ["A"], "目标": ["B"], "流量": [-1]}))
    with pytest.raises(ValueError):
        load_flow_edges(pd.DataFrame({"来源": [None], "目标": ["B"], "流量": [1]}))


def test_validate_edges_structure(edges):
    check = validate_edges(edges)
    assert check["edges"] == 8
    assert check["nodes"] == 9
    assert check["pure_sources"] == 1
    assert check["has_cycle"] is False
    assert check["total_flow"] == 800 + 700 + 300 + 300 + 250 + 200 + 100 + 150


def test_validate_edges_detects_cycle():
    cyclic = pd.DataFrame(
        {"来源": ["A", "B"], "目标": ["B", "A"], "流量": [1, 2]}
    )
    assert validate_edges(cyclic)["has_cycle"] is True
    with pytest.raises(ValueError):
        node_levels(cyclic)


def test_node_flow_summary_outflow_inflow(edges):
    result = node_flow_summary(edges).set_index("节点")
    assert result.loc["首页", "流出"] == 1800.0
    assert result.loc["首页", "流入"] == 0.0
    assert result.loc["产品页", "流出"] == 550.0
    assert result.loc["产品页", "流入"] == 800.0
    assert result.loc["表单页", "流出"] == 0.0
    assert result.loc["表单页", "流入"] == 100.0


def test_node_levels_topological(edges):
    levels = node_levels(edges)
    assert levels["首页"] == 0
    assert levels["产品页"] == 1
    assert levels["服务页"] == 2
    assert levels["博客页"] == 2
    assert levels["成功案例"] == 3


def test_node_flow_summary_net_flow_ordering():
    edges = pd.DataFrame(
        {"来源": ["A", "B", "C"], "目标": ["D", "D", "D"], "流量": [10, 20, 30]}
    )
    result = node_flow_summary(edges)
    # 纯来源节点净流量为正且按流量降序；汇节点 D 净流量为 -60 排在最后。
    assert result.iloc[0]["节点"] == "C"
    assert result.iloc[0]["净流量"] == 30.0
    assert result.iloc[-1]["节点"] == "D"
    assert result.iloc[-1]["净流量"] == -60.0

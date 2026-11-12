"""Daily registration cohort and retention calculations."""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ("用户编号", "注册日期", "登录时点")


def compute_cohort_analysis(logins: pd.DataFrame) -> dict[str, pd.DataFrame | pd.Series]:
    missing = [c for c in REQUIRED_COLUMNS if c not in logins.columns]
    if missing:
        raise ValueError(f"缺少必需字段：{', '.join(missing)}")
    if logins.empty:
        raise ValueError("输入数据为空")
    data = logins.loc[:, REQUIRED_COLUMNS].copy()
    if data.isna().any().any():
        raise ValueError("必需字段存在缺失值")
    data["注册日期"] = pd.to_datetime(data["注册日期"], errors="coerce", format="mixed").dt.normalize()
    data["登录日期"] = pd.to_datetime(data["登录时点"], errors="coerce", format="mixed").dt.normalize()
    if data[["注册日期", "登录日期"]].isna().any().any():
        raise ValueError("日期字段存在无法解析的值")
    data["第几日"] = (data["登录日期"] - data["注册日期"]).dt.days
    if (data["第几日"] < 0).any():
        raise ValueError("登录日期不得早于注册日期")

    registrations = data.groupby("注册日期")["用户编号"].nunique().sort_index()
    registration_summary = registrations.rename("registered_users").to_frame()
    registration_summary["period_growth"] = registration_summary["registered_users"].pct_change()
    daily_logins = data.groupby("登录日期")["用户编号"].nunique().sort_index().rename("login_users")
    retained = data.groupby(["注册日期", "第几日"])["用户编号"].nunique().unstack(fill_value=0)
    retention = retained.div(registrations, axis=0).sort_index(axis=1)
    total_users = data["用户编号"].nunique()
    overall = data.groupby("第几日")["用户编号"].nunique().div(total_users).sort_index().rename("overall_retention")
    return {
        "registration_summary": registration_summary,
        "daily_login_users": daily_logins,
        "retention_matrix": retention,
        "overall_retention": overall,
    }


def plot_retention(retention_matrix: pd.DataFrame):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    image = ax.imshow(retention_matrix.to_numpy(), aspect="auto", vmin=0, vmax=1, cmap="Blues")
    ax.set(xlabel="Days since registration", ylabel="Registration cohort", title="Cohort retention")
    ax.set_xticks(range(len(retention_matrix.columns)), [str(c) for c in retention_matrix.columns])
    fig.colorbar(image, ax=ax, label="Retention rate")
    fig.tight_layout()
    return fig


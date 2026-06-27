"""把價格歷史畫成走勢圖（PNG bytes）。

刻意只用 ASCII 標籤（航線用 IATA 代碼、英文字），避免 matplotlib 預設字型
缺中文字而變成豆腐方塊。matplotlib 只在這個模組 import，CI（runner）不需要它。
"""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # 無視窗環境（伺服器）用的後端
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def render_price_chart(
    title: str,
    points: list[tuple[str, float]],
    currency: str = "TWD",
    threshold: float | None = None,
    baseline: float | None = None,
) -> bytes:
    """points: [(iso_timestamp, price), ...]，已按時間排序。回傳 PNG bytes。"""
    times = [datetime.fromisoformat(ts) for ts, _ in points]
    prices = [p for _, p in points]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(times, prices, marker="o", markersize=3, linewidth=1.5,
            color="#2563eb", label="Price")

    low = min(prices)
    low_i = prices.index(low)
    ax.scatter([times[low_i]], [low], color="#16a34a", zorder=5,
               label=f"Lowest {low:.0f}")

    if threshold is not None:
        ax.axhline(threshold, color="#dc2626", linestyle="--", linewidth=1,
                   label=f"Budget {threshold:.0f}")
    if baseline is not None:
        ax.axhline(baseline, color="#9333ea", linestyle=":", linewidth=1,
                   label=f"Baseline {baseline:.0f}")

    ax.set_title(title)
    ax.set_ylabel(f"Price ({currency})")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    fig.autofmt_xdate(rotation=30)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

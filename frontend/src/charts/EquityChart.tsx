import { useEffect, useRef } from "react";
import { AreaSeries, ColorType, createChart } from "lightweight-charts";
import type { Equity } from "../types";

export default function EquityChart({ data }: { data: Equity[] }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current || !data.length) return;
    const chart = createChart(host.current, {
      autoSize: true,
      height: 205,
      layout: {
        background: { type: ColorType.Solid, color: "#fff" },
        textColor: "#8a94a3",
        fontSize: 10,
        panes: { separatorColor: "#edf0f4", enableResize: false },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#f2f4f7" } },
      timeScale: { borderVisible: false },
      rightPriceScale: { borderVisible: false, minimumWidth: 72 },
    });
    const equity = chart.addSeries(AreaSeries, {
      lineColor: "#168574",
      topColor: "#16857428",
      bottomColor: "#16857402",
      lineWidth: 2,
      priceLineVisible: false,
    });
    equity.setData(data.map((p) => ({ time: p.date, value: p.total_equity })));
    const drawdown = chart.addSeries(
      AreaSeries,
      {
        lineColor: "#cc797b",
        topColor: "#cc797b02",
        bottomColor: "#cc797b30",
        lineWidth: 1,
        priceLineVisible: false,
        priceFormat: { type: "percent" },
      },
      1,
    );
    drawdown.setData(
      data.map((p) => ({ time: p.date, value: p.drawdown * 100 })),
    );
    chart.panes()[0].setStretchFactor(130);
    chart.panes()[1].setStretchFactor(50);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data]);
  return <div ref={host} className="equity-canvas" />;
}

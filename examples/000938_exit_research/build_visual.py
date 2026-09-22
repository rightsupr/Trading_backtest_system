"""离线 Lightweight Charts 图表：逐笔对比同一买点的原/新卖出。"""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
output = root / "output/exit-research-000938"
r = json.loads((output / "000938-report.json").read_text())
bars = json.loads((output / "000938-bars.json").read_text())["bars"]
library = (
    root
    / "frontend/node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js"
).read_text()
payload = {
    "bars": bars,
    "old": r["fixed_entries"]["baseline"],
    "new": r["fixed_entries"]["locked_guard"],
    "equity_old": r["full"]["baseline"]["equity"],
    "equity_new": r["full"]["locked_guard"]["equity"],
}
html = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>000938 · 卖出点对照研究</title><link rel="icon" href="data:,"><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#213449;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:32px auto;padding:0 22px}h1{font-size:28px;margin:8px 0 12px}h2{font-size:17px}p{line-height:1.8;color:#637084}.eyebrow{font-size:11px;letter-spacing:3px;color:#278370}.panel{background:#fff;border:1px solid #dce4e9;border-radius:12px;padding:20px;margin-top:18px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{background:#edf5f2;border-radius:8px;padding:16px}.card b{font-size:23px;display:block;margin:8px 0;color:#24765f}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap}select,button{font:inherit;padding:8px;border:1px solid #cad6e0;border-radius:5px;background:white}#price{height:430px}#equity{height:240px}.legend span{display:inline-block;margin-right:18px}.blue{color:#306fc3}.gray{color:#7b8596}.orange{color:#cf7c28}#detail{background:#f6f8fa;border-radius:8px;padding:12px 16px;line-height:1.9;margin-top:10px}.notice{border-left:3px solid #c18f42;padding-left:12px}.foot{font-size:12px;margin:20px 0;color:#738096}@media(max-width:640px){.cards{grid-template-columns:1fr}main{padding:0 12px}.panel{padding:12px}h1{font-size:23px}}
</style><main><div class="eyebrow">EXIT RESEARCH / 000938</div><h1>同一个买点，卖得早一点会怎样？</h1>
<p>腾讯前复权 · 2021-09-22 至 2026-09-21 · 21 笔原买点全部保留。仅研究历史，不预测最高点。</p>
<div class="cards"><div class="card">持有期最高收盘至卖价的回吐中位数<b>9.81% → 8.40%</b>曾有收盘浮盈的17笔交易</div><div class="card">高点后至卖出的交易日中位数<b>6 → 4 根</b>收盘确认，下一根开盘成交</div><div class="card">固定原买点，单笔净收益比较<b>11 改善 / 1 受损</b>另9笔不变；按相同初始资金逐笔诊断</div></div>
<section class="panel"><div class="toolbar"><h2>逐笔 K 线对照</h2><label for="trade">选择原买入日</label><select id="trade"></select><button id="all">看完整区间</button></div>
<p class="legend"><span class="blue">▲ 同一买入</span><span class="gray">▼ 原卖出</span><span class="orange">▼ 新卖出</span>滚轮缩放、拖动查看；标记在成交日，数值见下方。</p><div id="price"></div><div id="detail"></div></section>
<section class="panel"><h2>完整资金回测：10万元起始</h2><p><span class="gray">原版 +63.79%，最大回撤−29.98%</span>　<span class="orange">新候选 +122.27%，最大回撤−26.38%</span></p><div id="equity"></div></section>
<p class="notice">限制：002396交叉检查未显示收益提升（49.76% → 49.28%），且年份间差异明显。候选是在看过主样本后改进的，不是严格样本外验证；更早卖出也可能错过后续上涨。实际费用、滑点与回测模型边界见研究报告。</p>
<p class="foot">图表由 <a href="https://www.tradingview.com/">TradingView Lightweight Charts</a> 提供。数据与库均内嵌，本文件可离线打开。</p></main>
<script>__LIBRARY__</script><script>
const d=__DATA__;
const opt={autoSize:true,layout:{background:{color:'#ffffff'},textColor:'#617080'},grid:{vertLines:{color:'#f2f5f7'},horzLines:{color:'#f2f5f7'}},timeScale:{borderColor:'#e2e8ec'},rightPriceScale:{borderColor:'#e2e8ec'},localization:{locale:'zh-CN'}};
const chart=LightweightCharts.createChart(document.getElementById('price'),opt);
const candles=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:'#cf6262',downColor:'#278a75',borderVisible:false,wickUpColor:'#cf6262',wickDownColor:'#278a75'});
candles.setData(d.bars.map(b=>({time:b.date,open:b.open,high:b.high,low:b.low,close:b.close})));
const marks=LightweightCharts.createSeriesMarkers(candles,[]);
const sel=document.getElementById('trade');
const pct=v=>(v>=0?'+':'')+(v*100).toFixed(2)+'%';
d.old.forEach((r,i)=>{const delta=d.new[i].trade.net_return-r.trade.net_return;const op=document.createElement('option');op.value=i;op.textContent=r.entry_date+' · 净收益变化 '+(delta*100).toFixed(2)+' 个百分点';sel.appendChild(op);});
function show(i){const b=d.old[i].trade,a=d.new[i].trade;
 marks.setMarkers([{time:b.entry_date,position:'belowBar',color:'#306fc3',shape:'arrowUp',text:'同一买入'},
 {time:b.exit_date,position:'aboveBar',color:'#7b8596',shape:'arrowDown',text:'原卖出'},
 {time:a.exit_date,position:'aboveBar',color:'#cf7c28',shape:'arrowDown',text:'新卖出'}].sort((x,y)=>x.time.localeCompare(y.time)));
 const dates=d.bars.map(x=>x.date),start=Math.max(0,dates.indexOf(b.entry_date)-12),end=Math.min(dates.length-1,Math.max(dates.indexOf(b.exit_date),dates.indexOf(a.exit_date))+12);
 chart.timeScale().setVisibleRange({from:dates[start],to:dates[end]});
 document.getElementById('detail').textContent='买入：'+b.entry_date+'，'+b.entry_price.toFixed(2)+'元。原卖出：'+b.exit_date+'，'+b.exit_price.toFixed(2)+'元，净收益 '+pct(b.net_return)+'。新卖出：'+a.exit_date+'，'+a.exit_price.toFixed(2)+'元，净收益 '+pct(a.net_return)+'。新卖出原因：'+a.exit_reason;
}
sel.addEventListener('change',()=>show(Number(sel.value)));document.getElementById('all').addEventListener('click',()=>chart.timeScale().fitContent());show(0);
const equity=LightweightCharts.createChart(document.getElementById('equity'),opt);
for(const [key,color,title] of [['equity_old','#7b8596','原版'],['equity_new','#cf7c28','保护候选']]){const s=equity.addSeries(LightweightCharts.LineSeries,{color,title,lineWidth:2});s.setData(d[key].map(x=>({time:x.date,value:x.total_equity})));}equity.timeScale().fitContent();
</script></html>"""
html = html.replace("__LIBRARY__", library).replace(
    "__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
)
(output / "exit-comparison.html").write_text(html, encoding="utf-8")
print(output / "exit-comparison.html")

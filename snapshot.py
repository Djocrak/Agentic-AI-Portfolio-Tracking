
import os
import json
import math
import html
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import yfinance as yf

from free_discovery import discover_free_candidates, candidate_html, candidate_plain

# =============================================================================
# AGENTIC ECONOMY 46 — WEEKLY INDEX + EPISODIC ALERT ENGINE
# =============================================================================
# Allocation model:
#   Equities: weighted proportionally to structural conviction scores.
#   Crypto:   equally weighted within the crypto allocation.
#
# Defaults allocate 70% to equities and 30% to crypto. These are configurable
# through EQUITY_ALLOCATION and CRYPTO_ALLOCATION environment variables.
#
# Structural score = long-term agentic-economy conviction.
# Tactical score   = current market setup.
# Opportunity      = 60% structural + 40% tactical.
#
# This is a research and signal-generation tool, not personalised financial
# advice. Target weights are allocation references, not automatic trade orders.
# =============================================================================

STATE_FILE = os.getenv("STATE_FILE", "agentic_state.json")
SPY_TICKER = "SPY"
CRYPTO_BENCHMARK = "BTC-USD"
YF_PERIOD = "1y"
REQUEST_TIMEOUT = 15

EMAIL_RECIPIENT = os.getenv("PORTFOLIO_EMAIL_RECIPIENT", "djocrak@gmail.com")
EMAIL_SENDER = os.getenv("PORTFOLIO_EMAIL_SENDER", "djocrak@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

EQUITY_ALLOCATION = float(os.getenv("EQUITY_ALLOCATION", "70"))
CRYPTO_ALLOCATION = float(os.getenv("CRYPTO_ALLOCATION", "30"))

if not 0 <= EQUITY_ALLOCATION <= 100:
    raise ValueError("EQUITY_ALLOCATION must be between 0 and 100.")
if not 0 <= CRYPTO_ALLOCATION <= 100:
    raise ValueError("CRYPTO_ALLOCATION must be between 0 and 100.")
if not math.isclose(EQUITY_ALLOCATION + CRYPTO_ALLOCATION, 100.0, abs_tol=0.01):
    raise ValueError("EQUITY_ALLOCATION and CRYPTO_ALLOCATION must add up to 100.")

PORTFOLIO = [
    ("NVDA", "NVIDIA", "Equity", "AI Compute", 97, "Medium", "Foundational accelerator and inference platform."),
    ("AVGO", "Broadcom", "Equity", "AI Compute", 95, "Medium", "Custom accelerators, networking and connectivity."),
    ("TSM", "TSMC", "Equity", "AI Compute", 94, "Medium", "Leading-edge semiconductor manufacturing bottleneck."),
    ("AMD", "AMD", "Equity", "AI Compute", 88, "Medium-High", "Second-source accelerator and CPU platform."),
    ("ARM", "Arm Holdings", "Equity", "AI Compute", 87, "High", "Low-power architecture across edge and agent endpoints."),
    ("MRVL", "Marvell Technology", "Equity", "AI Compute", 86, "High", "Custom silicon, optical and connectivity exposure."),
    ("MU", "Micron Technology", "Equity", "Memory & Networking", 92, "High", "HBM and advanced memory bottleneck."),
    ("000660.KS", "SK Hynix", "Equity", "Memory & Networking", 91, "High", "HBM leadership and accelerator memory exposure."),
    ("ANET", "Arista Networks", "Equity", "Memory & Networking", 92, "Medium", "AI networking fabric."),
    ("VRT", "Vertiv", "Equity", "Memory & Networking", 91, "High", "Power, thermal management and cooling."),
    ("EQIX", "Equinix", "Equity", "Memory & Networking", 84, "Medium", "Datacentre, interconnection and edge infrastructure."),
    ("GEV", "GE Vernova", "Equity", "Power & Grid", 91, "Medium-High", "Generation and grid equipment."),
    ("ETN", "Eaton", "Equity", "Power & Grid", 90, "Medium", "Electrical distribution and power management."),
    ("CEG", "Constellation Energy", "Equity", "Power & Grid", 87, "High", "Baseload/nuclear generation."),
    ("PWR", "Quanta Services", "Equity", "Power & Grid", 86, "Medium", "Transmission and grid construction."),
    ("MSFT", "Microsoft", "Equity", "Enterprise Agents", 96, "Medium", "Azure, Copilot, identity and enterprise workflows."),
    ("GOOGL", "Alphabet", "Equity", "Enterprise & Personal Agents", 94, "Medium", "Gemini, Cloud, Search, Workspace, Android and TPUs."),
    ("AMZN", "Amazon", "Equity", "Enterprise Agents", 93, "Medium", "AWS, Bedrock, commerce and consumer distribution."),
    ("PLTR", "Palantir", "Equity", "Enterprise Agents", 91, "High", "AIP and operational data integration."),
    ("CRM", "Salesforce", "Equity", "Enterprise Agents", 84, "Medium", "CRM as a control plane for business agents."),
    ("NOW", "ServiceNow", "Equity", "Enterprise Agents", 91, "Medium-High", "Workflow automation and agent execution."),
    ("PANW", "Palo Alto Networks", "Equity", "Cybersecurity & Identity", 92, "Medium-High", "Autonomous security and expanded agent attack surface."),
    ("CRWD", "CrowdStrike", "Equity", "Cybersecurity & Identity", 91, "High", "Endpoint and identity telemetry."),
    ("NET", "Cloudflare", "Equity", "Cybersecurity & Identity", 91, "High", "Edge, network and developer infrastructure."),
    ("OKTA", "Okta", "Equity", "Cybersecurity & Identity", 82, "High", "Machine identity and permissioning."),
    ("AAPL", "Apple", "Equity", "Personal Agents", 93, "Medium", "Hardware, OS, identity, payments and distribution."),
    ("META", "Meta Platforms", "Equity", "Personal Agents", 94, "Medium", "Consumer AI, messaging, social graph and wearables."),
    ("TSLA", "Tesla", "Equity", "Robotics & Physical Agents", 86, "High", "Autonomy, robotics and edge AI."),
    ("ABB", "ABB", "Equity", "Robotics & Physical Agents", 84, "Medium", "Industrial robotics, electrification and automation."),
    ("SIEGY", "Siemens", "Equity", "Robotics & Physical Agents", 83, "Medium", "Industrial automation and digital twins."),
    ("COIN", "Coinbase", "Equity", "Agentic Finance Rails", 91, "High", "Exchange, custody, Base and agentic transaction infrastructure."),
    ("HOOD", "Robinhood", "Equity", "Agentic Finance Rails", 90, "High", "Agentic trading, tokenization and consumer finance."),
    ("CRCL", "Circle", "Equity", "Agentic Finance Rails", 92, "High", "Stablecoin, wallets and machine-payment infrastructure."),
    ("BTC-USD", "Bitcoin", "Crypto", "Crypto Monetary Rail", 99, "Medium-High", "Potential reserve monetary and collateral layer."),
    ("ETH-USD", "Ethereum", "Crypto", "Settlement & Smart Contracts", 96, "High", "Programmable settlement and tokenized assets."),
    ("SOL-USD", "Solana", "Crypto", "High-Speed Agent Rails", 94, "Very High", "High-throughput machine-to-machine settlement."),
    ("LINK-USD", "Chainlink", "Crypto", "Oracle & Interoperability", 91, "Very High", "Data, interoperability and verification."),
    ("ONDO-USD", "Ondo", "Crypto", "Tokenization / RWA", 87, "Very High", "Programmable tokenized real-world assets."),
    ("AVAX-USD", "Avalanche", "Crypto", "L1 / Tokenization", 83, "Very High", "Customizable institutional/tokenization networks."),
    ("SUI-USD", "Sui", "Crypto", "L1 / Agents", 86, "Very High", "High-performance agent-native application optionality."),
    ("ARB-USD", "Arbitrum", "Crypto", "L2 / Settlement", 82, "Very High", "Ethereum scaling and financial applications."),
    ("OP-USD", "Optimism", "Crypto", "L2 / Settlement", 80, "Very High", "Ethereum scaling ecosystem."),
    ("TAO-USD", "Bittensor", "Crypto", "Decentralized AI", 89, "Extreme", "Decentralized machine-intelligence incentive layer."),
    ("RENDER-USD", "Render", "Crypto", "Decentralized Compute", 84, "Extreme", "Distributed GPU compute optionality."),
    ("AKT-USD", "Akash", "Crypto", "Decentralized Compute", 81, "Extreme", "Open compute marketplace."),
    ("FIL-USD", "Filecoin", "Crypto", "Decentralized Storage", 78, "Extreme", "Decentralized storage for machine data."),
]


def calculate_target_weights():
    """Return target weights as percentages of the total portfolio."""
    equities = [item for item in PORTFOLIO if item[2] == "Equity"]
    crypto = [item for item in PORTFOLIO if item[2] == "Crypto"]

    if not equities:
        raise ValueError("Portfolio contains no equities.")
    if not crypto:
        raise ValueError("Portfolio contains no crypto assets.")

    structural_total = sum(item[4] for item in equities)
    if structural_total <= 0:
        raise ValueError("Total equity structural score must be positive.")

    weights = {}

    # Equity allocation is distributed in proportion to structural scores.
    for ticker, name, asset_type, vertical, structural, risk, thesis in equities:
        weights[ticker] = EQUITY_ALLOCATION * structural / structural_total

    # Crypto allocation is divided equally among all crypto assets.
    crypto_weight = CRYPTO_ALLOCATION / len(crypto)
    for ticker, name, asset_type, vertical, structural, risk, thesis in crypto:
        weights[ticker] = crypto_weight

    if not math.isclose(sum(weights.values()), 100.0, abs_tol=0.01):
        raise ValueError("Calculated target weights do not add up to 100%.")

    return weights


TARGET_WEIGHTS = calculate_target_weights()

META = {
    ticker: {
        "name": name,
        "asset_type": asset_type,
        "vertical": vertical,
        "structural": structural,
        "risk": risk,
        "thesis": thesis,
    }
    for ticker, name, asset_type, vertical, structural, risk, thesis in PORTFOLIO
}

SIGNAL_ICON = {
    "STRONG BUY": "🟢",
    "BUY": "🟢",
    "BUY ON PULLBACK": "🔵",
    "HOLD": "✅",
    "WATCH": "🟡",
    "REDUCE": "🟠",
    "THESIS REVIEW": "🔴",
}


def safe_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def pct_change(close, periods):
    if close is None or len(close) <= periods:
        return None
    old, new = safe_float(close.iloc[-periods]), safe_float(close.iloc[-1])
    return None if old == 0 else (new / old - 1) * 100


def rsi(close, period=14):
    if len(close) < period + 2:
        return 50.0
    d = close.diff()
    gain = d.clip(lower=0).rolling(period).mean().iloc[-1]
    loss = (-d.clip(upper=0)).rolling(period).mean().iloc[-1]
    if pd.isna(gain) or pd.isna(loss):
        return 50.0
    if loss == 0:
        return 100.0
    return float(100 - 100 / (1 + gain / loss))


def atr_percent(hist, period=14):
    if len(hist) < period + 2:
        return 0.0
    h, l, c = hist["High"], hist["Low"], hist["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    px = c.iloc[-1]
    return 0.0 if pd.isna(atr) or px == 0 else float(atr / px * 100)


def moving_average(close, n):
    return float(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None


def ma_slope(close, n, lookback=10):
    if len(close) < n + lookback:
        return 0.0
    x = close.rolling(n).mean()
    a, b = x.iloc[-1], x.iloc[-1 - lookback]
    return 0.0 if pd.isna(a) or pd.isna(b) or b == 0 else float((a / b - 1) * 100)


def volume_trend(hist):
    if "Volume" not in hist or len(hist) < 40:
        return False
    v = hist["Volume"].tail(40)
    return safe_float(v.tail(10).mean()) > safe_float(v.head(10).mean()) * 1.05


def benchmark_return(histories, asset_type):
    key = SPY_TICKER if asset_type == "Equity" else CRYPTO_BENCHMARK
    hist = histories.get(key)
    if hist is None:
        return 0.0
    return pct_change(hist["Close"].dropna(), 63) or 0.0


def tactical_score(hist, bench_return):
    close = hist["Close"].dropna()
    if len(close) < 200:
        return 0, {}

    price = float(close.iloc[-1])
    ma20 = moving_average(close, 20)
    ma50 = moving_average(close, 50)
    ma200 = moving_average(close, 200)
    r1 = pct_change(close, 21) or 0
    r3 = pct_change(close, 63) or 0
    r6 = pct_change(close, 126) or 0
    rs3 = r3 - bench_return
    rrsi = rsi(close)
    atr = atr_percent(hist)

    score = 0

    # Trend: 0-30
    score += 8 if price > ma20 else 0
    score += 8 if price > ma50 else 0
    score += 8 if price > ma200 else 0
    score += 3 if ma20 and ma50 and ma20 > ma50 else 0
    score += 3 if ma50 and ma200 and ma50 > ma200 else 0

    # Momentum / relative strength: 0-30
    score += 7 if r1 > 0 else 0
    score += 7 if r3 > 0 else 0
    score += 5 if r6 > 0 else 0
    score += 6 if rs3 > 0 else 0
    score += 5 if rs3 > 10 else 0

    # RSI: 0-15
    if 50 <= rrsi <= 68:
        score += 15
    elif 45 <= rrsi < 50 or 68 < rrsi <= 74:
        score += 10
    elif 40 <= rrsi < 45 or 74 < rrsi <= 80:
        score += 5

    # Volume: 0-5
    score += 5 if volume_trend(hist) else 0

    flags = []
    penalty = 0
    ext50 = (price / ma50 - 1) * 100 if ma50 else 0
    ext20 = (price / ma20 - 1) * 100 if ma20 else 0

    if rrsi >= 80:
        penalty += 7
        flags.append("RSI>=80")
    elif rrsi >= 75:
        penalty += 3
        flags.append("RSI>=75")

    if ext50 >= 25:
        penalty += 6
        flags.append(">25% above 50DMA")
    elif ext50 >= 15:
        penalty += 3
        flags.append(">15% above 50DMA")

    if ext20 >= 12:
        penalty += 2
        flags.append(">12% above 20DMA")
    if atr >= 10:
        penalty += 3
        flags.append("ATR>=10%")

    score = max(0, min(100, score - penalty))

    # Crossover logic.
    prev = close.iloc[:-1]
    p20 = moving_average(prev, 20)
    p50 = moving_average(prev, 50)
    p200 = moving_average(prev, 200)
    crosses = []

    if p20 and p50 and p20 <= p50 and ma20 > ma50:
        crosses.append("20/50 bullish")
    if p20 and p50 and p20 >= p50 and ma20 < ma50:
        crosses.append("20/50 bearish")
    if p20 and p200 and p20 <= p200 and ma20 > ma200:
        crosses.append("20/200 bullish")
    if p20 and p200 and p20 >= p200 and ma20 < ma200:
        crosses.append("20/200 bearish")
    if p50 and p200 and p50 <= p200 and ma50 > ma200:
        crosses.append("50/200 bullish")
    if p50 and p200 and p50 >= p200 and ma50 < ma200:
        crosses.append("50/200 bearish")

    return score, {
        "price": price,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "rsi": rrsi,
        "atr": atr,
        "r1": r1,
        "r3": r3,
        "r6": r6,
        "rel3": rs3,
        "s20": ma_slope(close, 20),
        "s50": ma_slope(close, 50),
        "flags": flags,
        "crosses": crosses,
    }


def classify(meta, tactical, m):
    structural = meta["structural"]
    risk = meta["risk"]
    opportunity = round(0.60 * structural + 0.40 * tactical)
    below50 = m["price"] < m["ma50"] if m["ma50"] else False
    below200 = m["price"] < m["ma200"] if m["ma200"] else False
    extended = bool(m["flags"])

    if structural >= 90 and tactical >= 82 and not extended:
        signal = "STRONG BUY"
    elif opportunity >= 84 and tactical >= 70 and not extended:
        signal = "BUY"
    elif structural >= 90 and tactical >= 60 and (extended or m["rsi"] > 74):
        signal = "BUY ON PULLBACK"
    elif below200 and tactical < 45:
        signal = "THESIS REVIEW"
    elif below50 and tactical < 50:
        signal = "REDUCE"
    elif opportunity >= 68:
        signal = "HOLD"
    else:
        signal = "WATCH"

    # Extreme-risk crypto requires stronger tactical confirmation.
    if risk == "Extreme" and signal == "BUY" and tactical < 78:
        signal = "BUY ON PULLBACK"

    return opportunity, signal


def review_level(m):
    price, atr, ma50, ma200 = m["price"], m["atr"], m["ma50"], m["ma200"]
    dist = max(0.08, min(0.20, (atr * 2.2) / 100)) if atr else 0.10
    level = price * (1 - dist)
    if ma50:
        level = max(level, ma50 * 0.97)
    if ma200 and price < ma200:
        level = min(level, ma200 * 0.98)
    return level


def download_histories(tickers):
    symbols = list(dict.fromkeys(tickers + [SPY_TICKER, CRYPTO_BENCHMARK]))
    histories = {}

    try:
        raw = yf.download(
            symbols,
            period=YF_PERIOD,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:
        print(f"[WARN] Bulk price download failed: {exc}")
        raw = pd.DataFrame()

    if raw is None or raw.empty:
        # Fall back to individual downloads so one bulk failure does not
        # necessarily prevent the whole scan.
        for ticker in symbols:
            try:
                df = yf.download(
                    ticker,
                    period=YF_PERIOD,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                if df is not None and not df.empty and len(df) >= 30:
                    histories[ticker] = df.dropna(how="all")
            except Exception as exc:
                print(f"[WARN] {ticker} download failed: {exc}")
        return histories

    for ticker in symbols:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    print(f"[WARN] No downloaded columns for {ticker}")
                    continue
                df = raw[ticker].dropna(how="all")
            else:
                df = raw.dropna(how="all")

            if len(df) >= 30:
                histories[ticker] = df
            else:
                print(f"[WARN] Insufficient downloaded history for {ticker}")
        except Exception as exc:
            print(f"[WARN] {ticker}: {exc}")

    return histories


def score_all():
    histories = download_histories(list(META))
    results = []

    for ticker, meta in META.items():
        hist = histories.get(ticker)
        if hist is None or len(hist) < 200:
            print(f"[WARN] insufficient history: {ticker}")
            continue

        tactical, metrics = tactical_score(
            hist,
            benchmark_return(histories, meta["asset_type"]),
        )
        opportunity, signal = classify(meta, tactical, metrics)

        results.append({
            "ticker": ticker,
            **meta,
            "target_weight": TARGET_WEIGHTS[ticker],
            "tactical": tactical,
            "opportunity": opportunity,
            "signal": signal,
            "review_level": review_level(metrics),
            **metrics,
        })

    return sorted(
        results,
        key=lambda x: (x["opportunity"], x["structural"]),
        reverse=True,
    )


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"assets": {}, "last_weekly": None}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def material_events(results, state):
    old = state.get("assets", {})
    events = []

    for r in results:
        prev = old.get(r["ticker"])
        if not prev:
            continue

        old_price = safe_float(prev.get("price"), r["price"])
        move = ((r["price"] / old_price) - 1) * 100 if old_price else 0
        old_signal = prev.get("signal")
        old_opportunity = safe_float(prev.get("opportunity"), r["opportunity"])
        score_jump = abs(r["opportunity"] - old_opportunity) >= 8
        is_crypto = r["asset_type"] == "Crypto"
        move_threshold = 12 if is_crypto else 8
        large_move = abs(move) >= move_threshold
        signal_change = old_signal and old_signal != r["signal"]
        crossover = bool(r["crosses"])

        if signal_change or score_jump or large_move or crossover:
            reasons = []
            if signal_change:
                reasons.append(f"signal {old_signal} → {r['signal']}")
            if score_jump:
                reasons.append(
                    f"opportunity {old_opportunity:.0f} → {r['opportunity']}"
                )
            if large_move:
                reasons.append(f"move {move:+.1f}% since prior scan")
            if crossover:
                reasons.append(", ".join(r["crosses"]))

            priority = (
                3
                if r["signal"] in ("STRONG BUY", "THESIS REVIEW")
                or abs(move) >= move_threshold * 1.5
                else 2
            )
            events.append({
                "ticker": r["ticker"],
                "reasons": reasons,
                "priority": priority,
            })

    return sorted(events, key=lambda x: x["priority"], reverse=True)


def recent_news(tickers):
    out = []

    for ticker in tickers[:10]:
        try:
            items = yf.Ticker(ticker).news or []
            for item in items[:3]:
                content = item.get("content", item)
                title = content.get("title") if isinstance(content, dict) else None
                if title:
                    out.append((ticker, title))
        except Exception:
            pass

    return out[:20]


def html_table(results):
    rows = []

    for r in results:
        rows.append(f"""
        <tr>
          <td>{html.escape(r["name"])}<br><b>{html.escape(r["ticker"])}</b></td>
          <td>{html.escape(r["asset_type"])}</td>
          <td>{html.escape(r["vertical"])}</td>
          <td>{r["target_weight"]:.2f}%</td>
          <td>{r["structural"]}</td>
          <td>{r["tactical"]}</td>
          <td><b>{r["opportunity"]}</b></td>
          <td>{SIGNAL_ICON[r["signal"]]} {r["signal"]}</td>
          <td>{html.escape(r["risk"])}</td>
          <td>{r["price"]:,.5g}</td>
          <td>{r["r3"]:+.1f}%</td>
          <td>{r["rel3"]:+.1f}%</td>
          <td>{r["rsi"]:.1f}</td>
          <td>{r["review_level"]:,.5g}</td>
          <td>{html.escape("; ".join(r["flags"]) or "—")}</td>
        </tr>""")

    return """<table><thead><tr>
    <th>Name</th><th>Type</th><th>Vertical</th><th>Target weight</th>
    <th>Structural</th><th>Tactical</th><th>Opportunity</th><th>Signal</th>
    <th>Risk</th><th>Price</th><th>3M</th><th>3M vs benchmark</th>
    <th>RSI</th><th>Review level</th><th>Extension</th>
    </tr></thead><tbody>""" + "".join(rows) + "</tbody></table>"


def send_email(subject, html_body, plain_body):
    if not EMAIL_PASSWORD:
        print("[ERROR] EMAIL_PASSWORD is not set; email not sent.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=REQUEST_TIMEOUT) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"[OK] Email sent to {EMAIL_RECIPIENT}")
    except Exception as exc:
        # A mail-server issue should be visible in the Actions log.
        # Do not silently report a successful email.
        print(f"[ERROR] Email delivery failed: {exc}")


def weekly_report(results, discovery=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    buys = [
        r for r in results
        if r["signal"] in ("STRONG BUY", "BUY", "BUY ON PULLBACK")
    ]
    reviews = [r for r in results if r["signal"] == "THESIS REVIEW"]
    top = results[:10]

    action_lines = []

    for r in buys[:8]:
        action = (
            "Wait for a pullback/reset before adding."
            if r["signal"] == "BUY ON PULLBACK"
            else (
                f"Review the position against its "
                f"{r['target_weight']:.2f}% target weight."
            )
        )
        action_lines.append(
            f"<li><b>{html.escape(r['ticker'])}</b>: {r['signal']} — "
            f"{action}</li>"
        )

    for r in reviews[:5]:
        action_lines.append(
            f"<li><b>{html.escape(r['ticker'])}</b>: "
            "<b>THESIS REVIEW</b> — reassess thesis, trend and position size.</li>"
        )

    discovery = discovery or {}
    discovery_candidates = discovery.get("candidates", [])
    source_health = html.escape(str(discovery.get("sources", {})))
    discovery_counts = html.escape(str(discovery.get("counts", {})))

    html_body = f"""<html><head><style>
    body{{font-family:Arial,sans-serif;color:#222;line-height:1.4}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}
    th{{background:#18202b;color:#fff;padding:6px;text-align:left}}
    td{{border-bottom:1px solid #ddd;padding:6px;vertical-align:top}}
    .box{{background:#f4f7fb;border:1px solid #ccd6e0;padding:12px;border-radius:6px}}
    </style></head><body>
    <h1>🤖 Agentic Economy 46 — Weekly Signal</h1>
    <p><b>{now}</b> · Target allocation: <b>{EQUITY_ALLOCATION:.1f}% equities</b>
    and <b>{CRYPTO_ALLOCATION:.1f}% crypto</b>.</p>
    <div class="box"><b>Scoring:</b> Structural thesis 60% + tactical timing 40%.
    Equity target weights are proportional to structural scores. Crypto target
    weights are equal within the crypto allocation. Risk is reported separately.
    Target weights are references, not automatic trade instructions.</div>
    <h2>Action plan</h2>
    <ul>{''.join(action_lines) or '<li>No new action.</li>'}</ul>
    <h2>Top opportunities</h2>
    <ul>{''.join(
        f"<li><b>{html.escape(r['ticker'])}</b>: {r['signal']} — "
        f"Opportunity {r['opportunity']}/100; Structural {r['structural']}; "
        f"Tactical {r['tactical']}; Target weight {r['target_weight']:.2f}%</li>"
        for r in top
    )}</ul>
    <h2>Free-source market discovery</h2>
    <p>New candidates are research leads, not automatic holdings or buy
    recommendations. Discovery sources include SEC EDGAR, CoinGecko free API,
    DefiLlama public data and GDELT public news. Source failures and missing
    data are disclosed.</p>
    {candidate_html(discovery_candidates, 15)}
    <p><b>Source health:</b> {source_health}.
    Candidate count: {discovery_counts}.</p>
    <h2>Portfolio allocation and signal matrix</h2>
    {html_table(results)}
    <p><small>Review levels are mechanical risk-review levels, not guaranteed
    execution prices. Discovery scores are prioritisation heuristics, not buy
    signals.</small></p>
    </body></html>"""

    plain = (
        f"Agentic Economy 46 — Weekly Signal — {now}\n"
        f"Allocation: {EQUITY_ALLOCATION:.1f}% equities / "
        f"{CRYPTO_ALLOCATION:.1f}% crypto\n"
        "Equities are weighted by structural score; crypto is equally weighted.\n\n"
        "ACTION PLAN\n"
    )
    plain += "\n".join(
        f"- {r['ticker']}: {r['signal']} | Target {r['target_weight']:.2f}% | "
        f"Opp {r['opportunity']} | Structural {r['structural']} | "
        f"Tactical {r['tactical']}"
        for r in buys[:10]
    )
    plain += "\n\nTHESIS REVIEWS\n" + "\n".join(
        f"- {r['ticker']}" for r in reviews[:5]
    )
    plain += (
        "\n\nFREE-SOURCE MARKET DISCOVERY\n"
        + candidate_plain(discovery_candidates, 15)
    )
    plain += "\n\nSource health: " + str(discovery.get("sources", {}))

    send_email(
        f"🤖 Agentic Economy 46 — Weekly Signal — {datetime.now().strftime('%d %b %Y')}",
        html_body,
        plain,
    )


def event_report(results, events, new_candidates=None):
    new_candidates = new_candidates or []

    if not events and not new_candidates:
        print("[INFO] No material market or discovery event — no email.")
        return

    tickers = [event["ticker"] for event in events]
    news = recent_news(tickers)
    bullets = ""

    for event in events:
        result = next(
            (item for item in results if item["ticker"] == event["ticker"]),
            None,
        )
        if result is None:
            continue

        bullets += (
            f"<li><b>{html.escape(result['ticker'])}</b> — {result['signal']} — "
            f"Opportunity {result['opportunity']}/100 — "
            f"Target weight {result['target_weight']:.2f}% — "
            f"{html.escape('; '.join(event['reasons']))}</li>"
        )

    news_html = (
        "<ul>" + "".join(
            f"<li><b>{html.escape(ticker)}</b>: {html.escape(title)}</li>"
            for ticker, title in news
        ) + "</ul>"
        if news
        else "<p>No additional headline context retrieved.</p>"
    )

    discovery_html = (
        candidate_html(new_candidates, 10)
        if new_candidates
        else "<p>No new candidate nominations.</p>"
    )

    html_body = f"""<html><body style="font-family:Arial,sans-serif;line-height:1.4">
    <h1>🚨 Agentic Economy 46 — Material Alert</h1>
    <p>Only material changes are emailed; unchanged signals are suppressed.</p>
    <h2>Triggers</h2><ul>{bullets}</ul>
    <h2>Action plan</h2>
    <ul>
      <li><b>STRONG BUY / BUY:</b> review the current holding against its
      asset-specific target weight; avoid chasing severe extensions.</li>
      <li><b>BUY ON PULLBACK:</b> thesis remains strong; wait for a technical
      reset/reclaim rather than chasing the price.</li>
      <li><b>REDUCE:</b> review position size against its target and reassess
      risk; do not automatically abandon the thesis.</li>
      <li><b>THESIS REVIEW:</b> reassess fundamentals, thesis and trend before
      deciding.</li>
    </ul>
    <h2>Headline context</h2>{news_html}
    <h2>New free-source discovery candidates</h2>{discovery_html}
    <p>Discovery candidates require source verification and fundamental/valuation
    review before any portfolio decision.</p>
    </body></html>"""

    plain = "Agentic Economy 46 — MATERIAL ALERT\n\n"

    for event in events:
        result = next(
            (item for item in results if item["ticker"] == event["ticker"]),
            None,
        )
        if result:
            plain += (
                f"{result['ticker']} — {result['signal']} — "
                f"Opp {result['opportunity']} — "
                f"Target {result['target_weight']:.2f}%\n"
                f"  {'; '.join(event['reasons'])}\n"
            )

    plain += (
        "\nNEW DISCOVERY CANDIDATES\n"
        + candidate_plain(new_candidates, 10)
    )

    send_email(
        f"🚨 Agentic Economy 46 — Material Alert — "
        f"{datetime.now().strftime('%d %b %Y %H:%M UTC')}",
        html_body,
        plain,
    )


def update_state(results, state):
    state["assets"] = {
        r["ticker"]: {
            "price": r["price"],
            "signal": r["signal"],
            "opportunity": r["opportunity"],
            "structural": r["structural"],
            "tactical": r["tactical"],
            "r3": r["r3"],
            "target_weight": r["target_weight"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for r in results
    }
    return state


def main(mode="weekly"):
    print(f"[INFO] Agentic Economy 46 — {mode}")
    print(
        f"[INFO] Target allocation: {EQUITY_ALLOCATION:.1f}% equities / "
        f"{CRYPTO_ALLOCATION:.1f}% crypto"
    )

    results = score_all()
    if not results:
        raise SystemExit("No core market data returned.")

    state = load_state()

    # Free-only discovery runs alongside the core scan. Failures in public
    # sources should be contained inside the discovery module.
    discovery = discover_free_candidates(
        core_tickers=set(META),
        max_output=50,
    )

    previous_seen = set(state.get("discovery_seen", []))
    discovered = discovery.get("candidates", [])
    new_candidates = [
        candidate
        for candidate in discovered
        if candidate.get("ticker") not in previous_seen
        and (
            int(candidate.get("structural") or 0) >= 78
            or bool(candidate.get("news_title"))
        )
    ]

    if mode == "weekly":
        weekly_report(results, discovery)
        state = update_state(results, state)
        state["last_weekly"] = datetime.now(timezone.utc).isoformat()
    else:
        events = material_events(results, state)
        event_report(results, events, new_candidates[:10])
        state = update_state(results, state)

    # Remember seen discovery tickers to suppress repeated alerts.
    seen_now = [
        candidate.get("ticker")
        for candidate in discovered
        if candidate.get("ticker")
    ]
    state["discovery_seen"] = list(
        dict.fromkeys(seen_now + list(previous_seen))
    )[:2000]
    state["discovery_sources"] = discovery.get("sources", {})
    state["last_discovery_scan"] = datetime.now(timezone.utc).isoformat()

    save_state(state)
    print(
        f"[OK] scored {len(results)}/{len(PORTFOLIO)} core assets; "
        f"discovered {len(discovered)} candidates"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["weekly", "event"],
        default="weekly",
    )
    main(parser.parse_args().mode)

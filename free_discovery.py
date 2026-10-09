"""Free-only discovery and evidence layer for the Agentic Economy scanner.

Sources:
- SEC company tickers + CompanyFacts/submissions (free; US reporting issuers)
- CoinGecko public/Demo API (free tier; optional free key via COINGECKO_DEMO_API_KEY)
- DefiLlama public protocol endpoint
- GDELT public news API

This module is deliberately best-effort. A source failure is recorded and does not
prevent the core portfolio scan from running. It does not claim complete global
market coverage, and it never converts missing fundamentals into a positive score.
"""
from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import requests

TIMEOUT = 15
USER_AGENT = os.getenv("SEC_USER_AGENT") or (
    "AgenticEconomyScanner/1.0 contact=" +
    os.getenv("PORTFOLIO_EMAIL_SENDER", "contact@example.com")
)
COINGECKO_KEY = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

# Broad, intentionally diverse fallback universe. SEC name discovery below expands it.
DISCOVERY_SEEDS: dict[str, tuple[str, str, int, str]] = {
    "ASML": ("ASML Holding", "Semiconductor Equipment", 91, "Lithography bottleneck for advanced compute."),
    "AMAT": ("Applied Materials", "Semiconductor Equipment", 86, "Semiconductor manufacturing equipment."),
    "LRCX": ("Lam Research", "Semiconductor Equipment", 86, "Etch and deposition equipment."),
    "KLAC": ("KLA Corporation", "Semiconductor Equipment", 85, "Process control and yield management."),
    "CRDO": ("Credo Technology", "AI Networking", 84, "High-speed connectivity for AI clusters."),
    "COHR": ("Coherent", "AI Networking", 80, "Optical components and photonics."),
    "CLS": ("Celestica", "AI Infrastructure", 82, "AI server and networking manufacturing."),
    "SMCI": ("Super Micro Computer", "AI Infrastructure", 82, "AI server systems; elevated execution risk."),
    "DELL": ("Dell Technologies", "AI Infrastructure", 78, "AI server and enterprise infrastructure."),
    "ORCL": ("Oracle", "Enterprise Agents", 86, "Cloud infrastructure, data and enterprise applications."),
    "SAP": ("SAP", "Enterprise Agents", 84, "Enterprise workflows and business data."),
    "ADBE": ("Adobe", "Enterprise Agents", 82, "Creative workflows and AI-assisted software."),
    "INTU": ("Intuit", "Enterprise Agents", 82, "Financial workflows and small-business automation."),
    "SNOW": ("Snowflake", "AI Data Layer", 83, "Enterprise data layer for AI applications."),
    "DDOG": ("Datadog", "AI Observability", 82, "Observability for increasingly complex software systems."),
    "ZS": ("Zscaler", "Cybersecurity & Identity", 83, "Zero-trust security for users, workloads and agents."),
    "FTNT": ("Fortinet", "Cybersecurity & Identity", 80, "Network security and security appliances."),
    "ISRG": ("Intuitive Surgical", "Robotics", 80, "Robotic-assisted medical procedures."),
    "SYM": ("Symbotic", "Robotics", 82, "Warehouse automation and robotics."),
    "TER": ("Teradyne", "Robotics & Test", 79, "Semiconductor test and industrial robotics."),
    "ROK": ("Rockwell Automation", "Industrial Automation", 78, "Industrial control and factory automation."),
    "HON": ("Honeywell", "Industrial Automation", 77, "Industrial automation and building systems."),
    "UBER": ("Uber Technologies", "Autonomous Mobility", 78, "Mobility platform with autonomous-vehicle optionality."),
    "SHOP": ("Shopify", "Agentic Commerce", 82, "Commerce infrastructure and merchant tooling."),
    "PYPL": ("PayPal", "Agentic Commerce", 78, "Digital payments and merchant checkout."),
    "V": ("Visa", "Agentic Finance Rails", 80, "Global payment network and transaction infrastructure."),
    "MA": ("Mastercard", "Agentic Finance Rails", 80, "Global payment network and identity services."),
    "SQ": ("Block", "Agentic Finance Rails", 77, "Merchant payments and consumer financial tools."),
    "JPM": ("JPMorgan Chase", "Agentic Finance Rails", 76, "Financial infrastructure and institutional distribution."),
    "BLK": ("BlackRock", "Tokenization & Finance", 78, "Asset management and tokenized-fund distribution."),
    "MSTR": ("Strategy", "Bitcoin Treasury", 74, "Bitcoin treasury exposure; financing and premium risk."),
    "MARA": ("MARA Holdings", "Crypto Infrastructure", 68, "Bitcoin mining and infrastructure; high operating leverage."),
    "RIOT": ("Riot Platforms", "Crypto Infrastructure", 67, "Bitcoin mining and power infrastructure."),
}

THEME_TERMS = {
    "AI Compute": ("semiconductor", "chip", "gpu", "accelerator", "compute", "silicon", "foundry"),
    "AI Infrastructure": ("data center", "datacenter", "networking", "optical", "server", "cooling", "power", "grid"),
    "Enterprise Agents": ("enterprise software", "workflow", "automation", "cloud", "artificial intelligence", "data platform", "cybersecurity", "identity"),
    "Robotics & Physical AI": ("robot", "autonomous", "automation", "industrial", "machine vision", "drone"),
    "Agentic Finance Rails": ("payments", "payment", "fintech", "financial technology", "stablecoin", "tokenization", "digital asset"),
    "Crypto & Decentralized Compute": ("blockchain", "cryptocurrency", "digital asset", "decentralized", "cloud computing", "artificial intelligence"),
}
CORE_CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "LINK", "ONDO", "AVAX", "SUI", "ARB", "OP", "TAO", "RENDER", "AKT", "FIL"}
CORE_STOCK_SYMBOLS = {"NVDA", "AVGO", "TSM", "AMD", "ARM", "MRVL", "MU", "ANET", "VRT", "EQIX", "GEV", "ETN", "CEG", "PWR", "MSFT", "GOOGL", "AMZN", "PLTR", "CRM", "NOW", "PANW", "CRWD", "NET", "OKTA", "AAPL", "META", "TSLA", "ABB", "SIEGY", "COIN", "HOOD", "CRCL"}


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    try:
        response = SESSION.get(url, params=params, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[WARN] Free discovery source unavailable: {url.split('?')[0]} ({exc})")
        return None


def _clean_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Z0-9.\-]", "", (symbol or "").upper().strip())


def _sec_ticker_map() -> dict[str, dict[str, str]]:
    data = _get_json("https://www.sec.gov/files/company_tickers.json")
    out: dict[str, dict[str, str]] = {}
    if not isinstance(data, dict):
        return out
    for row in data.values():
        ticker = _clean_symbol(str(row.get("ticker", "")))
        name = str(row.get("title", "")).strip()
        cik = str(row.get("cik_str", "")).strip()
        if ticker and name and cik:
            out[ticker] = {"name": name, "cik": cik.zfill(10)}
    return out


def _thematic_candidates(sec_map: dict[str, dict[str, str]], limit: int = 100) -> list[dict[str, Any]]:
    # SEC ticker list provides a fresh issuer universe. Company-name matching is a
    # discovery heuristic, not a substitute for sector classification.
    matches = []
    terms = sorted({term for group in THEME_TERMS.values() for term in group}, key=len, reverse=True)
    for ticker, item in sec_map.items():
        if ticker in CORE_STOCK_SYMBOLS or len(ticker) > 6 or any(ch in ticker for ch in ("^", "$")):
            continue
        name_l = item["name"].lower()
        found = [term for term in terms if term in name_l]
        if not found:
            continue
        # Rank issuer-name hits by breadth of relevant words and prefer common-looking symbols.
        score = min(92, 62 + 6 * len(set(found)))
        matches.append({
            "ticker": ticker, "name": item["name"], "asset_type": "Equity",
            "vertical": "SEC name-match discovery", "agentic_adoption": score,
            "structural": score, "risk": "Unrated", "thesis": "Candidate discovered from current SEC issuer list; verify business exposure.",
            "discovery_source": "SEC company ticker list", "source_url": "https://www.sec.gov/search-filings",
            "cik": item["cik"], "discovery_reason": "Issuer name matched thematic keyword(s): " + ", ".join(found[:5]),
            "fundamental_quality": None, "fundamental_note": "Not yet verified; see SEC filings before acting.",
        })
    matches.sort(key=lambda x: (x["agentic_adoption"], x["name"]), reverse=True)
    return matches[:limit]


def _sec_fact_values(facts: dict, concept_names: list[str]) -> list[tuple[str, float, str]]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concept_names:
        item = gaap.get(concept)
        if not item:
            continue
        units = item.get("units", {})
        rows = units.get("USD", []) or units.get("shares", [])
        annual = []
        for row in rows:
            if row.get("form") not in ("10-K", "20-F", "40-F"):
                continue
            if not row.get("fy") or not row.get("filed") or row.get("val") is None:
                continue
            annual.append((str(row.get("end", "")), float(row["val"]), str(row.get("filed", ""))))
        # Consolidate duplicate facts for the same period end; keep the latest filed.
        by_end: dict[str, tuple[str, float, str]] = {}
        for row in sorted(annual, key=lambda x: x[2]):
            by_end[row[0]] = row
        result = sorted(by_end.values(), key=lambda x: x[0], reverse=True)
        if result:
            return result
    return []


def sec_fundamentals(cik: str) -> dict[str, Any]:
    if not cik:
        return {"fundamental_quality": None, "fundamental_note": "No SEC CIK available."}
    facts = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json")
    if not isinstance(facts, dict):
        return {"fundamental_quality": None, "fundamental_note": "SEC fundamentals unavailable this run."}
    revenue = _sec_fact_values(facts, ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues", "SalesRevenueGoodsNet"])
    operating_income = _sec_fact_values(facts, ["OperatingIncomeLoss"])
    cashflow = _sec_fact_values(facts, ["NetCashProvidedByUsedInOperatingActivities"])
    capex = _sec_fact_values(facts, ["PaymentsToAcquirePropertyPlantAndEquipment"])
    score, available = 50, []
    growth = None
    if len(revenue) >= 2 and revenue[1][1] != 0:
        growth = (revenue[0][1] / revenue[1][1] - 1) * 100
        available.append(f"latest annual revenue growth {growth:+.1f}%")
        score += 18 if growth >= 25 else 12 if growth >= 10 else 5 if growth > 0 else -12
    if revenue and operating_income:
        rev_by_end = {r[0]: r[1] for r in revenue}
        op_match = next((x for x in operating_income if x[0] in rev_by_end and rev_by_end[x[0]]), None)
        if op_match:
            margin = op_match[1] / rev_by_end[op_match[0]] * 100
            available.append(f"latest matching annual operating margin {margin:.1f}%")
            score += 12 if margin >= 20 else 7 if margin >= 10 else 2 if margin >= 0 else -10
    if cashflow:
        if cashflow[0][1] > 0:
            score += 8; available.append("positive operating cash flow in latest annual filing")
        else:
            score -= 8; available.append("negative operating cash flow in latest annual filing")
    if revenue and capex:
        cf_by_end = {r[0]: r[1] for r in cashflow}
        capex_match = next((x for x in capex if x[0] in cf_by_end), None)
        if capex_match:
            fcf = cf_by_end[capex_match[0]] - abs(capex_match[1])
            available.append("positive free cash flow" if fcf > 0 else "negative free cash flow")
            score += 5 if fcf > 0 else -5
    if not available:
        return {"fundamental_quality": None, "fundamental_note": "SEC filing found but comparable fundamentals were insufficient."}
    return {
        "fundamental_quality": max(0, min(100, int(score))),
        "fundamental_note": "; ".join(available),
        "revenue_growth_pct": round(growth, 1) if growth is not None else None,
        "fundamental_source": "SEC CompanyFacts",
        "fundamental_url": f"https://www.sec.gov/edgar/browse/?CIK={str(cik).lstrip('0')}",
    }


def sec_recent_filings(cik: str) -> dict[str, Any]:
    """Retrieve recent material SEC filing metadata for an issuer."""
    if not cik:
        return {}
    data = _get_json(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json")
    recent = (data or {}).get("filings", {}).get("recent", {}) if isinstance(data, dict) else {}
    forms = recent.get("form", []) or []
    dates = recent.get("filingDate", []) or []
    accession = recent.get("accessionNumber", []) or []
    docs = recent.get("primaryDocument", []) or []
    items = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "10-K", "10-Q", "20-F", "6-K", "SC 13D", "SC 13G"):
            continue
        try:
            acc = accession[i].replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{docs[i]}"
            items.append({"form": form, "date": dates[i], "url": url})
        except Exception:
            continue
        if len(items) >= 5:
            break
    if not items:
        return {"recent_filings": [], "filings_note": "No recent material filing metadata found."}
    return {"recent_filings": items, "filings_note": "; ".join(f"{x['form']} filed {x['date']}" for x in items)}


def yahoo_valuation_snapshot(ticker: str) -> dict[str, Any]:
    """Best-effort free Yahoo Finance valuation fields; missing fields stay missing."""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).get_info()
        out = {}
        for source, target in (("marketCap", "market_cap_usd"), ("trailingPE", "trailing_pe"),
                               ("forwardPE", "forward_pe"), ("priceToSalesTrailing12Months", "price_to_sales"),
                               ("enterpriseToEbitda", "ev_to_ebitda"), ("freeCashflow", "free_cash_flow_usd")):
            value = info.get(source)
            if isinstance(value, (int, float)) and value > 0:
                out[target] = value
        if out:
            out["valuation_source"] = "Yahoo Finance unofficial public data"
            out["valuation_note"] = "Ratios are best-effort, may be stale or unavailable, and should be checked against filings."
        return out
    except Exception as exc:
        print(f"[WARN] Yahoo valuation unavailable for {ticker}: {exc}")
        return {}


def yahoo_market_snapshots(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Best-effort technical snapshot for discovered equities using free yfinance data."""
    clean = list(dict.fromkeys(t for t in tickers if t and "(" not in t))[:30]
    if not clean:
        return {}
    try:
        import yfinance as yf
        import pandas as pd
        raw = yf.download(clean, period="1y", interval="1d", auto_adjust=True,
                          progress=False, group_by="ticker", threads=False)
        out: dict[str, dict[str, Any]] = {}
        if raw is None or raw.empty:
            return out
        for ticker in clean:
            try:
                hist = raw[ticker].dropna(how="all") if isinstance(raw.columns, pd.MultiIndex) else raw.dropna(how="all")
                close = hist["Close"].dropna()
                if len(close) < 60:
                    continue
                price = float(close.iloc[-1])
                r21 = (price / float(close.iloc[-22]) - 1) * 100 if len(close) >= 22 and float(close.iloc[-22]) else None
                r63 = (price / float(close.iloc[-64]) - 1) * 100 if len(close) >= 64 and float(close.iloc[-64]) else None
                r126 = (price / float(close.iloc[-127]) - 1) * 100 if len(close) >= 127 and float(close.iloc[-127]) else None
                ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
                ma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
                market_score = 50
                if ma50 is not None:
                    market_score += 15 if price > ma50 else -10
                if ma200 is not None:
                    market_score += 15 if price > ma200 else -15
                if r63 is not None:
                    market_score += 10 if r63 > 10 else 5 if r63 > 0 else -10 if r63 < -10 else 0
                out[ticker] = {
                    "market_price": round(price, 4), "return_1m_pct": round(r21, 2) if r21 is not None else None,
                    "return_3m_pct": round(r63, 2) if r63 is not None else None,
                    "return_6m_pct": round(r126, 2) if r126 is not None else None,
                    "above_50dma": bool(price > ma50) if ma50 is not None else None,
                    "above_200dma": bool(price > ma200) if ma200 is not None else None,
                    "market_score": max(0, min(100, market_score)),
                    "market_note": f"Price {price:.4g}; 3m {r63:+.1f}%" if r63 is not None else f"Price {price:.4g}; limited history",
                    "market_source": "Yahoo Finance via yfinance (unofficial public data)",
                }
            except Exception:
                continue
        return out
    except Exception as exc:
        print(f"[WARN] Yahoo discovery price scan unavailable: {exc}")
        return {}


def _coin_gecko_candidates() -> list[dict[str, Any]]:
    headers = {"x-cg-demo-api-key": COINGECKO_KEY} if COINGECKO_KEY else None
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1,
              "sparkline": "false", "price_change_percentage": "7d"}
    data = _get_json("https://api.coingecko.com/api/v3/coins/markets", params=params, headers=headers)
    if not isinstance(data, list):
        return []
    out = []
    for coin in data:
        symbol = str(coin.get("symbol", "")).upper()
        name = str(coin.get("name", "Unknown"))
        market_cap = coin.get("market_cap") or 0
        volume = coin.get("total_volume") or 0
        if not symbol or symbol in CORE_CRYPTO_SYMBOLS or market_cap < 100_000_000 or volume < 5_000_000:
            continue
        change7 = coin.get("price_change_percentage_7d_in_currency")
        # Candidate score blends scale and positive/negative weekly momentum; it is not a buy signal.
        scale_score = min(70, 45 + 5 * max(0, 8 - (coin.get("market_cap_rank") or 100)))
        momentum = 10 if isinstance(change7, (int, float)) and change7 > 10 else 5 if isinstance(change7, (int, float)) and change7 > 0 else -5 if isinstance(change7, (int, float)) and change7 < -15 else 0
        out.append({
            "ticker": symbol + "-USD", "name": name, "asset_type": "Crypto", "vertical": "CoinGecko market discovery",
            "agentic_adoption": None, "structural": max(0, min(100, int(scale_score + momentum))), "risk": "High / verify",
            "thesis": "New crypto-market candidate; agentic relevance and token value capture require verification.",
            "discovery_source": "CoinGecko free API", "source_url": f"https://www.coingecko.com/en/coins/{coin.get('id', '')}",
            "discovery_reason": f"Rank #{coin.get('market_cap_rank')}; market cap ${market_cap:,.0f}; 24h volume ${volume:,.0f}; 7d change {change7 if isinstance(change7, (int, float)) else 'n/a'}%.",
            "market_cap_usd": market_cap, "volume_24h_usd": volume, "change_7d_pct": change7,
            "fundamental_quality": None, "fundamental_note": "Crypto fundamentals are not inferred from price; protocol metrics are checked separately.",
        })
    return out


def _defillama_candidates() -> list[dict[str, Any]]:
    data = _get_json("https://api.llama.fi/protocols")
    if not isinstance(data, list):
        return []
    out = []
    terms = ("ai", "compute", "agent", "data", "oracle", "storage", "depin", "infrastructure", "lending", "dex", "bridge", "payments")
    for p in data:
        name = str(p.get("name", ""))
        category = str(p.get("category", ""))
        symbol = str(p.get("symbol", "")).upper()
        tvl = p.get("tvl") or 0
        if not name or not symbol or tvl < 10_000_000:
            continue
        text = f"{name} {category}".lower()
        if not any(term in text for term in terms):
            continue
        if symbol in CORE_CRYPTO_SYMBOLS:
            continue
        out.append({
            "ticker": symbol + " (protocol)", "name": name, "asset_type": "Crypto protocol", "vertical": category or "Protocol discovery",
            "agentic_adoption": None, "structural": min(90, 55 + (10 if "ai" in text or "compute" in text or "agent" in text else 0) + (10 if tvl >= 1_000_000_000 else 0)),
            "risk": "High / verify", "thesis": "Protocol surfaced by public DeFi analytics; confirm token availability and value capture.",
            "discovery_source": "DefiLlama public protocol list", "source_url": str(p.get("url") or "https://defillama.com/protocols"),
            "discovery_reason": f"Category {category}; TVL ${tvl:,.0f}; 1d change {p.get('change_1d', 'n/a')}%; 7d change {p.get('change_7d', 'n/a')}%.",
            "tvl_usd": tvl, "fundamental_quality": None, "fundamental_note": "TVL is a usage/capital metric, not protocol revenue or token-holder value capture.",
        })
    out.sort(key=lambda x: x.get("tvl_usd", 0), reverse=True)
    return out[:60]


def _news_candidates(sec_map: dict[str, dict[str, str]], limit: int = 20) -> list[dict[str, Any]]:
    query = '("AI agent" OR "agentic AI" OR "autonomous agent" OR "AI infrastructure" OR "robotics AI" OR "AI data center")'
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    data = _get_json(url, params={"query": query, "mode": "ArtList", "format": "json", "sort": "DateDesc", "maxrecords": 75})
    if not isinstance(data, dict):
        return []
    articles = data.get("articles", []) or []
    by_name = sorted(sec_map.items(), key=lambda kv: len(kv[1]["name"]), reverse=True)
    found: dict[str, dict[str, Any]] = {}
    for article in articles:
        title = str(article.get("title", ""))
        title_l = title.lower()
        for ticker, item in by_name:
            name = item["name"]
            if len(name) < 5 or name.lower() not in title_l or ticker in CORE_STOCK_SYMBOLS:
                continue
            found[ticker] = {
                "ticker": ticker, "name": name, "asset_type": "Equity", "vertical": "News-led discovery",
                "agentic_adoption": 70, "structural": 70, "risk": "Unrated",
                "thesis": "News-led candidate; verify the primary source and whether the event is financially material.",
                "discovery_source": "GDELT public news index", "source_url": str(article.get("url") or "https://www.gdeltproject.org/"),
                "discovery_reason": "Recent headline match: " + title,
                "news_title": title, "news_date": article.get("seendate"), "cik": item["cik"],
                "fundamental_quality": None, "fundamental_note": "Fundamentals not yet checked.",
            }
            break
        if len(found) >= limit:
            break
    return list(found.values())[:limit]


def discover_free_candidates(core_tickers: set[str] | None = None, max_output: int = 50) -> dict[str, Any]:
    """Return ranked free-source candidates and source-health diagnostics."""
    started = datetime.now(timezone.utc).isoformat()
    sources = {"sec_issuer_list": False, "coingecko": False, "defillama": False, "gdelt": False}
    sec_map = _sec_ticker_map()
    sources["sec_issuer_list"] = bool(sec_map)
    stock_seed_candidates = []
    for ticker, (name, vertical, adoption, thesis) in DISCOVERY_SEEDS.items():
        if ticker in CORE_STOCK_SYMBOLS or (core_tickers and ticker in core_tickers):
            continue
        sec_match = sec_map.get(ticker, {})
        stock_seed_candidates.append({
            "ticker": ticker, "name": name, "asset_type": "Equity", "vertical": vertical,
            "agentic_adoption": adoption, "structural": adoption, "risk": "Medium-High / verify", "thesis": thesis,
            "discovery_source": "Curated free-source seed universe", "source_url": f"https://www.sec.gov/edgar/search/",
            "discovery_reason": "Broad thematic seed; must pass fresh fundamentals and market checks.",
            "cik": sec_match.get("cik"),
            "fundamental_quality": None, "fundamental_note": "Not yet verified; SEC check attempted for top candidates.",
        })
    thematic = _thematic_candidates(sec_map)
    news = _news_candidates(sec_map)
    coins = _coin_gecko_candidates()
    protocols = _defillama_candidates()
    sources["coingecko"] = bool(coins)
    sources["defillama"] = bool(protocols)
    sources["gdelt"] = bool(news)

    # Deduplicate by source identity, keeping the richest record and never replacing a core name.
    combined: dict[str, dict[str, Any]] = {}
    for item in stock_seed_candidates + thematic + news + coins + protocols:
        key = item["ticker"].upper()
        if core_tickers and key in core_tickers:
            continue
        if key not in combined:
            combined[key] = item
        else:
            old = combined[key]
            if item.get("news_title") and not old.get("news_title"):
                old.update({k: v for k, v in item.items() if v is not None})
            old["discovery_sources"] = sorted(set(old.get("discovery_sources", [old.get("discovery_source", "unknown")]) + [item.get("discovery_source", "unknown")]))
            old["structural"] = max(int(old.get("structural") or 0), int(item.get("structural") or 0))

    candidates = list(combined.values())
    # Pull free price histories for a bounded equity batch; never attempt thousands of downloads.
    market_batch = sorted([x for x in candidates if x.get("asset_type") == "Equity" and "(" not in x.get("ticker", "")],
                          key=lambda x: int(x.get("structural") or 0), reverse=True)[:30]
    market_data = yahoo_market_snapshots([x.get("ticker", "") for x in market_batch])
    for item in candidates:
        if item.get("ticker") in market_data:
            item.update(market_data[item["ticker"]])
    # Pull SEC fundamentals for a small batch to respect free-source access and runtime limits.
    sec_candidates = [x for x in candidates if x.get("cik")]
    for item in sec_candidates[:12]:
        cik = item.get("cik", "")
        item.update(sec_fundamentals(cik))
        item.update(sec_recent_filings(cik))
        if item.get("asset_type") == "Equity":
            item.update(yahoo_valuation_snapshot(item.get("ticker", "")))
        time.sleep(0.12)

    # Mark news-led names separately; a headline is a lead, not confirmed evidence.
    for item in candidates:
        if item.get("news_title"):
            item["news_status"] = "Lead only — verify primary source"
        if item.get("recent_filings"):
            item["discovery_reason"] = str(item.get("discovery_reason", "")) + " | SEC filings: " + str(item.get("filings_note", ""))
    candidates.sort(key=lambda x: (
        1 if x.get("news_title") else 0,
        1 if x.get("fundamental_quality") is not None else 0,
        int(x.get("market_score") if x.get("market_score") is not None else 50),
        int(x.get("structural") or 0),
        float(x.get("market_cap_usd") or x.get("tvl_usd") or 0),
    ), reverse=True)
    return {
        "generated_at": started,
        "sources": sources,
        "source_note": "Free-tier/public sources only. Discovery coverage is broad but not exhaustive; missing data is not scored as positive.",
        "candidates": candidates[:max_output],
        "counts": {"total": len(candidates), "equity": sum(x.get("asset_type") == "Equity" for x in candidates),
                   "crypto": sum(x.get("asset_type") in ("Crypto", "Crypto protocol") for x in candidates),
                   "news_led": sum(bool(x.get("news_title")) for x in candidates)},
    }


def candidate_html(candidates: list[dict[str, Any]], limit: int = 15) -> str:
    rows = []
    for c in candidates[:limit]:
        fundamentals = c.get("fundamental_note") or "Not available"
        url = html.escape(str(c.get("source_url") or ""), quote=True)
        title = html.escape(str(c.get("discovery_reason") or c.get("thesis") or ""))
        market = c.get("market_note") or (f"7d {c.get('change_7d_pct'):+.1f}%" if isinstance(c.get("change_7d_pct"), (int, float)) else "No price snapshot")
        rows.append(
            "<tr><td><b>" + html.escape(str(c.get("name", ""))) + "</b><br>" + html.escape(str(c.get("ticker", ""))) +
            "</td><td>" + html.escape(str(c.get("asset_type", ""))) + " / " + html.escape(str(c.get("vertical", ""))) +
            "</td><td>" + str(c.get("structural", "n/a")) + "</td><td>" + html.escape(str(market)) +
            "</td><td>" + html.escape(str(fundamentals)) +
            "</td><td>" + title + "<br><a href=\"" + url + "\">Source</a></td></tr>"
        )
    if not rows:
        return "<p>No new free-source candidates were available this run.</p>"
    return "<table><thead><tr><th>Candidate</th><th>Type / vertical</th><th>Discovery score</th><th>Market snapshot</th><th>Fundamental evidence</th><th>Reason / source</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def candidate_plain(candidates: list[dict[str, Any]], limit: int = 15) -> str:
    lines = []
    for c in candidates[:limit]:
        lines.append(f"- {c.get('name')} ({c.get('ticker')}) | {c.get('asset_type')} | discovery score {c.get('structural', 'n/a')} | {c.get('discovery_reason', '')} | {c.get('source_url', '')}")
        if c.get("fundamental_note"):
            lines.append("  Fundamentals: " + c["fundamental_note"])
    return "\n".join(lines) if lines else "No new free-source candidates were available this run."

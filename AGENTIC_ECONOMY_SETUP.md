# Agentic Economy — Core 46 + Free Market Discovery

## What this version does

- Keeps the strategic 46-name core at an equal-weight target of about 2.17% per name.
- Retains the technical trend, momentum, relative-strength, RSI, volatility and material-move checks.
- Adds a separate free-source discovery module (`free_discovery.py`) to surface candidates beyond the core list.
- Uses free/public sources only. There are no paid data dependencies or mandatory API keys.
- Adds discovery candidates, available fundamentals, recent SEC filings, source health and source links to the weekly report.
- Can alert on new candidate nominations during the daily event scan; candidates are research leads, not automatic holdings.

## Free sources

1. **SEC EDGAR** — `https://www.sec.gov/files/company_tickers.json`, CompanyFacts XBRL and issuer submissions. Used for US reporting-company discovery, selected financial statement metrics and recent filings. Set `SEC_USER_AGENT` to a descriptive contact string with a valid email address where possible. If not configured, the script uses the configured sender address as a fallback.
2. **Yahoo Finance via yfinance** — public/unofficial price histories and best-effort valuation fields. Availability, fields and rate limits are not guaranteed. Ratios must be verified against filings.
3. **CoinGecko API** — public/free-tier market discovery for larger crypto assets. `COINGECKO_DEMO_API_KEY` is optional and may improve reliability within its free-tier limits.
4. **DefiLlama public protocol endpoint** — protocol discovery and TVL changes. TVL is not the same as protocol revenue or token-holder value capture.
5. **GDELT public news index** — broad news leads. Headlines are leads only; verify material claims against primary sources before acting.

The scanner never requires paid APIs. Optional free keys are optional; if a source is unavailable or rate-limited, the core portfolio scan continues and source health is reported.

## Discovery approach and limitations

The module combines a broad thematic seed universe with thematic name matches from the current SEC issuer list, GDELT headline matches, CoinGecko market candidates and DefiLlama protocols. This expands discovery but is **not a complete global market scan**. Company-name keyword matching can miss companies whose legal names do not reveal their business, and Yahoo ticker mapping is imperfect for crypto assets.

Candidate scores are prioritisation heuristics, not buy signals. News mentions are unverified leads. SEC financial analysis is attempted for a limited batch of candidates per run to respect free-service limits. Valuation fields from Yahoo Finance are unofficial and may be stale or missing. No missing field is treated as a positive result. Non-US financial disclosures and crypto token-holder value capture will often require manual verification.

## Fundamental evidence currently extracted

Where available in SEC CompanyFacts, the script checks annual revenue growth, operating margin, operating cash flow and free-cash-flow direction. It also retrieves recent material filing metadata (including 8-K, 10-K, 10-Q and selected foreign-issuer filings). Yahoo Finance valuation fields may include market cap, trailing/forward P/E, price-to-sales, EV/EBITDA and free cash flow. These fields are evidence inputs, not a complete discounted-cash-flow model; verify all material values against the latest filings.

For crypto, the current free module collects market cap, volume, seven-day price change and selected protocol TVL/category data. It does **not** claim that these metrics prove token value capture. Before a token is considered investable, manually verify supply/unlocks, fees/revenue, security, governance, liquidity and legal risks.

## Scoring and action discipline

- The core structural score is a thesis prior; tactical timing remains a separate score.
- Discovery scores rank research priorities and are not directly comparable with the core portfolio's opportunity score.
- New candidates do not automatically enter the 46-name portfolio.
- Review primary sources, valuation and risk before considering a trade.
- Missing fundamentals remain unavailable rather than being imputed as neutral or positive.

## Schedule

- Monday 08:00 UTC: full weekly core report plus free-source discovery.
- Daily 20:00 UTC: material event and new-candidate scan, including weekends for crypto.
- GitHub Actions cron uses UTC, so UK local time changes between GMT and BST.
- Event alerts are deduplicated using `agentic_state.json`; the weekly report always includes the discovery shortlist.

## GitHub Actions secrets

Required for email delivery:

- `EMAIL_PASSWORD` — Gmail app password (not the normal account password).
- `PORTFOLIO_EMAIL_RECIPIENT` — destination email address.
- `PORTFOLIO_EMAIL_SENDER` — sender Gmail address.

Optional free-source configuration:

- `SEC_USER_AGENT` — descriptive SEC request identity with contact email.
- `COINGECKO_DEMO_API_KEY` — optional free CoinGecko Demo API key.

No paid subscription or paid API key is required. If `EMAIL_PASSWORD` is missing, the scan runs but does not send email.

## Files to commit

- `snapshot.py`
- `free_discovery.py`
- `.github/workflows/Daily_snapshot.yml`
- `AGENTIC_ECONOMY_SETUP.md`

The workflow commits `agentic_state.json` after each successful run to maintain alert deduplication.

"""What data exists and which data tells which story.

Everything here is plain configuration: series IDs, plain-English names, and which
charts belong to which kind of topic. No numbers live in this file - numbers are
always fetched.
"""
from __future__ import annotations

# id -> title: plain-English name used in facts and on charts
#       units: percent | index | usd | usd_billions | usd_trillions | thousands | millions | count
#       org:   the agency that produces the number (FRED republishes it)
#       noun:  how to say it in a sentence ("the 30-year mortgage rate")
SERIES: dict[str, dict] = {
    # --- Fed and interest rates
    "DFEDTARU": {"title": "Fed funds target rate (upper limit)", "noun": "the Fed's target rate (upper limit)", "units": "percent", "org": "Federal Reserve Board", "freq": "daily", "decimals": 2},
    "DFF": {"title": "Effective federal funds rate", "noun": "the effective federal funds rate", "units": "percent", "org": "Federal Reserve Board", "freq": "daily", "decimals": 2},
    "DGS2": {"title": "2-year Treasury yield", "noun": "the 2-year Treasury yield", "units": "percent", "org": "Federal Reserve Board, H.15", "freq": "daily", "decimals": 2},
    "DGS10": {"title": "10-year Treasury yield", "noun": "the 10-year Treasury yield", "units": "percent", "org": "Federal Reserve Board, H.15", "freq": "daily", "decimals": 2},
    "DGS30": {"title": "30-year Treasury yield", "noun": "the 30-year Treasury yield", "units": "percent", "org": "Federal Reserve Board, H.15", "freq": "daily", "decimals": 2},
    "T10Y2Y": {"title": "10-year minus 2-year Treasury yield", "noun": "the gap between the 10-year and 2-year Treasury yields", "units": "percentage_points", "org": "Federal Reserve Bank of St. Louis", "freq": "daily", "decimals": 2},
    "MORTGAGE30US": {"title": "30-year fixed mortgage rate", "noun": "the average 30-year fixed mortgage rate", "units": "percent", "org": "Freddie Mac", "freq": "weekly", "decimals": 2},
    "TERMCBCCALLNS": {"title": "Average credit card interest rate", "noun": "the average credit card interest rate", "units": "percent", "org": "Federal Reserve Board, G.19", "freq": "quarterly", "decimals": 2},
    "BAMLH0A0HYM2": {"title": "High-yield bond spread", "noun": "the extra yield investors demand on risky corporate bonds", "units": "percentage_points", "org": "ICE BofA", "freq": "daily", "decimals": 2},
    # --- Inflation and prices (indexes; we chart the 12-month change)
    "CPIAUCNS": {"title": "Consumer prices (CPI, all items)", "noun": "consumer prices (CPI)", "units": "index", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1, "bls_id": "CUUR0000SA0"},
    "CPILFENS": {"title": "Core consumer prices (CPI excluding food and energy)", "noun": "core consumer prices (CPI without food and energy)", "units": "index", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1, "bls_id": "CUUR0000SA0L1E"},
    "PCEPI": {"title": "PCE price index", "noun": "the PCE price index, the Fed's preferred inflation gauge", "units": "index", "org": "U.S. Bureau of Economic Analysis", "freq": "monthly", "decimals": 1},
    "CUSR0000SAF11": {"title": "Grocery prices (CPI, food at home)", "noun": "grocery prices (CPI food at home)", "units": "index", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1},
    "CUSR0000SEHA": {"title": "Rent (CPI, rent of primary residence)", "noun": "rent (CPI rent of primary residence)", "units": "index", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1},
    "GASREGW": {"title": "Regular gasoline price (U.S. average)", "noun": "the average U.S. price of regular gasoline", "units": "usd", "org": "U.S. Energy Information Administration", "freq": "weekly", "decimals": 2, "per": "per gallon"},
    "APU0000708111": {"title": "Eggs, price per dozen (U.S. city average)", "noun": "the average price of a dozen eggs", "units": "usd", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 2, "per": "per dozen"},
    "APU000072610": {"title": "Electricity price per kWh (U.S. city average)", "noun": "the average price of electricity", "units": "usd", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 3, "per": "per kWh"},
    # --- Jobs and pay
    "UNRATE": {"title": "Unemployment rate", "noun": "the unemployment rate", "units": "percent", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1, "bls_id": "LNS14000000"},
    "PAYEMS": {"title": "Total nonfarm payroll jobs", "noun": "total nonfarm payroll jobs", "units": "thousands", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 0},
    "ICSA": {"title": "Initial jobless claims (weekly)", "noun": "new weekly jobless claims", "units": "count", "org": "U.S. Department of Labor", "freq": "weekly", "decimals": 0},
    "JTSJOL": {"title": "Job openings (JOLTS)", "noun": "job openings", "units": "thousands", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 0},
    "CES0500000003": {"title": "Average hourly earnings (private sector)", "noun": "average hourly earnings", "units": "usd", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 2, "per": "per hour"},
    # --- Growth and consumers
    "A191RL1Q225SBEA": {"title": "Real GDP growth (quarterly, annualized)", "noun": "real GDP growth (annualized)", "units": "percent", "org": "U.S. Bureau of Economic Analysis", "freq": "quarterly", "decimals": 1},
    "UMCSENT": {"title": "Consumer sentiment (University of Michigan)", "noun": "consumer sentiment", "units": "index", "org": "University of Michigan", "freq": "monthly", "decimals": 1},
    "PSAVERT": {"title": "Personal saving rate", "noun": "the personal saving rate", "units": "percent", "org": "U.S. Bureau of Economic Analysis", "freq": "monthly", "decimals": 1},
    "DRCCLACBS": {"title": "Credit card delinquency rate", "noun": "the credit card delinquency rate", "units": "percent", "org": "Federal Reserve Board", "freq": "quarterly", "decimals": 2},
    # --- Housing
    "MSPUS": {"title": "Median U.S. home sale price", "noun": "the median U.S. home sale price", "units": "usd", "org": "U.S. Census Bureau and HUD", "freq": "quarterly", "decimals": 0},
    "CSUSHPINSA": {"title": "U.S. home prices (Case-Shiller index)", "noun": "U.S. home prices (Case-Shiller)", "units": "index", "org": "S&P Dow Jones Indices", "freq": "monthly", "decimals": 1},
    # --- Markets
    "SP500": {"title": "S&P 500", "noun": "the S&P 500", "units": "index", "org": "S&P Dow Jones Indices", "freq": "daily", "decimals": 0},
    "NASDAQCOM": {"title": "Nasdaq Composite", "noun": "the Nasdaq Composite", "units": "index", "org": "Nasdaq", "freq": "daily", "decimals": 0},
    "VIXCLS": {"title": "VIX (stock market volatility index)", "noun": "the VIX, Wall Street's fear gauge", "units": "index", "org": "Cboe", "freq": "daily", "decimals": 1},
    "CBBTCUSD": {"title": "Bitcoin price (Coinbase)", "noun": "the price of Bitcoin", "units": "usd", "org": "Coinbase", "freq": "daily", "decimals": 0},
    # --- Commodities and the dollar
    "DCOILWTICO": {"title": "Crude oil price (WTI)", "noun": "the price of U.S. crude oil (WTI)", "units": "usd", "org": "U.S. Energy Information Administration", "freq": "daily", "decimals": 2, "per": "per barrel"},
    "DCOILBRENTEU": {"title": "Crude oil price (Brent)", "noun": "the price of Brent crude oil", "units": "usd", "org": "U.S. Energy Information Administration", "freq": "daily", "decimals": 2, "per": "per barrel"},
    "IQ12260": {"title": "Gold export price index", "noun": "the U.S. export price index for gold", "units": "index", "org": "U.S. Bureau of Labor Statistics", "freq": "monthly", "decimals": 1},
    "DTWEXBGS": {"title": "U.S. dollar index (broad, trade-weighted)", "noun": "the broad U.S. dollar index", "units": "index", "org": "Federal Reserve Board", "freq": "daily", "decimals": 1},
    # --- Government and the Fed's balance sheet
    "A091RC1Q027SBEA": {"title": "Federal interest payments (annual rate)", "noun": "federal government interest payments (annual rate)", "units": "usd_billions", "org": "U.S. Bureau of Economic Analysis", "freq": "quarterly", "decimals": 0},
    "WALCL": {"title": "Federal Reserve balance sheet (total assets)", "noun": "the Federal Reserve's balance sheet", "units": "usd_millions", "org": "Federal Reserve Board, H.4.1", "freq": "weekly", "decimals": 0},
    # --- AI and tech
    "IPG3344S": {"title": "U.S. semiconductor production index", "noun": "U.S. semiconductor production", "units": "index", "org": "Federal Reserve Board, G.17", "freq": "monthly", "decimals": 1},
    # --- Helper
    "USREC": {"title": "U.S. recession periods", "noun": "recession periods", "units": "flag", "org": "NBER", "freq": "monthly", "decimals": 0},
}

# Charts. kind:
#   lines        raw values, 1-3 series that share a unit
#   yoy          12-month % change of index series
#   bars_change  change from the previous period (e.g. jobs added per month)
#   bars         raw values as columns (e.g. quarterly GDP growth)
#   indexed      each series rebased to 100 at the start of the window (compare different things)
#   treasury     pulled from Treasury Fiscal Data
#   edgar        annual company figures from SEC 10-K filings
CHARTS: dict[str, dict] = {
    "fed_vs_2y": {"kind": "lines", "series": ["DFEDTARU", "DGS2"], "years": 5, "title": "The Fed's rate vs the 2-year Treasury yield", "teaches": "The 2-year yield moves on where traders think the Fed is heading next."},
    "fed_rate": {"kind": "lines", "series": ["DFEDTARU"], "years": 20, "title": "The Fed's target interest rate", "teaches": "The Fed's rate is the base price of borrowing money for everything else."},
    "yields_10_2": {"kind": "lines", "series": ["DGS10", "DGS2"], "years": 5, "title": "10-year vs 2-year Treasury yields", "teaches": "The 10-year is the benchmark that long-term loans are priced off."},
    "ten_year_long": {"kind": "lines", "series": ["DGS10"], "years": 20, "title": "10-year Treasury yield", "teaches": "A long view shows whether today's yield is normal or unusual."},
    "curve": {"kind": "lines", "series": ["T10Y2Y"], "years": 20, "zero_line": True, "title": "Yield curve: 10-year minus 2-year yield", "teaches": "Below zero means short-term borrowing costs more than long-term, which is unusual."},
    "mortgage_vs_10y": {"kind": "lines", "series": ["MORTGAGE30US", "DGS10"], "years": 5, "title": "30-year mortgage rate vs 10-year Treasury yield", "teaches": "Mortgage rates tend to follow the 10-year Treasury yield, not the Fed's rate directly."},
    "mortgage_long": {"kind": "lines", "series": ["MORTGAGE30US"], "years": 20, "title": "30-year fixed mortgage rate", "teaches": "Where today's mortgage rate sits against the last two decades."},
    "home_prices": {"kind": "lines", "series": ["MSPUS"], "years": 15, "title": "Median U.S. home sale price", "teaches": "Price plus rate is what sets the monthly payment."},
    "cpi_yoy": {"kind": "yoy", "series": ["CPIAUCNS", "CPILFENS"], "years": 6, "target": 2.0, "target_label": "Fed's 2% goal", "title": "Inflation: prices vs a year ago (CPI)", "teaches": "Inflation is how fast prices are rising compared with a year ago."},
    "grocery_yoy": {"kind": "yoy", "series": ["CUSR0000SAF11"], "years": 6, "title": "Grocery prices vs a year ago", "teaches": "This is the inflation people feel at the checkout."},
    "rent_yoy": {"kind": "yoy", "series": ["CUSR0000SEHA"], "years": 6, "title": "Rent vs a year ago", "teaches": "Rent is one of the biggest parts of the inflation number."},
    "gas_price": {"kind": "lines", "series": ["GASREGW"], "years": 5, "title": "U.S. regular gasoline price", "teaches": "Gas prices follow crude oil with a short delay."},
    "oil": {"kind": "lines", "series": ["DCOILWTICO"], "years": 5, "title": "Crude oil price (WTI)", "teaches": "Oil feeds into gas, shipping and almost every price in the economy."},
    "unemployment": {"kind": "lines", "series": ["UNRATE"], "years": 10, "title": "U.S. unemployment rate", "teaches": "The share of people who want a job and can't find one."},
    "payrolls": {"kind": "bars_change", "series": ["PAYEMS"], "years": 3, "title": "Jobs added or lost each month", "teaches": "Each bar is how many jobs the economy added or lost that month."},
    "claims": {"kind": "lines", "series": ["ICSA"], "years": 3, "title": "New jobless claims each week", "teaches": "The earliest warning sign for layoffs."},
    "openings": {"kind": "lines", "series": ["JTSJOL"], "years": 6, "title": "Job openings", "teaches": "Fewer openings means it is harder to switch jobs or get a raise."},
    "wages_yoy": {"kind": "yoy", "series": ["CES0500000003"], "years": 6, "title": "Pay growth vs a year ago", "teaches": "Compare this with inflation to see if paychecks are keeping up."},
    "gdp": {"kind": "bars", "series": ["A191RL1Q225SBEA"], "years": 5, "title": "U.S. economic growth by quarter (real GDP)", "teaches": "Two shrinking quarters in a row is the rule of thumb for a recession."},
    "sentiment": {"kind": "lines", "series": ["UMCSENT"], "years": 10, "title": "How consumers feel about the economy", "teaches": "How people feel affects how much they spend."},
    "sp500": {"kind": "lines", "series": ["SP500"], "years": 5, "title": "S&P 500", "teaches": "The S&P 500 is what most 401(k) stock funds track."},
    "stocks_indexed": {"kind": "indexed", "series": ["SP500", "NASDAQCOM"], "years": 3, "title": "S&P 500 vs Nasdaq (start = 100)", "teaches": "Both start at 100 so you can compare how far each has moved."},
    "vix": {"kind": "lines", "series": ["VIXCLS"], "years": 3, "title": "VIX: the stock market's fear gauge", "teaches": "Higher means investors expect bigger swings."},
    "nasdaq": {"kind": "lines", "series": ["NASDAQCOM"], "years": 5, "title": "Nasdaq Composite", "teaches": "The Nasdaq is heavy on tech and AI companies."},
    "bitcoin": {"kind": "lines", "series": ["CBBTCUSD"], "years": 3, "title": "Bitcoin price", "teaches": "Bitcoin swings far more than stocks."},
    "gold": {"kind": "lines", "series": ["IQ12260"], "years": 10, "title": "Gold price index (U.S. export prices)", "teaches": "People tend to buy gold when they worry about inflation or the dollar."},
    "dollar": {"kind": "lines", "series": ["DTWEXBGS"], "years": 5, "title": "U.S. dollar vs other currencies", "teaches": "A stronger dollar makes imports cheaper and U.S. exports dearer."},
    "card_rates": {"kind": "lines", "series": ["TERMCBCCALLNS"], "years": 15, "title": "Average credit card interest rate", "teaches": "Card rates move with the Fed's rate."},
    "card_delinquency": {"kind": "lines", "series": ["DRCCLACBS"], "years": 15, "title": "Credit card delinquency rate", "teaches": "The share of card balances that are behind on payments."},
    "saving_rate": {"kind": "lines", "series": ["PSAVERT"], "years": 10, "title": "Personal saving rate", "teaches": "How much of their income people have left to save."},
    "national_debt": {"kind": "treasury", "dataset": "debt", "years": 10, "title": "U.S. national debt", "teaches": "The total the federal government owes."},
    "debt_interest_rate": {"kind": "treasury", "dataset": "avg_rate", "years": 10, "title": "Average interest rate on U.S. government debt", "teaches": "As old cheap debt is replaced, the government's interest bill rises."},
    "interest_payments": {"kind": "lines", "series": ["A091RC1Q027SBEA"], "years": 15, "title": "Federal interest payments", "teaches": "Money spent on interest can't be spent on anything else."},
    "fed_balance_sheet": {"kind": "lines", "series": ["WALCL"], "years": 10, "title": "Federal Reserve balance sheet", "teaches": "When this shrinks the Fed is pulling money out of the system."},
    "chips": {"kind": "lines", "series": ["IPG3344S"], "years": 10, "title": "U.S. semiconductor production", "teaches": "How much chip-making is actually happening in the U.S."},
    "electricity": {"kind": "lines", "series": ["APU000072610"], "years": 10, "title": "Electricity price per kWh", "teaches": "Data centers need huge amounts of power, and households share the grid."},
    "ai_capex": {"kind": "edgar", "tickers": ["MSFT", "GOOGL", "AMZN"], "concept": "capex", "title": "Big Tech capital spending by fiscal year", "teaches": "This is the money going into data centers and chips."},
    "ticker_revenue": {"kind": "edgar", "tickers": [], "concept": "revenue", "title": "Annual revenue from company filings", "teaches": "Revenue shows whether the spending is turning into sales."},
}

# Upcoming data releases. release_id is FRED's ID (dates need a FRED API key).
RELEASES: dict[str, dict] = {
    "cpi": {"name": "Consumer Price Index (CPI) report", "release_id": 10, "schedule_url": "https://www.bls.gov/schedule/news_release/cpi.htm", "why": "The main inflation report."},
    "jobs": {"name": "Jobs report (Employment Situation)", "release_id": 50, "schedule_url": "https://www.bls.gov/schedule/news_release/empsit.htm", "why": "Unemployment rate and jobs added."},
    "pce": {"name": "PCE inflation (Personal Income and Outlays)", "release_id": 54, "schedule_url": "https://www.bea.gov/news/schedule", "why": "The inflation gauge the Fed watches most closely."},
    "gdp": {"name": "GDP report", "release_id": 53, "schedule_url": "https://www.bea.gov/news/schedule", "why": "How fast the economy grew."},
    "jolts": {"name": "Job openings report (JOLTS)", "release_id": 192, "schedule_url": "https://www.bls.gov/schedule/news_release/jolts.htm", "why": "How many jobs employers are trying to fill."},
    "claims": {"name": "Weekly jobless claims", "release_id": 180, "schedule_url": "https://www.dol.gov/ui/data.pdf", "why": "Out every Thursday; the earliest read on layoffs."},
    "mortgage": {"name": "Freddie Mac weekly mortgage rate survey", "release_id": 190, "schedule_url": "https://www.freddiemac.com/pmms", "why": "Out every Thursday."},
    "fomc": {"name": "Federal Reserve interest rate decision (FOMC)", "release_id": 101, "schedule_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "why": "When the Fed announces whether rates change."},
    "sentiment": {"name": "University of Michigan consumer sentiment", "release_id": 91, "schedule_url": "http://www.sca.isr.umich.edu/", "why": "How households feel about the economy."},
    "earnings": {"name": "Company earnings reports", "release_id": None, "schedule_url": "https://www.sec.gov/edgar/search/", "why": "Check each company's investor-relations page for its next report date."},
}

# Topic categories. keywords are matched as whole words/phrases against the topic text.
# is/are: grammar for the label in title templates.
CATEGORIES: dict[str, dict] = {
    "housing": {
        "label": "Mortgage Rates", "plural": True, "lead_series": "MORTGAGE30US",
        "keywords": ["mortgage", "mortgages", "housing", "home prices", "home price", "homebuyer", "homebuyers", "real estate", "refinance", "rent", "housing market", "home sales"],
        "charts": ["mortgage_vs_10y", "mortgage_long", "home_prices", "ten_year_long", "rent_yoy"],
        "releases": ["mortgage", "cpi", "fomc"],
    },
    "bonds": {
        "label": "Treasury Yields", "plural": True, "lead_series": "DGS10",
        "keywords": ["treasury", "treasuries", "yield", "yields", "bond", "bonds", "10-year", "10 year", "bond market", "yield curve"],
        "charts": ["ten_year_long", "yields_10_2", "mortgage_vs_10y", "curve", "debt_interest_rate"],
        "releases": ["fomc", "cpi", "jobs"],
    },
    "fed": {
        "label": "The Fed", "plural": False, "lead_series": "DFEDTARU",
        "keywords": ["fed", "fomc", "federal reserve", "rate cut", "rate cuts", "rate hike", "rate hikes", "interest rate", "interest rates", "powell", "warsh", "central bank", "monetary policy"],
        "charts": ["fed_vs_2y", "cpi_yoy", "unemployment", "fed_rate", "mortgage_vs_10y"],
        "releases": ["fomc", "cpi", "jobs", "pce"],
    },
    "inflation": {
        "label": "Inflation", "plural": False, "lead_series": "CPIAUCNS",
        "keywords": ["inflation", "cpi", "prices", "price", "groceries", "grocery", "cost of living", "tariff", "tariffs", "pce", "stagflation", "eggs", "affordability"],
        "charts": ["cpi_yoy", "grocery_yoy", "gas_price", "wages_yoy", "fed_vs_2y", "rent_yoy"],
        "releases": ["cpi", "pce", "fomc"],
    },
    "jobs": {
        "label": "The Job Market", "plural": False, "lead_series": "UNRATE",
        "keywords": ["jobs", "job", "unemployment", "layoff", "layoffs", "payrolls", "payroll", "labor market", "hiring", "wages", "jobless", "workers", "employment"],
        "charts": ["unemployment", "payrolls", "claims", "openings", "wages_yoy"],
        "releases": ["jobs", "claims", "jolts", "fomc"],
    },
    "oil": {
        "label": "Oil Prices", "plural": True, "lead_series": "DCOILWTICO",
        "keywords": ["oil", "crude", "opec", "gas prices", "gasoline", "energy", "brent", "barrel", "iran", "strait of hormuz", "pump"],
        "charts": ["oil", "gas_price", "cpi_yoy", "fed_vs_2y"],
        "releases": ["cpi", "fomc"],
    },
    "stocks": {
        "label": "The Stock Market", "plural": False, "lead_series": "SP500",
        "keywords": ["stock market", "stocks", "s&p", "s&p 500", "nasdaq", "dow", "rally", "crash", "correction", "selloff", "sell-off", "bubble", "401k", "401(k)", "wall street", "bear market", "bull market", "all-time high", "record high"],
        "charts": ["sp500", "stocks_indexed", "vix", "ten_year_long"],
        "releases": ["fomc", "cpi", "jobs", "earnings"],
    },
    "ai": {
        "label": "The AI Boom", "plural": False, "lead_series": "NASDAQCOM",
        "keywords": ["ai", "artificial intelligence", "nvidia", "chip", "chips", "semiconductor", "semiconductors", "data center", "data centers", "openai", "anthropic", "hyperscaler", "hyperscalers", "gpu", "big tech", "tech stocks", "capex"],
        "charts": ["ai_capex", "nasdaq", "ticker_revenue", "chips", "electricity", "stocks_indexed"],
        "releases": ["earnings", "fomc"],
    },
    "debt": {
        "label": "The National Debt", "plural": False, "lead_series": "TREASURY_DEBT",
        "keywords": ["national debt", "deficit", "debt ceiling", "shutdown", "government spending", "treasury auction", "budget", "federal debt", "interest payments", "moody's", "downgrade"],
        "charts": ["national_debt", "debt_interest_rate", "interest_payments", "ten_year_long"],
        "releases": ["fomc", "gdp"],
    },
    "recession": {
        "label": "The Economy", "plural": False, "lead_series": "A191RL1Q225SBEA",
        "keywords": ["recession", "gdp", "slowdown", "economy", "economic growth", "soft landing", "hard landing", "consumer spending", "consumer sentiment"],
        "charts": ["gdp", "unemployment", "curve", "sentiment", "sp500"],
        "releases": ["gdp", "jobs", "sentiment", "fomc"],
    },
    "gold_dollar": {
        "label": "Gold and the Dollar", "plural": True, "lead_series": "DTWEXBGS",
        "keywords": ["gold", "dollar", "currency", "currencies", "dxy", "de-dollarization", "silver", "yen", "euro"],
        "charts": ["gold", "dollar", "ten_year_long", "cpi_yoy"],
        "releases": ["fomc", "cpi"],
    },
    "credit": {
        "label": "Consumer Debt", "plural": False, "lead_series": "TERMCBCCALLNS",
        "keywords": ["credit card", "credit cards", "consumer debt", "delinquency", "delinquencies", "savings", "saving rate", "buy now pay later", "student loans", "auto loans", "household debt"],
        "charts": ["card_rates", "card_delinquency", "saving_rate", "fed_vs_2y"],
        "releases": ["fomc", "cpi"],
    },
    "crypto": {
        "label": "Bitcoin", "plural": False, "lead_series": "CBBTCUSD",
        "keywords": ["bitcoin", "crypto", "cryptocurrency", "ethereum", "btc", "stablecoin", "stablecoins"],
        "charts": ["bitcoin", "stocks_indexed", "dollar"],
        "releases": ["fomc", "cpi"],
    },
}

# Used when a topic matches nothing above, and to top up a package to three charts.
DEFAULT_CHARTS = ["fed_vs_2y", "cpi_yoy", "sp500", "unemployment"]

# The four "what it means for you" angles always get a real number behind them.
WALLET = {
    "mortgage": {"label": "Mortgage", "series": "MORTGAGE30US", "also": ["MSPUS"]},
    "job": {"label": "Job", "series": "UNRATE", "also": []},
    "groceries": {"label": "Groceries", "series": "CUSR0000SAF11", "also": []},
    "retirement": {"label": "401(k)", "series": "SP500", "also": []},
}

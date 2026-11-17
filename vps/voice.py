"""Plain-English wording used by the built-in templates (no LLM needed).

No numbers live here. Each topic category has: a one-line explanation a 12-year-old
could follow, a hook question, the name of its headline number, a thumbnail word, and
symbolic B-roll ideas. B-roll is always generic - no real people, no real events.
"""
from __future__ import annotations

CATEGORY_VOICE: dict[str, dict] = {
    "housing": {
        "plain": "A mortgage rate is the price of borrowing money to buy a home. When it goes up, the exact same house costs more every month.",
        "question": "What actually sets your mortgage rate, and what does this do to a monthly payment?",
        "metric": "Mortgage Rates", "metric_plural": True, "thumb": "MORTGAGES",
        "broll": [
            ("Slow aerial drone shot gliding over a quiet suburban neighborhood at golden hour, rows of similar houses, soft haze, cinematic", "homes and neighborhoods"),
            ("Close-up of a house key resting on a kitchen counter beside a calculator and blank paperwork, soft window light, slow push-in", "the cost of buying"),
            ("A 'for sale' style blank yard sign in front of a generic house, shallow depth of field, gentle wind in the trees", "the housing market"),
        ],
    },
    "bonds": {
        "plain": "A Treasury yield is the interest the U.S. government pays to borrow money. Banks use it as the starting point for what they charge you.",
        "question": "Why should anyone who doesn't own a single bond care about this number?",
        "metric": "The 10-Year Yield", "metric_plural": False, "thumb": "YIELDS",
        "broll": [
            ("Abstract animation of glowing lines rising and falling like a heartbeat across a dark grid, slow camera drift, cinematic", "interest rates moving"),
            ("Macro shot of stacked coins of different heights on a dark reflective table, slow dolly, moody lighting", "the cost of money"),
            ("Wide shot of a grand neoclassical government-style building at dusk, generic and unnamed, light traffic trails", "government borrowing"),
        ],
    },
    "fed": {
        "plain": "The Fed sets the base price of borrowing money in the U.S. Raise it and loans get more expensive; lower it and they get cheaper.",
        "question": "What does the Fed's rate actually change in your everyday life?",
        "metric": "The Fed's Rate", "metric_plural": False, "thumb": "THE FED",
        "broll": [
            ("Empty wood-paneled boardroom with a long table and empty chairs, morning light through tall windows, slow push-in, no people", "a big decision"),
            ("Close-up of a large dial being turned slowly by a gloved hand, industrial control room, shallow depth of field", "turning the rate dial"),
            ("Abstract animation of glowing lines rising and falling like a heartbeat across a dark grid, slow camera drift", "interest rates moving"),
        ],
    },
    "inflation": {
        "plain": "Inflation is how fast prices are rising. If it is higher than your raise, your paycheck buys less than it did a year ago.",
        "question": "What is this number really measuring, and where do you feel it?",
        "metric": "Inflation", "metric_plural": False, "thumb": "INFLATION",
        "broll": [
            ("Slow tracking shot down a supermarket aisle with full shelves, generic unbranded products, soft overhead light, no people", "prices at the store"),
            ("Close-up of a shopping cart being pushed, only hands visible, generic unbranded groceries, shallow depth of field", "the weekly shop"),
            ("Macro shot of a paper receipt curling out of a register with blurred unreadable print, warm light", "the bill adding up"),
        ],
    },
    "jobs": {
        "plain": "The job market is how easy it is to find work. When it weakens, it takes longer to get hired and harder to ask for a raise.",
        "question": "Is it getting easier or harder to find a job right now?",
        "metric": "Unemployment", "metric_plural": False, "thumb": "JOBS",
        "broll": [
            ("Wide shot of an empty modern open-plan office at dawn, rows of desks and dark monitors, slow dolly, no people", "the workplace"),
            ("Close-up of hands typing on a laptop at a kitchen table, face not visible, soft morning light", "looking for work"),
            ("Time-lapse of anonymous commuters as motion-blurred silhouettes crossing a station concourse, faces not visible", "people heading to work"),
        ],
    },
    "oil": {
        "plain": "Oil is in almost everything: gas, shipping, plastic, food delivery. When a barrel costs more, so does nearly everything else, a little later.",
        "question": "How does the price of a barrel of oil end up in your grocery bill?",
        "metric": "Oil", "metric_plural": False, "thumb": "OIL",
        "broll": [
            ("Wide shot of oil pump jacks nodding slowly against a sunset sky, heat haze, cinematic", "where oil comes from"),
            ("Close-up of a generic unbranded fuel nozzle in a car, numbers on the pump out of focus and unreadable", "filling the tank"),
            ("Aerial shot of a generic cargo ship crossing open ocean, long wake, calm water", "moving goods around the world"),
        ],
    },
    "stocks": {
        "plain": "The stock market is a giant auction for pieces of companies. Most people own it without thinking about it, through a 401(k).",
        "question": "What does this mean if the only stocks you own are in a 401(k)?",
        "metric": "The S&P 500", "metric_plural": False, "thumb": "STOCKS",
        "broll": [
            ("Abstract wall of glowing green and red candlestick shapes with no readable text, slow camera drift, dark room", "the market moving"),
            ("Slow dolly through an empty trading floor at dawn, dark monitors, chairs pushed in, no people", "Wall Street before the open"),
            ("Close-up of a phone on a desk showing an abstract unlabeled line chart, hand reaching for a coffee cup, face not visible", "checking your account"),
        ],
    },
    "ai": {
        "plain": "AI runs on giant warehouses full of computer chips. Building them costs enormous amounts of money, and investors are betting it pays off.",
        "question": "Who is paying for the AI boom, and is it showing up in real numbers yet?",
        "metric": None, "metric_plural": False, "thumb": "AI BOOM",
        "broll": [
            ("Slow dolly down a long aisle of server racks with blinking blue lights, cool mist, cinematic, no people", "inside a data center"),
            ("Macro shot of a generic computer chip on a circuit board with light sweeping across it, no logos or markings", "the chips behind AI"),
            ("Aerial shot of a huge windowless warehouse-style building beside power lines at dusk, generic and unnamed", "the scale of the build-out"),
        ],
    },
    "debt": {
        "plain": "The national debt is everything the U.S. government has borrowed and not paid back. Like any loan, it comes with an interest bill.",
        "question": "Who pays the interest on this, and does it ever touch your wallet?",
        "metric": "The National Debt", "metric_plural": False, "thumb": "U.S. DEBT",
        "broll": [
            ("Wide shot of a grand neoclassical government-style building at dusk, generic and unnamed, light traffic trails", "government finances"),
            ("Macro shot of a tall stack of blank paper growing in time-lapse on a wooden desk, dramatic side light", "the bill piling up"),
            ("Abstract animation of a counter made of spinning blank mechanical tiles, no readable digits, dark background", "a number that keeps growing"),
        ],
    },
    "recession": {
        "plain": "The economy is everyone's buying, selling and working added together. A recession is when that total shrinks for a while.",
        "question": "Is the economy actually slowing down, or does it just feel that way?",
        "metric": "GDP Growth", "metric_plural": False, "thumb": "RECESSION?",
        "broll": [
            ("Time-lapse of a generic city skyline from day to night, clouds racing, lights coming on", "the whole economy"),
            ("Slow tracking shot along a quiet main street with generic unbranded storefronts, early morning, no people", "main street"),
            ("Wide shot of shipping containers stacked at a generic port, cranes moving slowly, overcast light", "goods moving"),
        ],
    },
    "gold_dollar": {
        "plain": "The dollar's value is what it can buy compared with other countries' money. Gold is where some people park savings when they worry about it.",
        "question": "What does the dollar's value change for someone who never leaves the country?",
        "metric": None, "metric_plural": False, "thumb": "THE DOLLAR",
        "broll": [
            ("Macro shot of plain unmarked gold bars on dark velvet with a slow light sweep, no stamps or text", "gold"),
            ("Close-up of a spinning globe on a desk beside generic unmarked banknotes out of focus, warm lamp light", "money around the world"),
            ("Abstract animation of two glowing lines crossing over each other on a dark grid, slow drift", "currencies trading places"),
        ],
    },
    "credit": {
        "plain": "A credit card balance is a loan with one of the highest interest rates most people ever pay. When rates rise, carrying a balance costs more.",
        "question": "What does this mean if you carry a balance from month to month?",
        "metric": "Credit Card Rates", "metric_plural": True, "thumb": "CARD DEBT",
        "broll": [
            ("Close-up of a hand tapping a blank unbranded card on a payment terminal, face not visible, shallow depth of field", "paying with plastic"),
            ("Macro shot of a stack of blank envelopes and a calculator on a kitchen table, evening lamp light", "the monthly bills"),
            ("Top-down shot of a wallet opening to show blank unbranded cards, slow push-in", "what's in your wallet"),
        ],
    },
    "crypto": {
        "plain": "Bitcoin is digital money with no government behind it. Its price is set only by what the next buyer will pay, so it swings a lot.",
        "question": "What actually moves this price up and down?",
        "metric": "Bitcoin", "metric_plural": False, "thumb": "BITCOIN",
        "broll": [
            ("Abstract network of glowing nodes and lines pulsing in a dark space, slow camera orbit", "a digital network"),
            ("Slow dolly past rows of humming computer rigs with small colored lights in a dim warehouse, no people", "the machines behind crypto"),
            ("Close-up of a phone on a desk showing an abstract unlabeled jagged line chart, face not visible", "a volatile price"),
        ],
    },
}

GENERIC_VOICE = {
    "plain": "Here is the short version of what happened, in everyday words.",
    "question": "Why is this happening, and what does it mean for your wallet?",
    "metric": None, "metric_plural": False, "thumb": "EXPLAINED",
    "broll": [
        ("Time-lapse of a generic city skyline from day to night, clouds racing, lights coming on", "the economy"),
        ("Abstract animation of glowing lines rising and falling like a heartbeat across a dark grid, slow camera drift", "numbers moving"),
        ("Close-up of hands holding a coffee cup beside a laptop showing an abstract unlabeled chart, face not visible", "following the news"),
    ],
}

WALLET_LINES = {
    "mortgage": "If you already have a fixed-rate mortgage, your payment does not change. This matters if you are buying, refinancing or have an adjustable rate.",
    "job": "Explain what this means for someone job-hunting or asking for a raise: a tighter market gives workers more leverage, a looser one gives employers more.",
    "groceries": "This is the change in average grocery prices across the country. Your own basket can be higher or lower.",
    "retirement": "Most 401(k) stock funds follow the S&P 500. This is a snapshot of where it stands, not a prediction and not a reason to change anything.",
}

# Appended to every B-roll prompt, whoever wrote it.
BROLL_SAFETY_SUFFIX = (
    "Fictional generic scene. No real people, no recognizable faces, no real brands or logos, "
    "no readable on-screen text, not a depiction of any real event."
)
ILLUSTRATIVE_LABEL = "ILLUSTRATIVE - AI-generated"

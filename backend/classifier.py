"""
FinanceAI Transaction Classifier
Architecture: 9-step pipeline with weighted scoring, merchant aliases,
per-user + global correction memory, and ambiguity resolution.
"""
import re
import hashlib
from typing import Optional, Tuple, Dict, List, Any

# ── 1. MERCHANT ALIAS TABLE ──────────────────────────────────────────────────
# Pre-normalization patterns — applied BEFORE stripping symbols
PRE_NORM_ALIASES = {
    'costco gas': 'costco gas station',
    'google *youtube': 'youtube premium',
    'dd *sprouts': 'sprouts delivery',
    'sq *el mixteco': 'el mixteco restaurant',
    'sq *yummy': 'yummy fresh restaurant',
    'sq *villa': 'villa restaurant',
    'dd *safeway': 'safeway delivery',
    'dd *kroger': 'kroger delivery',
    'dd *whole': 'whole foods delivery',
    'dd *costco': 'costco delivery',
    'google*youtube': 'youtube premium',
    'google *google one': 'google one',
    'google *play': 'google play',
    'clear *clearme': 'clearme subscription',
    'raz*indigo': 'indigo airlines',
    'raz* indigo': 'indigo airlines',
    'raz*chirukaanuka': 'indigo airlines',
    'clear*clearme': 'clearme subscription',
    'apple *': 'apple subscription',
    'uber *eats': 'uber eats',
    'uber* eats': 'uber eats',
    'ubereats': 'uber eats',
    'uber eats': 'uber eats',
    'in-n-out': 'innout burger',
    'in n out': 'innout burger',
}

MERCHANT_ALIASES = {
    # Amazon variants
    'amzn mktp':        'amazon',
    'amzn':             'amazon',
    'amazon mktplace':  'amazon',
    'amazon mktpl':     'amazon',
    'amazon.com':       'amazon',
    # Uber variants
    'uber eats':        'uber eats',
    'ubereats':         'uber eats',
    'uber *eats':       'uber eats',
    # DoorDash variants
    'dd *':             'doordash',
    'dsh*':             'doordash',
    'doordash':         'doordash',
    # Starbucks
    'sbux':             'starbucks',
    # Whole Foods
    'wholefds':         'whole foods',
    'wholefoodsmkt':    'whole foods',
    'wfm':              'whole foods',
    # Walmart
    'wal-mart':         'walmart',
    'wmt':              'walmart',
    # Apple
    'apple.com/bill':   'apple subscription',
    'itunes':           'apple subscription',
    'apple one':        'apple subscription',
    # Google
    'google *youtube':  'youtube premium',
    'google*youtube':   'youtube premium',
    'google *google one': 'google one',
    # Netflix
    'netflix.com':      'netflix',
    # Spotify
    'spotify usa':      'spotify',
    # PayPal wrapper
    'paypal *':         '',   # strip, keep what follows
    # Square/Toast wrappers
    'sq *':             '',   # strip, keep what follows
    'tst* ':            '',   # strip, keep what follows
    'toast':            '',   # strip if prefix
}

# ── 2. NOISE PATTERNS TO STRIP IN NORMALIZATION ──────────────────────────────
STRIP_PATTERNS = [
    r'\b\d{4,}\b',                          # store/auth numbers 4+ digits
    r'\b[A-Z]{2}\b$',                        # trailing state code
    r'\b(seattle|new york|chicago|los angeles|san francisco|houston|phoenix|'
     r'philadelphia|san antonio|san diego|dallas|san jose|austin|jacksonville|'
     r'fort worth|columbus|charlotte|indianapolis|san francisco|denver|'
     r'washington|nashville|oklahoma|el paso|boston|portland|las vegas|'
     r'memphis|louisville|baltimore|milwaukee|albuquerque|tucson|fresno|'
     r'sacramento|mesa|kansas|atlanta|omaha|colorado|raleigh|miami|'
     r'minneapolis|cleveland|wichita|arlington|new orleans|bakersfield|'
     r'tampa|aurora|anaheim|santa ana|corpus christi|riverside|st louis|'
     r'lexington|pittsburgh|anchorage|stockton|cincinnati|st paul|greensboro|'
     r'toledo|newark|plano|henderson|lincoln|buffalo|fort wayne|jersey city|'
     r'chula vista|orlando|st petersburg|norfolk|chandler|laredo|madison|'
     r'durham|lubbock|winston|garland|glendale|hialeah|reno|baton rouge|'
     r'irvine|chesapeake|north las vegas|gilbert|scottsdale|shoreline|bellevue|'
     r'redmond|bothell|edmonds|kirkland|tacoma|everett|issaquah|enumclaw|'
     r'sunnyvale|san mateo|palo alto|mountain view|cupertino|fremont|hayward|'
     r'oakland|berkeley|richmond|concord|antioch|santa rosa|petaluma|'
     r'san jose|san bruno|south san francisco|daly city|san leandro|'
     r'milpitas|santa clara|sunnyvale|campbell|los gatos|saratoga|'
     r'los altos|menlo park|atherton|portola valley|woodside|san carlos|'
     r'foster city|burlingame|millbrae|san francisco|daly city|colma|'
     r'south san francisco|brisbane|pacifica|half moon bay)\b',
    r'\b(wa|ca|ny|tx|fl|il|pa|oh|ga|nc|mi|nj|va|az|ma|in|tn|mo|md|wi|'
     r'mn|co|al|sc|la|ky|or|ok|ct|ut|ia|nv|ar|ms|ks|ne|nm|id|wv|hi|'
     r'nh|me|ri|mt|de|sd|nd|ak|vt|wy|dc)\b',  # state abbreviations
    r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b',    # phone numbers
    r'\bx+\d+\b',                            # masked account refs
    r'#\d+',                                 # store numbers with #
    r'\*+\w+\b',                             # auth codes after *
    r'\b(ach|debit|purchase|checkcard|pos|visa|mc|mastercard|'
     r'electron|contactless|tap|chip|swipe)\b',
    r'\b(des|id|indn|co id|ppd|ccd|web|tel)\b',  # ACH fields
    r'\s{2,}',                               # multiple spaces → single
]

COMPILED_STRIP = [re.compile(p, re.IGNORECASE) for p in STRIP_PATTERNS]

# Payment-processor wrappers that prefix the REAL merchant name (e.g. "SQ *BIRYANI BISTRO").
# These must be stripped BEFORE the generic "*word" auth-code pattern, otherwise the
# merchant's first word gets deleted. Captures everything after the prefix.
PROCESSOR_PREFIX_RE = re.compile(
    r'^(?:sq|tst|toast|dd|dsh|paypal|pp|sp|clkbank|wpy|gum|fs|ven(?:mo)?)\s*\*+\s*',
    re.IGNORECASE)

# Summary/junk row indicators
SUMMARY_KEYWORDS = [
    'opening balance', 'closing balance', 'statement balance',
    'beginning balance', 'ending balance', 'payment due',
    'minimum payment', 'new balance', 'previous balance',
    'total new charges', 'total payments', 'total credits',
    'finance charge', 'interest charge', 'annual fee notice',
    'continued on', 'page total', 'subtotal',
]

# ── 3. TRANSACTION TYPE PATTERNS (precompiled) ────────────────────────────────

# Reimbursements — check early
REIMBURSEMENT_RE = re.compile(
    r'\b(reimbursement|reimburse|expense.?refund|expense.?repay|rebate|'
     r'employer.?credit|expense.?report)\b', re.IGNORECASE)

# Cash/ATM
CASH_RE = re.compile(
    r'\b(shoreline.?club.?\d+.?withdrwl|eft.?\d+.?withdrwl|'
     r'withdrawal.?eft|withdrwl)\b', re.IGNORECASE)

CASH_RE = re.compile(
    r'\b(atm.?withdrawal|cash.?withdrawal|cash.?advance|atm.?disbursement|'
     r'atm.?fee|cash.?back.?at.?pos|withdrwl|withdrawal)\b', re.IGNORECASE)

# CC Payments
CC_PAYMENT_RE = re.compile(
    r'\b(american.?express.?des.?ach|amex.?des.?ach|'
     r'chase.?credit.?crd.?des.?epay|chase.?crd.?epay|'
     r'applecard.?gsbank.?des.?payment|'
     r'discover.?des.?payment|citi.?des.?payment|'
     r'capital.?one.?des.?payment)\b', re.IGNORECASE)

CC_PAYMENT_RE = re.compile(
    r'\b(automatic.?payment|payment.?thank.?you|thank.?you.?payment|autopay|auto.?pay|'
     r'online.?payment|mobile.?payment|payment.?received|'
     r'minimum.?payment|cc.?payment|credit.?card.?payment|'
     r'amex.?payment|chase.?payment|citi.?payment|discover.?payment|'
     r'bofa.?payment|bank.?of.?america.?payment|apple.?card.?payment|'
     r'capital.?one.?payment|'
     r'american.?express.*\bpmt\b|amex.*\bpmt\b|'
     r'chase.?credit.?crd|chase.?crd.*epay|'
     r'applecard|gsbank.*payment|'
     r'discover.*\bpmt\b|citi.*\bpmt\b|capital.?one.*\bpmt\b)\b', re.IGNORECASE)

# Loan/mortgage
LOAN_RE = re.compile(
    r'\b(mortgage|mtg.?pymt|mtg.?payment|home.?loan|auto.?loan|'
     r'car.?loan|student.?loan|personal.?loan|loan.?payment|'
     r'bmw.?financial|bmw.?bank|bmwfs|ally.?financial|honda.?financial|toyota.?financial|'
     r'ford.?credit|gm.?financial|nissan.?motor|hyundai.?finance|'
     r'lakeview|quicken.?loan|rocket.?mortgage|nationstar|'
     r'mr.?cooper|freedom.?mortgage|pennymac|loandepot|'
     r'sallie.?mae|navient|fedloan|mohela|nelnet|great.?lakes)\b',
    re.IGNORECASE)

# Income/payroll — check before ACH
INCOME_RE = re.compile(
    r'\b(payroll|direct.?dep|direct.?deposit|salary|wages|compensation|'
     r'ach.?credit.?(payroll|salary|wages)|employer|stripe.?inc|'
     r'adp|paychex|gusto|quickbooks.?payroll|intuit.?payroll|'
     r'bamboohr|rippling|justworks|zenefits|trinet|'
     r'social.?security|ssa|pension|retirement|annuity|'
     r'unemployment|benefits.?payment|tax.?refund|irs.?refund)\b',
    re.IGNORECASE)

# Refunds
REFUND_RE = re.compile(
    r'\b(refund|reversal|chargeback|dispute.?credit|credit.?adjustment|'
     r'return.?credit|merchandise.?return|cancelled.?order|'
     r'price.?adjustment|goodwill.?credit)\b', re.IGNORECASE)

# Transfers — P2P (check after income/payroll)
TRANSFER_RE = re.compile(
    r'\b(zelle|venmo|cash.?app|apple.?cash|google.?pay.?send|'
     r'wire.?transfer|internal.?transfer|account.?transfer|'
     r'transfer.?to|transfer.?from|trnsfr|ext.?trnsfr|xoom|western.?union|moneygram|'
     r'wise|remitly|worldremit|paypal.?transfer|fb.?pay)\b',
    re.IGNORECASE)

# Financing fees — exclude
FINANCING_FEE_RE = re.compile(
    r'\b(pay.?over.?time|plan.?it.?fee|installment.?fee|'
     r'cash.?advance.?fee|balance.?transfer.?fee|late.?fee|'
     r'foreign.?transaction.?fee|annual.?membership.?fee|'
     r'new.?pay.?over.?time)\b', re.IGNORECASE)

# Statement credits (Amex)
STATEMENT_CREDIT_RE = re.compile(
    r'\b(platinum.?.*credit|gold.?.*credit|amex.?clear|'
     r'clear.?plus.?credit|card.?credit|statement.?credit|'
     r'annual.?credit|travel.?credit|digital.?entertainment.?credit|'
     r'walmart.?credit|uber.?cash|saks.?credit|streaming.?credit|'
     r'hotel.?credit|dining.?credit|equinox.?credit|'
     r'tsa.?credit|global.?entry.?credit|cell.?phone.?credit|'
     r'cashback|cash.?back.?reward|rewards.?redemption)\b',
    re.IGNORECASE)

# Payment summaries to exclude
PAYMENT_SUMMARY_RE = re.compile(
    r'^(payments.{0,5}credits|payments.?and.?credits|total.?payments|'
     r'new.?balance|minimum.?payment.?due|statement.?balance|'
     r'previous.?balance)$', re.IGNORECASE)

# ── 4. CATEGORY PATTERNS (precompiled weighted) ───────────────────────────────
# Each entry: (pattern, score, category)
# Higher score = stronger signal

RAW_CATEGORY_PATTERNS = [
    # ── Food & Dining ──
    (r'\b(restaurant|cafe|coffee|starbucks|mcdonald|burger|pizza|sushi|taco|'
     r'diner|bistro|bakery|donut|dunkin|chipotle|subway|wendy|kfc|popeye|'
     r'panda|chick.?fil|five.?guys|shake.?shack|in.?n.?out|whataburger|'
     r'ihop|denny|waffle.?house|cracker.?barrel|olive.?garden|red.?lobster|'
     r'applebee|chilis|outback|cheesecake.?factory|panera|jason.?deli|'
     r'dominos?|dominoes?|pizza.?hut|papa.?john|little.?caesar|sbarro)\b', 4, 'Food & Dining'),
    (r'\b(pub|tavern|deli|food.?truck|buffet|steakhouse|seafood|ramen|'
     r'pho|smoothie|juice.?bar|eatery|kitchen|brasserie|trattoria|'
     r'cantina|taqueria|pizzeria|grill|brew.?pub|gastropub)\b', 4, 'Food & Dining'),
    (r'\b(ethiopian|eritrean|cuisine|cuisin|cuisi|delish|african|caribbean|jamaican|thai|vietnamese|korean|mediterranean|greek|turkish|persian|lebanese|moroccan)\b', 4, 'Food & Dining'),
    (r'\b(singapore|dubai|london|paris|tokyo|seoul|bangkok|amsterdam)\b', 2, 'Food & Dining'),

    (r'\b(almond.?house|burma.?burma|premium.?lifestyle|onamalu|'
     r'ikea.?india|hpcl|fern.?thai|yummy.?fresh|el.?mixteco)\b', 3, 'Food & Dining'),
    (r'\b(bagel|wok|ramen|menya|pao|noodle|noodles|udon|pho|banh.?mi|poke|dumpling|dim.?sum|hotpot|hot.?pot|izakaya|teriyaki|katsu|bibimbap|congee|gelato|creamery|patisserie|creperie|taqueria)\b', 4, 'Food & Dining'),
    (r'\b(dosa|curry|biryani|tandoor|halal|kebab|shawarma|falafel|hummus|'
     r'dim.?sum|dumpling|wonton|banh|bubble.?tea|milk.?tea|boba|'
     r'spring.?roll|fried.?rice|pad.?thai|poke|acai|'
     r'mayuri|indian.?restaurant|nepali|desi|punjabi|masala|charminar|'
     r'spice|namaste|maharaja|taj.?restaurant)\b', 4, 'Food & Dining'),
    (r'\b(latte|espresso|cappuccino|americano|matcha|chai)\b', 3, 'Food & Dining'),
    (r'ubereats|uber.?eats|doordash|grubhub|postmates|seamless|caviar|gopuff', 4, 'Food & Dining'),
    (r'tst\s*\*|sq\s*\*.*(?:cafe|coffee|pizza|burger|grill|kitchen|bar|brew)', 3, 'Food & Dining'),
    (r'\b(innout|in.?n.?out|qdoba|chipotle|panera|five.?guys|whataburger|'
     r'culvers|wendys|arbys|jack.?in.?the.?box|del.?taco|el.?pollo)\b', 4, 'Food & Dining'),
    (r'\b(food|eats|dining|menufy)\b', 2, 'Food & Dining'),
    (r'\b(chaat|munchen|tacos?|taqueria|gastropub|lanai|akamai|the.?buoy|'
     r'sugar.?momma|sweets|dessert|ice.?cream|creamery|bakery|deli|bistro|eatery)\b', 3, 'Food & Dining'),
    (r'\b(salt.?&?.?straw|molly.?moon|kream|cold.?stone|baskin|'
     r'ben.?&?.?jerry|haagen|creamery|gelato|frozen.?yogurt|froyo)\b', 4, 'Food & Dining'),

    # ── Groceries ──
    (r'\b(safeway|kroger|whole.?foods|trader.?joe|aldi|publix|sprouts|'
     r'heb|wegmans|food.?lion|stop.?shop|vons|ralphs|giant|'
     r'harris.?teeter|winn.?dixie|meijer|hy.?vee|winco|smart.?final|'
     r'fresh.?market|natural.?grocers|grocery.?outlet|market.?basket|'
     r'stater.?bros|price.?chopper|brookshire|piggly|winn)\b', 4, 'Groceries'),
    (r'\b(grocery|groceries|supermarket|fresh.?market)\b', 4, 'Groceries'),
    (r'\b(instacart|shipt|amazon.?fresh|walmart.?grocery|sprouts.?delivery|safeway.?delivery|kroger.?delivery|whole.?foods.?delivery|costco.?delivery)\b', 3, 'Groceries'),
    (r'\bcostco\b', 4, 'Groceries'),
    (r'\b(mayuri.?foods|mayuri.?video|indian.?grocery|mayuri.?market|'
     r'ethnic.?grocery|international.?market|global.?food|'
     r'asian.?market|halal.?grocery|indian.?store)\b', 3, 'Groceries'),
    (r'\b(central.?market|ctrl.?mkt|ctrl.?market|town.?country.?market|'
     r'metropolitan.?market|uwajimaya|h.?mart|99.?ranch|mitsuwa)\b', 4, 'Groceries'),

    # ── Transport ──
    (r'\b(lyft|curb|taxi|cab|rideshare|ride.?share)\b', 4, 'Transport'),
    (r'\b(chevron|shell|bp|exxon|mobil|arco|texaco|valero|sunoco|'
     r'marathon|citgo|caseys|speedway|wawa|quiktrip|racetrac|'
     r'circle.?k|pilot|flying.?j|loves|76.?gas)\b', 4, 'Transport'),
    (r'\b(chargepoint|tesla.?supercharger|evgo|blink|electrify.?america)\b', 4, 'Transport'),
    (r'\b(spothero|parkmobile|laz.?parking|paybyphone|parkwhiz)\b', 4, 'Transport'),
    (r'\b(ezpass|fastrak|sunpass|txtag|tolltag|ipass|peach.?pass)\b', 4, 'Transport'),
    (r'\b(hertz|avis|budget.?car|enterprise|national.?car|alamo|'
     r'dollar.?rent|thrifty|sixt|turo|zipcar)\b', 4, 'Transport'),
    (r'\b(bart|wmata|cta|mbta|septa|caltrain|lirr|nj.?transit|amtrak|'
     r'greyhound|megabus|good2go)\b', 4, 'Transport'),
    (r'\b(jiffy.?lube|midas|pep.?boys|autozone|oreilly|napa|mavis|'
     r'firestone|discount.?tire|goodyear)\b', 3, 'Transport'),
    (r'\b(gull.?energy|conoco|phillips.?66|sinclair|valero|mini.?mart|'
     r'car.?wash|brown.?bear|quick.?stop|gas.?n.?go)\b', 3, 'Transport'),
    (r'\b(fuel|gas.?station|petrol|parking|toll)\b', 2, 'Transport'),

    # ── Bills & Utilities ──
    (r'\b(at.?t|verizon|comcast|xfinity|t.?mobile|sprint|'
     r'pg.?e|con.?ed|city.?light|duke.?energy|dominion|centerpoint|'
     r'spectrum|cox|fios|optimum|mediacom|frontier.?comm|windstream|'
     r'centurylink|lumen|consolidated.?comm|sparklight|astound)\b', 4, 'Bills & Utilities'),
    (r'\b(electric|electricity|utility|utilities|water.?bill|sewer|'
     r'gas.?bill|natural.?gas|internet|cable|broadband|wifi)\b', 4, 'Bills & Utilities'),
    (r'\b(phone.?bill|mobile.?bill|wireless.?bill|cell.?phone.?bill)\b', 3, 'Bills & Utilities'),
    (r'\b(seattle.?city.?light|puget.?sound.?energy|pse|scl.?util|'
     r'seattle.?util|king.?county.?util|water.?sewer|city.?util)\b', 4, 'Bills & Utilities'),

    # ── Subscriptions ──
    (r'\b(netflix|hulu|disney.?plus|hbo.?max|paramount.?plus|peacock|'
     r'apple.?tv|discovery.?plus|fubo|sling|youtube.?tv|tubi|espn.?plus)\b', 5, 'Subscriptions'),
    (r'\b(spotify|apple.?music|youtube.?music|tidal|amazon.?music|'
     r'pandora|siriusxm|deezer|audible)\b', 5, 'Subscriptions'),
    (r'\b(microsoft.?365|google.?one|dropbox|icloud|notion|evernote|'
     r'adobe|canva|figma|creative.?cloud)\b', 4, 'Subscriptions'),
    (r'\b(chatgpt|openai|claude|midjourney|jasper|grammarly)\b', 4, 'Subscriptions'),
    (r'\b(xbox.?game.?pass|playstation.?plus|nintendo.?online|ea.?play)\b', 4, 'Subscriptions'),
    (r'\b(peloton|strava|myfitnesspal|noom|calm|headspace|beachbody)\b', 4, 'Subscriptions'),
    (r'\b(nytimes|wsj|washington.?post|substack|medium|patreon)\b', 3, 'Subscriptions'),
    (r'\b(zoom|loom|slack|github|linear|vercel|heroku|digitalocean|'
     r'atlassian|jira|hubspot|salesforce)\b', 3, 'Subscriptions'),
    (r'\b(clearme|clear.?plus|tsa.?pre.?check.?member)\b', 4, 'Subscriptions'),
    (r'apple\.com/bill|itunes|google\*.*one|youtube\s*premium', 5, 'Subscriptions'),
    # ── Membership-style subscriptions (look like retail, are recurring) ──
    # Higher priority than retail rules so Walmart+, Costco membership, etc don't
    # fall into Shopping/Groceries based on the parent merchant name.
    (r'\bwalmart\+?\s*member\b|\bwmt\s*plus\b|\bwmt\+\b', 6, 'Subscriptions'),
    (r'\bcostco\s*(?:membership|annual\s*fee|renewal|connect)\b', 6, 'Subscriptions'),
    (r"\bsam'?s?\s*club\s*(?:membership|annual\s*fee|renewal)\b", 6, 'Subscriptions'),
    (r"\bbj'?s?\s*(?:wholesale|membership|annual\s*fee)\b", 6, 'Subscriptions'),
    (r'\b(?:amazon|amzn)\s*prime\b|\bprime\s*membership\b', 6, 'Subscriptions'),
    (r'\bapple\s*one\b|\bicloud\+?\b', 6, 'Subscriptions'),
    (r'\btarget\s*circle\s*360\b|\bshipt\s*membership\b', 6, 'Subscriptions'),
    # Catch the standalone word 'member' as a subscription signal — low priority,
    # so specific retail rules above can still win when relevant.
    (r'\b(subscription|membership|auto.?renew|monthly.?plan|annual.?plan)\b', 2, 'Subscriptions'),
    (r'\b(kindle|kindle.?unlimited|audible)\b', 4, 'Subscriptions'),

    # ── Health ──
    (r'\b(cvs|walgreen|walgreens|rite.?aid|duane.?reade|'
     r'walmart.?pharmacy|costco.?pharmacy)\b', 4, 'Health'),
    (r'\b(labcorp|quest.?diagnostics|bioreference)\b', 4, 'Health'),
    (r'\b(aspen.?dental|smile.?direct|western.?dental|'
     r'lenscrafters|warby.?parker|visionworks)\b', 4, 'Health'),
    (r'\b(betterhelp|talkspace)\b', 4, 'Health'),
    (r'\b(planet.?fitness|equinox|golds.?gym|la.?fitness|'
     r'anytime.?fitness|crunch|orangetheory|soulcycle|crossfit|'
     r'la.?fitns|fitness)\b', 4, 'Health'),
    (r'\b(kaiser|aetna|cigna|unitedhealth|bcbs|blue.?cross|'
     r'blue.?shield|humana|molina)\b', 4, 'Health'),
    (r'\b(doctor|medical|dental|hospital|clinic|urgent.?care|'
     r'pharmacy|drug.?store|optometry|vision)\b', 3, 'Health'),
    (r'\b(copay|deductible|prescription|therapy|telehealth|therapist)\b', 3, 'Health'),

    # ── Shopping ──
    (r'\b(ebay|etsy|shopify|shein|temu|wish|aliexpress|wayfair|zappos)\b', 4, 'Shopping'),
    (r'\b(nordstrom|macys|bloomingdales|saks|neiman.?marcus|'
     r'jcpenney|kohls|dillards)\b', 4, 'Shopping'),
    (r'\b(tjmaxx|tj.?maxx|marshalls|ross|burlington|five.?below|'
     r'dollar.?tree|dollar.?general|family.?dollar)\b', 4, 'Shopping'),
    (r'\b(best.?buy|apple.?store|micro.?center|adorama|newegg|gamestop)\b', 4, 'Shopping'),
    (r'\b(gap|zara|h.?m|uniqlo|forever.?21|old.?navy|banana.?republic|'
     r'jcrew|madewell|anthropologie|asos|abercrombie|ae\b|express)\b', 4, 'Shopping'),
    (r'\b(loft\b|ann.?taylor|boutique|clothing.?co|apparel|outfitters)\b', 3, 'Shopping'),
    (r'\b(ralph.?lauren|polo.?ralph|tommy.?hilfiger|calvin.?klein|lacoste|'
     r'brooks.?brothers|nautica|vineyard.?vines|lululemon|patagonia.?store)\b', 4, 'Shopping'),
    (r'\b(nike|adidas|lululemon|athleta|under.?armour|reebok|new.?balance|dyson|'
     r'glow.?cosmetics|pop.?mart)\b', 4, 'Shopping'),
    (r'\b(crate.?barrel|williams.?sonoma|pottery.?barn|west.?elm|'
     r'ikea|homegoods|bed.?bath)\b', 4, 'Shopping'),
    (r'\b(sephora|ulta|bath.?body|the.?body.?shop)\b', 4, 'Shopping'),
    (r'\b(sams.?club|bjs.?wholesale|staples|office.?depot|officemax|road.?runner|running.?warehouse|fleet.?feet)\b', 3, 'Shopping'),
    (r'\b(sporting.?goods|big.?5|rei\b|dicks.?sporting|academy.?sports|'
     r'sports.?authority|cabelas|bass.?pro|dunhams|hibbett)\b', 4, 'Shopping'),
    (r'\bamzn\b|amazon.?mktp|amazon.?mktpl', 3, 'Shopping'),
    (r'\b(pret|marks.?spencer|boots.?pharmacy|tesco|sainsbury|waitrose|'
     r'carrefour|lulu.?hypermarket|noon|namshi|centrepoint)\b', 3, 'Shopping'),

    # ── Entertainment ──
    (r'\b(ticketmaster|stubhub|fandango|eventbrite|livenation)\b', 4, 'Entertainment'),
    (r'\b(amusement|bowling|golf|arcade|escape.?room|laser.?tag|'
     r'trampoline|top.?golf|mini.?golf)\b', 4, 'Entertainment'),
    (r'\b(steam|playstation|xbox|nintendo|twitch|gaming|epic.?games)\b', 4, 'Entertainment'),
    (r'\b(cinemark|amc|regal|cinepolis|alamo.?drafthouse|landmark.?theat|'
     r'showcase.?cinema|marcus.?theat|harkins|bow.?tie.?cinema)\b', 4, 'Entertainment'),
    (r'\b(movie|cinema|cinemas|theater|theatre|concert|imax|multiplex)\b', 3, 'Entertainment'),

    # ── Travel ──
    (r'\b(delta|united|american.?airlines|southwest|spirit.?airlines|indigo|indigoairlines|raz.?indigo|raz.?chirukaanuka|air.?india|vistara|spicejet|goair|akasa)\b', 4, 'Travel'),
    (r'\b(delta|united|american.?airlines|southwest|spirit.?airlines|'
     r'frontier|alaska.?airlines|jetblue|hawaiian|sun.?country|'
     r'indigo|raz\*indigo|etravelius)\b', 4, 'Travel'),
    (r'\b(marriott|hilton|hyatt|ihg|wyndham|best.?western|radisson|'
     r'four.?seasons|ritz.?carlton|sheraton|westin|courtyard|'
     r'hampton.?inn|holiday.?inn|comfort.?inn|embassy.?suites|'
     r'hoxton)\b', 4, 'Travel'),
    (r'\b(expedia|booking.?com|hotels.?com|kayak|priceline|hopper|'
     r'trivago|airbnb|vrbo|tripadvisor)\b', 4, 'Travel'),
    (r'\b(carnival|royal.?caribbean|norwegian.?cruise|'
     r'celebrity|princess.?cruise|disney.?cruise)\b', 4, 'Travel'),
    (r'\b(hotel|resort|motel|suite|hostel|flight|airline|airfare|airport|duty.?free|gmr.?airport|terminal.?shop|hyd.?duty|intl.?airport)\b', 3, 'Travel'),
    (r'\bgmr\b', 3, 'Travel'),

    # ── Personal Care ──
    (r'\b(hair.?bar|hair.?studio|hair.?lounge|blow.?dry|blowout.?bar|'
     r'bond.?hair|great.?clips|sport.?clips|supercuts|fantastic.?sams)\b', 5, 'Personal Care'),
    (r'\b(eyebrow|eye.?brow|threading|brow.?bar|brow.?studio|lash|'
     r'microblading|henna.?brow)\b', 5, 'Personal Care'),
    (r'\b(salon|spa|barber|haircut|nail.?salon|nail.?bar|beauty|'
     r'skincare|cosmetic|massage|waxing|esthetician|beauty.?supply)\b', 4, 'Personal Care'),

    # ── Insurance ──
    (r'\b(geico|progressive|state.?farm|allstate|farmers.?ins|usaa|'
     r'liberty.?mutual|nationwide|travelers|esurance|root|lemonade|'
     r'hippo|amica|chubb)\b', 5, 'Insurance'),
    (r'\b(metlife|prudential|northwestern.?mutual|new.?york.?life|'
     r'guardian|principal)\b', 4, 'Insurance'),
    (r'\b(insurance|premium|policy|coverage)\b', 2, 'Insurance'),

    # ── Pets ──
    (r'\b(petsmart|petco|pet.?supplies.?plus|tractor.?supply|chewy|'
     r'rover|wag|pet.?evolution|pet.?supermarket|pet.?valu|spot.?pet|paw.?print|grooming|'
     r'pet.?food.?express)\b', 5, 'Pets'),
    (r'\b(veterinary|veterinarian|animal.?hospital|vet.?clinic|'
     r'pet.?grooming|dog.?walk|pet.?board|pet.?sit|spot.?pet)\b', 4, 'Pets'),
    (r'\b(pet.?food|dog.?food|cat.?food|pet.?supply)\b', 3, 'Pets'),

    # ── Home Improvement ──
    (r'\b(home.?depot|lowes|menards|ace.?hardware|true.?value)\b', 5, 'Home Improvement'),
    (r'\b(floor.?decor|carpet.?one|empire.?flooring)\b', 4, 'Home Improvement'),
    (r'\b(contractor|renovation|remodel|plumber|electrician|'
     r'handyman|roofing|hvac|landscaping)\b', 4, 'Home Improvement'),
    (r'\b(hardware|lumber|tile|grout|drywall|fixture|faucet)\b', 3, 'Home Improvement'),

    # ── Baby & Kids ──
    (r'\b(carters|oshkosh|gap.?kids|gymboree|childrens.?place|'
     r'buy.?buy.?baby|babylist)\b', 4, 'Baby & Kids'),
    (r'\b(toys.?r.?us|learning.?express|melissa.?doug|lego)\b', 4, 'Baby & Kids'),
    (r'\b(daycare|preschool|babysitter|nanny|afterschool|childcare|'
     r'montessori|kindercare|bright.?horizons)\b', 5, 'Baby & Kids'),
    (r'\b(diapers|formula|stroller|crib|nursery|pampers|huggies)\b', 4, 'Baby & Kids'),


    # ── Education ──
    (r'\b(tuition|university|college|school|course|udemy|coursera|'
     r'edx|certification|exam.?fee|textbook|education)\b', 4, 'Education'),
    (r'\b(kumon|sylvan|tutoring|lessons|learning.?center)\b', 4, 'Education'),
    (r'\b(etv.?web|fireworks.?university)\b', 3, 'Education'),

    # ── Rent / Housing ──
    (r'\b(rent|lease|apt|apartment|property.?management|realty|'
     r'hoa|condo.?assoc|homeowner.?assoc|housing|landlord)\b', 5, 'Rent/Mortgage'),
    (r'\b(mortgage|mtg|lakeview|quicken.?loan|rocket.?mortgage|nationstar|'
     r'mr.?cooper|freedom.?mortgage|pennymac|loandepot|'
     r'caliber.?home|united.?wholesale|guild.?mortgage)\b', 5, 'Rent/Mortgage'),
    (r'\bfs.?pay.?hoa\b|\bhoa.?payment\b|\bhomeowner.?dues\b', 5, 'Rent/Mortgage'),

    # ── Government / Taxes ──
    (r'\b(irs|tax.?payment|property.?tax|state.?tax|franchise.?tax|'
     r'dmv|vehicle.?registration|gov.?payment|usps)\b', 5, 'Government & Taxes'),

    # ── Bank Fees ──
    (r'\b(overdraft|nsf.?fee|maintenance.?fee|service.?charge|'
     r'account.?fee|annual.?fee|late.?fee|foreign.?transaction|'
     r'cash.?advance.?fee|atm.?fee|out.?of.?network|surcharge|penalty)\b', 5, 'Bank Fees'),

    # ── Gifts / Donations ──
    (r'\b(gofundme|kickstarter|indiegogo|red.?cross|salvation.?army|'
     r'united.?way|habitat.?humanity)\b', 4, 'Gifts & Donations'),
    (r'\b(church|mosque|temple|synagogue|tithe|offering|donation|'
     r'nonprofit|fundraiser|charitable)\b', 3, 'Gifts & Donations'),

    # ── Professional Services ──
    (r'\b(law.?office|legal|attorney|accounting|cpa|consultant|'
     r'cleaning.?service|laundry|dry.?cleaning|alterations|notary)\b', 4, 'Professional Services'),

    # ── SaaS & Tools ──
    (r'\b(openai|figma|notion|slack|github|linear|vercel|heroku|aws|'
     r'digitalocean|atlassian|jira|hubspot|salesforce|intercom|'
     r'stripe|twilio|sendgrid|cloudflare)\b', 3, 'Subscriptions'),
    (r'\b(monarch.?money|ynab|mint|copilot.?money|rocket.?money|truebill|'
     r'personal.?capital|empower.?personal)\b', 4, 'Subscriptions'),
]

# Precompile all category patterns
COMPILED_CATEGORY_PATTERNS = [
    (re.compile(p, re.IGNORECASE), score, cat)
    for p, score, cat in RAW_CATEGORY_PATTERNS
]

# Categories that suggest recurring behavior (hint only — not final)
RECURRING_HINT_CATEGORIES = {
    'Subscriptions', 'Bills & Utilities', 'Insurance',
    'Bills & Utilities', 'Baby & Kids', 'Subscriptions'
}

# ── 5. HELPER FUNCTIONS ───────────────────────────────────────────────────────

def normalize_description(desc: str) -> str:
    """Step 1: Clean raw bank description string."""
    if not desc:
        return ''
    d = desc.lower().strip()
    # Strip payment-processor prefix FIRST (SQ *, TST*, DD *, PAYPAL *, …) so the
    # generic "*word" auth-code stripper below doesn't eat the merchant's first word.
    d = PROCESSOR_PREFIX_RE.sub('', d)
    # Split mashed merchant+number so word boundaries work across formats
    # (e.g. QFX memo 'firestone28258' -> 'firestone 28258'). Only splits a letter
    # run directly followed by a digit run; leaves normal alphanumerics alone.
    d = re.sub(r'([a-z])(\d)', r'\1 \2', d)
    d = re.sub(r'(\d)([a-z])', r'\1 \2', d)
    # Apply pre-normalization aliases BEFORE stripping symbols
    for alias, replacement in PRE_NORM_ALIASES.items():
        if alias in d:
            d = d.replace(alias, replacement)
            break
    # Strip POS wrappers and ACH noise
    for pattern in COMPILED_STRIP:
        d = pattern.sub(' ', d)
    # Collapse whitespace
    d = re.sub(r'\s+', ' ', d).strip()
    return d


def extract_merchant_alias(normalized: str) -> str:
    """Step 2: Convert wrapper patterns to clean merchant names."""
    d = normalized

    # Handle SQ * and TST* — strip prefix, keep merchant name
    sq_match = re.match(r'^(sq\s*\*|tst\*?\s+|toast\s+)(.+)', d)
    if sq_match:
        d = sq_match.group(2).strip()

    # Handle PAYPAL * — strip prefix
    pp_match = re.match(r'^paypal\s*\*\s*(.+)', d)
    if pp_match:
        d = pp_match.group(1).strip()

    # Apply alias table
    for alias, replacement in MERCHANT_ALIASES.items():
        if d.startswith(alias) or alias in d:
            if replacement:
                d = d.replace(alias, replacement)
            else:
                d = d.replace(alias, '').strip()

    return d.strip()


def is_summary_row(normalized: str, amount: float) -> bool:
    """Step 4: Filter invalid/summary rows."""
    if amount == 0:
        return True
    for kw in SUMMARY_KEYWORDS:
        if kw in normalized:
            return True
    if PAYMENT_SUMMARY_RE.search(normalized):
        return True
    return False


def classify_transaction_type(
    normalized: str, merchant: str, amount: float, bank: str = None
) -> Tuple[str, Optional[str]]:
    """
    Step 5: Classify transaction type.
    Returns (type, review_reason_or_None)
    Uses full normalized description + merchant + bank context.
    """
    # Statement credits (Amex card benefits)
    if STATEMENT_CREDIT_RE.search(normalized):
        return 'card_credit', None

    # Financing fees — exclude
    if FINANCING_FEE_RE.search(normalized):
        return 'excluded', 'financing_fee'

    # Payment summaries — exclude
    if PAYMENT_SUMMARY_RE.search(normalized):
        return 'excluded', 'payment_summary'

    # Reimbursements — exclude from spend
    if REIMBURSEMENT_RE.search(normalized):
        return 'reimbursement', None

    # Cash/ATM — exclude from spend
    if CASH_RE.search(normalized):
        return 'cash', None

    # CC Payments
    if CC_PAYMENT_RE.search(normalized):
        return 'credit_card_payment', None

    # P2P transfers (Zelle/Venmo/etc.) — check BEFORE loan so a memo like
    # 'zelle ... mortgage' types as transfer (it's person-to-person), not loan.
    if re.search(r'\b(zelle|venmo|cash.?app|apple.?cash)\b', normalized):
        return 'transfer', None

    # Loan/mortgage payments
    if LOAN_RE.search(normalized):
        return 'loan_payment', None

    # Income/Payroll — check BEFORE generic ACH transfer
    if INCOME_RE.search(normalized) and amount > 0:
        return 'income', None

    # Refunds
    if REFUND_RE.search(normalized):
        return 'refund', None

    # Transfers (P2P) — after income check
    if TRANSFER_RE.search(normalized):
        # Venmo/PayPal with merchant context → might be expense
        if re.search(r'\b(venmo|paypal)\b', normalized):
            # If amount is large and recurring, flag for review
            return 'transfer', 'wallet_ambiguous'
        return 'transfer', None

    # Positive amount with no strong income signal → possible expense (Amex/Citi style)
    # or unrecognized income
    if amount > 0:
        # Parser already flipped positive-expense-bank signs (charges are now
        # negative). So a positive amount on a card bank = money back = refund,
        # NOT expense. (This branch returned 'expense' before the sign fix.)
        bank_lower = (bank or '').lower()
        positive_expense_banks = {'amex', 'american express', 'citi', 'discover',
                                  'apple card', 'synchrony', 'barclays'}
        if any(b in bank_lower for b in positive_expense_banks):
            return 'refund', None
        return 'income', 'positive_amount_unclear'

    return 'expense', None


def score_categories(normalized: str, merchant: str) -> Dict[str, float]:
    """
    Step 6: Weighted scoring across all categories.
    Returns dict of {category: score}.
    """
    scores: Dict[str, float] = {}

    for pattern, score, category in COMPILED_CATEGORY_PATTERNS:
        if pattern.search(normalized) or pattern.search(merchant):
            scores[category] = scores.get(category, 0) + score

    return scores


def resolve_ambiguity(normalized: str, merchant: str, scores: Dict[str, float]) -> Dict[str, float]:
    """
    Step 6b: Apply ambiguity rules for known multi-category merchants.
    Adjusts scores based on context tokens.
    """
    # ── Indian streaming → Subscriptions ──
    if any(k in normalized for k in ['etv', 'zee5', 'hotstar', 'sonyliv', 'jiocinema', 'voot']):
        scores['Subscriptions'] = scores.get('Subscriptions', 0) + 6
        return scores

    # ── Grocery market → Groceries ──
    if any(k in normalized for k in ['control mkt', 'control market', 'shoreline mkt', 'farmers mkt', 'farmers market', 'public market']):
        scores['Groceries'] = scores.get('Groceries', 0) + 6
        return scores

    # ── Marathon/Race → Health ──
    if any(k in normalized for k in ['marathon', '5k', '10k', 'triathlon', 'race.entry', 'run.sign']):
        scores['Health'] = scores.get('Health', 0) + 5
        scores.pop('Transport', None)
        return scores

    # ── Mayuri Foods → Groceries ──
    if 'mayuri' in normalized and any(k in normalized for k in ['food', 'video', 'market']):
        scores = {'Groceries': 6}
        return scores

    # ── Clothing brands → Shopping ──
    if any(k in normalized for k in ['j crew', 'jcrew', 'br factory', 'banana republic', 'gap factory', 'j. crew']):
        scores['Shopping'] = scores.get('Shopping', 0) + 6
        return scores

    # ── Indian retail stores → Shopping ──
    if any(k in normalized for k in ['ikea india', 'premium lifestyle', 'lifestyle intl', 'lifestyle international', 'central square']):
        scores['Shopping'] = scores.get('Shopping', 0) + 6
        return scores

    # ── Airport stores → Travel ──
    if any(k in normalized for k in ['hudson st', 'hudson news', 'hudson bookseller', 'seatac', 'sea-tac']):
        scores['Travel'] = scores.get('Travel', 0) + 6
        return scores

    # ── Costco Gas → Transport ──
    if 'costco' in normalized and any(k in normalized for k in ['gas', 'station', 'fuel']):
        scores = {'Transport': 6}
        return scores

    # ── Paddle → Subscriptions ──
    if 'paddle' in normalized or 'paddle' in merchant:
        scores = {'Subscriptions': 6}
        return scores

    # ── Uber ──
    if 'uber' in merchant or 'uber' in normalized:
        if 'eats' in normalized or 'eats' in merchant:
            scores['Food & Dining'] = scores.get('Food & Dining', 0) + 3
            scores['Transport'] = max(0, scores.get('Transport', 0) - 3)
        elif 'one' in normalized:
            scores['Subscriptions'] = scores.get('Subscriptions', 0) + 5
            scores['Transport'] = max(0, scores.get('Transport', 0) - 3)
        else:
            scores['Transport'] = scores.get('Transport', 0) + 2

    # ── Amazon ──
    if 'amazon' in merchant or 'amazon' in normalized:
        if any(k in normalized for k in ['prime', 'music', 'video', 'audible', 'kindle']):
            scores['Subscriptions'] = scores.get('Subscriptions', 0) + 4
            scores['Shopping'] = max(0, scores.get('Shopping', 0) - 2)
        elif 'fresh' in normalized:
            scores['Groceries'] = scores.get('Groceries', 0) + 4
            scores['Shopping'] = max(0, scores.get('Shopping', 0) - 2)
        else:
            scores['Shopping'] = scores.get('Shopping', 0) + 2

    # ── Apple ──
    if 'apple' in merchant or 'apple' in normalized:
        if any(k in normalized for k in ['apple subscription', 'apple.com/bill', 'itunes', 'apple one', 'apple music', 'apple tv']):
            scores['Subscriptions'] = scores.get('Subscriptions', 0) + 5
            scores['Shopping'] = max(0, scores.get('Shopping', 0) - 3)
        elif 'apple store' in normalized:
            scores['Shopping'] = scores.get('Shopping', 0) + 4
            scores['Subscriptions'] = max(0, scores.get('Subscriptions', 0) - 2)
        elif 'apple card' in normalized:
            pass  # CC payment — handled earlier

    # ── Google ──
    if 'google' in normalized:
        if any(k in normalized for k in ['youtube premium', 'youtube tv', 'google one', 'google play']):
            scores['Subscriptions'] = scores.get('Subscriptions', 0) + 4
        elif 'google ads' in normalized or 'google cloud' in normalized:
            scores['Subscriptions'] = scores.get('Subscriptions', 0) + 4
            scores['Subscriptions'] = max(0, scores.get('Subscriptions', 0) - 2)

    # ── Walmart / Target ──
    for merchant_name in ['walmart', 'target']:
        if merchant_name in normalized or merchant_name in merchant:
            if any(k in normalized for k in ['grocery', 'food', 'market', 'fresh', 'supercenter']):
                scores['Groceries'] = scores.get('Groceries', 0) + 3
                scores['Shopping'] = max(0, scores.get('Shopping', 0) - 2)
            elif any(k in normalized for k in ['pharmacy', 'optical', 'vision']):
                scores['Health'] = scores.get('Health', 0) + 3
                scores['Shopping'] = max(0, scores.get('Shopping', 0) - 2)
            else:
                scores['Shopping'] = scores.get('Shopping', 0) + 2

    # ── Costco ──
    if 'costco' in normalized:
        if any(k in normalized for k in ['pharmacy', 'optical', 'vision']):
            scores['Health'] = scores.get('Health', 0) + 3
        elif any(k in normalized for k in ['instacart', 'grocery', 'food']):
            scores['Groceries'] = scores.get('Groceries', 0) + 2
        # else keep as Shopping or Groceries based on pattern match

    # ── PayPal / Venmo ──
    if re.search(r'\b(paypal|venmo)\b', normalized):
        # Penalize — ambiguous wallet
        for cat in list(scores.keys()):
            scores[cat] = scores[cat] - 1

    # ── Square / Toast ──
    # TST* and SQ* are almost always food/restaurant POS systems
    if re.search(r'tst|sq\s*\*|spring district', normalized):
        scores['Food & Dining'] = scores.get('Food & Dining', 0) + 3

    # ── Insurance ──
    if 'insurance' in normalized or scores.get('Insurance', 0) > 0:
        # Positive amount = possible refund/claim — penalize Insurance
        pass  # handled in type classification

    return scores


def evaluate_confidence(scores: Dict[str, float]) -> Tuple[str, str, bool, Optional[str]]:
    """
    Step 7: Evaluate scores and determine category, confidence, needs_review.
    Returns (category, confidence, needs_review, review_reason)
    """
    if not scores:
        return 'Other', 'low', True, 'merchant_unknown'

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_score = sorted_cats[0]

    # Determine confidence
    if top_score >= 5:
        confidence = 'high'
    elif top_score >= 3:
        confidence = 'medium'
    else:
        confidence = 'low'

    # Review conditions
    needs_review = False
    review_reason = None

    if top_score < 4:
        needs_review = True
        review_reason = 'low_confidence'

    if len(sorted_cats) > 1:
        second_cat, second_score = sorted_cats[1]
        if second_score >= 3 and abs(top_score - second_score) < 2:
            needs_review = True
            review_reason = 'multi_category_match'

    if top_cat == 'Other':
        needs_review = True
        review_reason = 'merchant_unknown'

    return top_cat, confidence, needs_review, review_reason


def emit_recurring_hint(category: str, merchant: str) -> bool:
    """Step 8: Soft hint for recurring detection layer."""
    return category in RECURRING_HINT_CATEGORIES



# Inconsistent bank / LLM transaction prefixes — stripped for FINGERPRINTING so
# the same real transaction fingerprints identically regardless of how the parser
# (template or LLM) happened to phrase the description this time.
_FP_PREFIXES = [
    "recurring debit card purchase", "recurring debit card", "debit card purchase",
    "pos purchase", "web pmt recur-", "web pmt-", "web pmt",
    "direct payment - purchase", "direct payment -", "direct payment",
    "intl purch & adv fee", "intl purch", "ach tel", "ach web", "ach",
    "checkcard", "check card", "point of sale", "pos", "purchase authorized on",
    "purchase", "payment", "recurring", "debit card", "card",
]


# Broad national-brand alias map. Key = canonical name; values = substrings that
# identify it after normalization. "contains" match. Grow from real data as new
# duplicate-causing merchants show up.
_MERCHANT_ALIASES = {
    "amazon": ["amazon", "amzn", "amazon mktpl", "amazon mktp", "amazon.com", "amazon prime", "amzn mktp", "amazon web"],
    "walmart": ["walmart", "wal-mart", "wal mart", "wm supercenter", "walmart.com"],
    "target": ["target", "targ ", "targ.", "target.com", "target debit"],  # 'targ' handled specially below
    "costco": ["costco"],
    "kroger": ["kroger"],
    "safeway": ["safeway"],
    "trader joes": ["trader joe", "trader joes"],
    "whole foods": ["whole foods", "wholefds", "wholefoods"],
    "aldi": ["aldi"],
    "publix": ["publix"],
    "vons": ["vons"],
    "albertsons": ["albertsons"],
    "sprouts": ["sprouts"],
    "starbucks": ["starbucks", "sbux"],
    "dunkin": ["dunkin"],
    "mcdonalds": ["mcdonald", "mcdonalds"],
    "chipotle": ["chipotle"],
    "chick-fil-a": ["chick-fil-a", "chick fil a", "chickfila"],
    "taco bell": ["taco bell"],
    "subway": ["subway"],
    "wendys": ["wendy"],
    "burger king": ["burger king"],
    "dominos": ["domino"],
    "pizza hut": ["pizza hut"],
    "panera": ["panera"],
    "dairy queen": ["dairy queen"],
    "in-n-out": ["in-n-out", "in n out"],
    "popeyes": ["popeye"],
    "doordash": ["doordash", "dd doordash", "dd *doordash"],
    "uber eats": ["uber eats", "ubereats"],
    "grubhub": ["grubhub"],
    "instacart": ["instacart"],
    "uber": ["uber"],
    "lyft": ["lyft"],
    "netflix": ["netflix"],
    "spotify": ["spotify"],
    "hulu": ["hulu"],
    "disney plus": ["disney plus", "disney+", "disneyplus"],
    "hbo max": ["hbo max", "hbomax", "max.com"],
    "youtube": ["youtube", "google youtube"],
    "apple": ["apple.com", "apple com", "apple store", "apple one", "itunes", "apple cash", "applecard"],
    "google": ["google", "goog "],
    "microsoft": ["microsoft", "msft"],
    "paypal": ["paypal", "pp *", "pp*"],
    "venmo": ["venmo"],
    "zelle": ["zelle"],
    "cash app": ["cash app", "cashapp", "sq cash"],
    "klarna": ["klarna"],
    "afterpay": ["afterpay"],
    "affirm": ["affirm"],
    "cvs": ["cvs"],
    "walgreens": ["walgreens", "walgreen"],
    "rite aid": ["rite aid"],
    "home depot": ["home depot", "homedepot"],
    "lowes": ["lowe's", "lowes"],
    "best buy": ["best buy", "bestbuy"],
    "ikea": ["ikea"],
    "wayfair": ["wayfair"],
    "chevron": ["chevron"],
    "shell": ["shell oil", "shell service", "shell "],
    "exxon": ["exxon", "exxonmobil"],
    "76": ["76 "],
    "arco": ["arco"],
    "bp": ["bp#", "bp gas"],
    "mobil": ["mobil"],
    "7-eleven": ["7-eleven", "7 eleven", "7eleven"],
    "circle k": ["circle k"],
    "petsmart": ["petsmart"],
    "petco": ["petco"],
    "chewy": ["chewy"],
    "nike": ["nike"],
    "adidas": ["adidas"],
    "lululemon": ["lululemon"],
    "old navy": ["old navy"],
    "gap": ["gap.com", "gap store"],
    "h&m": ["h&m", "h and m"],
    "zara": ["zara"],
    "macys": ["macy's", "macys"],
    "nordstrom": ["nordstrom"],
    "tj maxx": ["tj maxx", "tjmaxx", "t.j. maxx"],
    "marshalls": ["marshalls"],
    "ross": ["ross stores", "ross dress"],
    "sephora": ["sephora"],
    "ulta": ["ulta"],
    "att": ["at&t", "att "],
    "verizon": ["verizon"],
    "tmobile": ["t-mobile", "tmobile"],
    "comcast": ["comcast", "xfinity"],
    "spectrum": ["spectrum"],
    "pge": ["pg&e", "pgande", "pacific gas"],
    "geico": ["geico"],
    "progressive": ["progressive"],
    "state farm": ["state farm"],
    "allstate": ["allstate"],
}

def _fingerprint_merchant(description: str) -> str:
    """Aggressively reduce a description to its core merchant tokens, so parse
    variation doesn't change the fingerprint."""
    import re as _re
    if not description:
        return ""
    d = description.lower().strip()
    # strip processor prefixes like "sq *", "tst*", "dd *"
    d = _re.sub(r'^(?:sq|tst|toast|dd|dsh|paypal|pp|sp|wpy|gum|fs|ven(?:mo)?)\s*\*+\s*', '', d)
    # strip the bank/LLM transaction-type prefixes (longest first; loop until stable)
    changed = True
    while changed:
        changed = False
        ds = d.lstrip(" -*#")
        for pfx in _FP_PREFIXES:
            if ds.startswith(pfx):
                d = ds[len(pfx):]
                changed = True
                break
    # drop long digit runs (phone numbers, store ids), stars, years
    d = _re.sub(r'\d{4,}', '', d)
    d = _re.sub(r'\b20\d{2}\b', '', d)
    d = _re.sub(r'[*#]', ' ', d)
    d = _re.sub(r'[^a-z0-9 ]', ' ', d)
    d = _re.sub(r'\s+', ' ', d).strip()
    # Step 2: alias map — "contains" match against national brands.
    # Special short-token cases where truncation loses the trailing chars:
    _stub = {"targ": "target", "amzn": "amazon", "sbux": "starbucks", "wmt": "walmart"}
    if d.strip() in _stub:
        return _stub[d.strip()]
    for canonical, needles in _MERCHANT_ALIASES.items():
        for n in needles:
            if n in d:
                return canonical
    # Step 3: stem fallback for the long tail — first 2 significant tokens.
    toks = [t for t in d.split() if len(t) > 1]
    return " ".join(toks[:2])[:32].strip()


def generate_fingerprint(bank: str, date: str, amount: float, description: str, ext_id: str = "", account: str = "") -> str:
    # If the source gave a stable external id (OFX FITID), trust it outright.
    if ext_id:
        raw = f"{bank}|{account}|{ext_id}"
        return hashlib.sha256(raw.encode()).hexdigest()
    # Otherwise key on a PARSE-STABLE merchant stem so the same real transaction
    # fingerprints identically no matter how the parser phrased the description.
    stem = _fingerprint_merchant(description)
    raw = f"{bank}|{account}|{date}|{round(float(amount),2)}|{stem}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── 6. MAIN CLASSIFY FUNCTION ─────────────────────────────────────────────────

def classify_transaction(
    description: str,
    amount: float,
    bank: str = None,
    user_rules: list = None,
    user_id: str = None,
) -> Tuple[str, str, str, bool]:
    """
    Main classifier. Returns (transaction_type, category, confidence, needs_review).
    Additional detail available in meta (see classify_with_meta).
    """
    result, _ = classify_with_meta(description, amount, bank, user_rules, user_id)
    return result


def classify_with_meta(
    description: str,
    amount: float,
    bank: str = None,
    user_rules: list = None,
    user_id: str = None,
) -> Tuple[Tuple[str, str, str, bool], Dict[str, Any]]:
    """
    Full classifier with metadata.
    Returns ((transaction_type, category, confidence, needs_review), meta_dict)
    """
    amt = float(amount or 0)
    meta: Dict[str, Any] = {
        'review_reason': None,
        'scores': {},
        'recurring_hint': False,
        'normalized_merchant': '',
        'matched_rule_scope': 'classifier',
        'matched_rule_id': None,
    }

    # ── Step 1: Normalize ──
    normalized = normalize_description(description)

    # ── Step 2: Extract merchant alias ──
    merchant = extract_merchant_alias(normalized)
    meta['normalized_merchant'] = merchant

    # ── Step 3: Check user rules ──
    if user_rules:
        match_types_order = ['exact', 'starts_with', 'contains', 'regex']
        # Sort: user rules first (user_id not None), then global (user_id None)
        # Within each scope: priority DESC, then more specific match_type first
        def rule_sort_key(r):
            scope = 0 if (r.get('user_id') and r.get('user_id') == user_id) else 1
            mt_order = match_types_order.index(r.get('match_type', 'contains'))
            priority = -(r.get('priority') or 0)
            return (scope, priority, mt_order)

        for rule in sorted(user_rules, key=rule_sort_key):
            if not rule.get('is_active', True):
                continue
            match_val = (rule.get('match_value') or '').lower()
            if not match_val:
                continue  # blank match_value would match everything -> skip
            match_type = rule.get('match_type', 'contains')
            match_field = rule.get('match_field', 'merchant')
            target = merchant if match_field == 'merchant' else normalized

            matched = False
            if match_type == 'exact' and target == match_val:
                matched = True
            elif match_type == 'starts_with' and target.startswith(match_val):
                matched = True
            elif match_type == 'contains' and match_val in target:
                matched = True
            elif match_type == 'regex':
                try:
                    matched = bool(re.search(match_val, target, re.IGNORECASE))
                except:
                    pass

            if matched:
                tx_type = rule.get('transaction_type') or 'expense'
                category = rule.get('category') or 'Other'
                confidence = 'high' if (rule.get('confidence_override') or 0) >= 0.8 else 'medium'
                scope = 'user' if (rule.get('user_id') and rule.get('user_id') == user_id) else 'global'
                meta['matched_rule_scope'] = scope
                meta['matched_rule_id'] = str(rule.get('id', ''))
                meta['recurring_hint'] = emit_recurring_hint(category, merchant)
                return (tx_type, category, confidence, False), meta

    # ── Step 4: Filter summary/invalid rows ──
    if is_summary_row(normalized, amt):
        meta['review_reason'] = 'summary_row'
        return ('excluded', 'Other', 'high', False), meta

    # ── Step 5: Classify transaction type ──
    tx_type, type_review_reason = classify_transaction_type(normalized, merchant, amt, bank)

    # Cash withdrawals count as spending (cash out = intent to spend). Retype to
    # 'expense' so spend calculations include it, but force 'Cash & ATM' category.
    _force_cash_category = False
    if tx_type == 'cash':
        tx_type = 'expense'
        _force_cash_category = True

    # Loan/mortgage payments count as FIXED spending (housing/car/loans are real
    # monthly outflows). Retype to 'expense' and route the category by keyword.
    # mortgage/rent/HOA -> Rent/Mortgage ; everything else -> Loan Payment.
    # (Both are in FIXED_CATEGORIES, so fixed_classifier marks them fixed.)
    _force_loan_category = None
    if tx_type == 'loan_payment':
        tx_type = 'expense'
        if re.search(r'\b(mortgage|mtg|rent|lease|hoa|home.?loan|escrow|'
                     r'lakeview|rocket.?mortgage|nationstar|mr.?cooper|pennymac|'
                     r'loandepot|freedom.?mortgage|quicken.?loan)\b', normalized):
            _force_loan_category = 'Rent/Mortgage'
        else:
            _force_loan_category = 'Loan Payment'

    # Non-expense types — return immediately
    if tx_type != 'expense':
        # Determine category for non-expenses
        if tx_type == 'income':
            category = 'Salary' if re.search(r'\b(payroll|salary|wages|stripe|adp|paychex|gusto)\b', normalized) else 'Other'
        elif tx_type == 'loan_payment':
            category = 'Loan Payment'
        elif tx_type == 'credit_card_payment':
            category = 'Credit Card Payment'
        elif tx_type == 'card_credit':
            category = 'Card Credit'
        elif tx_type == 'transfer':
            category = 'Transfer'
        elif tx_type == 'refund':
            category = 'Refund'
        elif tx_type == 'cash':
            category = 'Cash & ATM'
        elif tx_type == 'reimbursement':
            category = 'Refund'
        else:
            category = 'Other'

        if type_review_reason:
            meta['review_reason'] = type_review_reason
        meta['recurring_hint'] = emit_recurring_hint(category, merchant)
        needs_review = type_review_reason is not None
        confidence = 'low' if needs_review else 'high'
        return (tx_type, category, confidence, needs_review), meta

    # Cash withdrawal: force Cash & ATM category, skip merchant scoring.
    if _force_cash_category:
        meta['recurring_hint'] = False
        return ('expense', 'Cash & ATM', 'high', False), meta

    # Loan/mortgage payment: force its routed category (fixed), skip merchant scoring.
    if _force_loan_category:
        meta['recurring_hint'] = True
        return ('expense', _force_loan_category, 'high', False), meta

    # ── Step 6: Score categories (expense only) ──
    scores = score_categories(normalized, merchant)
    scores = resolve_ambiguity(normalized, merchant, scores)
    meta['scores'] = scores

    # ── Step 7: Evaluate confidence ──
    category, confidence, needs_review, review_reason = evaluate_confidence(scores)

    # Override review reason with type reason if exists
    if type_review_reason:
        review_reason = type_review_reason
        needs_review = True

    # Non-English / unknown merchant check
    if category == 'Other' and not re.search(r'[a-zA-Z]{3,}', merchant):
        review_reason = 'international_merchant'
        needs_review = True

    meta['review_reason'] = review_reason
    meta['recurring_hint'] = emit_recurring_hint(category, merchant)

    # ── Step 8: Return ──
    return (tx_type, category, confidence, needs_review), meta


# ── 7. UTILITY ────────────────────────────────────────────────────────────────

def should_exclude_from_spending(transaction_type: str) -> bool:
    """Returns True if transaction should be excluded from spend calculations."""
    return transaction_type in {
        'income', 'transfer', 'credit_card_payment',
        'card_credit', 'refund', 'excluded', 'reimbursement', 'cash'
    }



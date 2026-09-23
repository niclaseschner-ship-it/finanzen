# Finanzen

*[Deutsche Fassung](README.de.md) · the application itself is in German.*

**Your bank statements become a report that tells you where the money went —
on your own machine, without an account anywhere, and every categorisation is justified.**

- 🔒 **Local.** No cloud, no bank access, no account. The data never leaves your machine.
- 🔍 **Traceable.** Every transaction shows *why* it landed in its category. What is unclear stays visibly unclear instead of being guessed.
- 🧾 **Receipts instead of guesswork.** For a transaction like "AMAZON −57.50 €" you see *what* was in it —
  linked automatically from your own order emails, via the order number.
- ⚡ **No installation.** Python 3.10 is enough — no `pip install`, no build, no Docker.

[![Statistics](docs/bilder/statistik.png)](docs/bilder/statistik.png)

## Try it in 30 seconds — without your own data

A complete, invented example household covering 18 months in the real bank format:

```bash
git clone https://github.com/niclaseschner-ship-it/finanzen.git
cd finanzen
python beispieldaten/erzeugen.py     # creates data + configuration, runs the pipeline
```

The script tells you at the end how to start the server. The demo has its **own
database** in `beispieldaten/demo/` — it touches nothing else, and deleting
`beispieldaten/demo/` removes it without a trace.

| ✏️ Editor | 📑 Contracts | 🏖️ Trips |
|---|---|---|
| [![Editor](docs/bilder/editor.png)](docs/bilder/editor.png) | [![Contracts](docs/bilder/vertraege.png)](docs/bilder/vertraege.png) | [![Trips](docs/bilder/reisen.png)](docs/bilder/reisen.png) |
| Category, labels — and the justification | Fixed costs, detected purely from recurrence | Vacations, detected purely from purchase locations |

The demo also ships **receipt emails** (as a real mbox, exactly as Thunderbird creates it) —
so the receipt linking is visible immediately. It deliberately also shows what does **not**
resolve: a few merchants stay `unkategorisiert` (uncategorised) instead of being guessed.
Only the **assets** view stays empty without your own data (it needs maintained numbers);
the retirement projection can be explored right away.

## How it works

One SQLite file is the single source of truth; every report is **reproducibly** recomputed
from it. Transactions come 1:1 from the bank data and are never invented; categories and
labels are a derived layer that can be recalculated at any time. Nothing is silently
deleted — status instead of deletion.

Supported are the CSV exports of **DKB** and **GLS**. Other banks need a few lines in
[`scripts/parse_konten.py`](scripts/parse_konten.py) — contributions welcome, see
[Contributing](#contributing).

## 🧾 Receipts from emails — what was actually in that package?

The bank statement says "AMAZON PAYMENTS EUROPE S.C.A, −57.50 €". That is the point where
every budgeting tool stops and you go searching your mailbox yourself. This app takes that
step with you: it links transactions to your **own order and payment emails** and shows
the product line right next to the transaction.

[![Receipt linking](docs/bilder/belege.png)](docs/bilder/belege.png)

**Mechanical, not guessed** — and every link states how certain it is:

| Path | Certainty |
|---|---|
| Order number from the payment reference appears in the email | **certain** |
| PayPal transaction ID | **certain** |
| PayPal merchant + amount within a time window | good |
| Merchant + amount + date (±5 days) | estimate, marked as such in the editor |

Ambiguous cases are **not** linked — a wrong match would be worse than none. PDF
attachments are stored and their text is searched too (that is what the optional
`pymupdf` is for), so invoices inside attachments are found as well.

**Where the emails come from:** **Thunderbird**. The import reads mbox files, and
Thunderbird creates exactly those. Hence the detour instead of direct mailbox access:
**this app never gets your email password**, the messages stay local, and you decide
per folder what gets imported.

```bash
python scripts/einrichten.py --mail    # finds the profiles, lists the folders with sizes
```

One step is easy to miss: in Thunderbird under *Account Settings → Synchronization &
Storage*, "Keep messages on this computer" must be enabled — otherwise the mbox files are
empty. The import is idempotent; interrupting and resuming later is safe.

Emails are **context only, never a transaction source**: amounts and transactions always
come 1:1 from the bank. Everything works without emails — the detail column just stays
emptier.

## When to use this project — and when another

There are mature alternatives, and for many people they are the better choice. This one is
deliberately small and covers a narrow case:

| Use … | if you … |
|---|---|
| **[Firefly III](https://github.com/firefly-iii/firefly-iii)** | want double-entry bookkeeping, budgets, multiple users, a mobile app and banking-API connections. The incumbent — far more features, at the cost of a server, a database and a learning curve. |
| **[Actual Budget](https://github.com/actualbudget/actual)** | want envelope budgeting (YNAB style), i.e. **plan ahead** instead of analysing in hindsight. |
| **[beancount](https://beancount.github.io/) / hledger** | like plain-text accounting and write your own reports. |
| **this project** | want to know **where your money went** without setting up a system — and without any software ever seeing your bank or email password. |

What exists here and not there:

- **Receipt linking from your own mailbox.** Next to "AMAZON −57.50 €" you see the product
  line from your order email. Receipt matching otherwise exists mainly as commercial SaaS
  for expense reports, or in [Midday](https://github.com/midday-ai/midday) for freelancers.
- **Justification requirement.** Every category carries its source. What is unclear stays
  visibly unclear — nothing is guessed to make the statistics look tidy.
- **No setup.** No server, no Docker, no database installation, no `pip install`.
- **Trip and contract detection** purely from transaction patterns, without you creating anything.

What does **not** exist here: budgets and targets, multi-user operation, a mobile app,
automatic bank fetching (deliberately — that would mean credentials), foreign-currency
accounts, double-entry bookkeeping. And the CSV formats so far are **DKB and GLS**.

## Requirements
- **Python 3.10+** — the core uses only the **standard library** (no `pip install` needed).
- Optional: **PyMuPDF** (`pip install pymupdf`) — only for text from PDF email attachments.
- **No internet needed.** Chart.js ships inside the project (`scripts/seiten/chart.min.js`)
  and is placed next to the generated page — the page carries all transactions in itself,
  so a script from a foreign server has no business there.

## Setup
There is **nothing to install** beyond Python — the work is configuration. The guided path
reads the account exports and only asks what no CSV contains:

```bash
cd scripts
python einrichten.py --pruefen   # read-only: what is inside the exports?
python einrichten.py             # creates konfig.json
python einrichten.py --mail      # optional: receipts from Thunderbird
```

If you use Claude Code, you can start the bundled skill `finanz-einrichtung`
([`.claude/skills/`](.claude/skills/)) instead — it additionally reviews the result and
looks for typical setup mistakes.

## Configuration — `konfig.json`
Everything that differs from household to household lives in **one** file in the project
folder. **No source-code editing required.** Doing it by hand works too:

```bash
copy konfig.beispiel.json konfig.json     # copy the template, then fill it in
cd scripts && python konfig.py            # validates the file and shows what was read
```

| Section | What it holds | Why it matters |
|---|---|---|
| `konten.eigene_giro` | your own checking accounts (IBAN → name) | **System boundary.** Transfers between these accounts are not expenses. If an account is missing here, the statistics are too high. |
| `konten.zuordnung` | brokerage, loans, salary, child benefit | counted, but with a fixed default category that no merchant rule overrides |
| `kategorien` | the fixed category list | exactly one per transaction; add your own (e.g. "Immobilie X") |
| `haushalt.heimat_orte` | home town + neighbouring towns | trip detection. Without it, everyday life is one endless trip. |
| `haushalt.eigene_namen` | family/landlord names | prevents private emails from landing as receipt context on transactions |
| `eigene_regeln` | property manager, landlord, favourite restaurant | the broad rules for common merchants are built into [`scripts/rules.py`](scripts/rules.py) |

`konfig.json` is **not** in git (see [`.gitignore`](.gitignore)) — only the template is
versioned. As long as no `konfig.json` exists, the example configuration runs: server and
pages start, but `run_all.py` **refuses** to run. With a foreign account map the reports
would be silently wrong, and that is worse than an abort.

The assets view has its own maintained file — template:
[`vermoegen/positionen.beispiel.json`](vermoegen/positionen.beispiel.json).

## Configuration (paths)
All paths live in **one** place in [`scripts/db.py`](scripts/db.py) and can be overridden
via environment variables:

| Env variable | Default | Meaning |
|---|---|---|
| `FINANZEN_BASE` | this repo's folder | project folder: DB, `output/`, `attachments/` |
| `FINANZEN_BANK` | `<BASE>\konten` | inbox for bank CSV exports (= upload target) |
| `FINANZEN_BANK_CSV` | `<BASE>\output\transaktionen.csv` | merged account CSV |
| `FINANZEN_PORT` | `8765` | server port — use a different one if a second instance (e.g. the demo) runs in parallel |

The defaults are **relative to the repo** — a fresh clone runs without any environment
variables set. You only set them if the data should live elsewhere:

```bash
# example: account exports live on another drive
set FINANZEN_BANK=D:\bank-exporte
```

## Quickstart
1. **Drop bank exports:** copy DKB/GLS CSVs into `konten/`
   (or upload later via the import page). The format is detected automatically.
   At least 12 months make sense — contract and trip detection need recurrences.
2. **Create the configuration:** `python scripts/einrichten.py` (or fill in the template
   `konfig.beispiel.json` by hand). Validate: `python scripts/konfig.py`.
3. **Run the pipeline** (idempotent, repeatable at will):
   ```bash
   cd scripts
   python run_all.py
   ```
4. **Start editor/statistics:**
   ```bash
   python app.py     # -> http://localhost:8765
   ```

## The pages (all under http://localhost:8765)
- **✏️ Editor** (`/`) — review every transaction, set category/labels/comment.
- **📊 Statistics** (`/statistik.html`) — income/expenses per month, category stack,
  ranking, trips. Filters: year · categories · contracts · label. Click a bar → transactions.
- **📑 Contracts** (`/vertraege`) — mechanically detected recurring payments (= fixed costs),
  confirm/reject, active/expired.
- **🏖️ Trips** (`/reisen`) — automatically detected trips (contiguous spending outside the
  home region), confirm → transactions become "Urlaub" (vacation).
- **📥 Import** (`/import`) — all data sources with range/state, a timeline + slider for the
  considered period, bank CSV upload and "process data".

## Layout
- `scripts/` — the core (pipeline + server). Details & order: [`PROCESS.md`](PROCESS.md).
- `scripts/extra/` — optional/one-off tools (text report, AI seed, legacy dashboard),
  not part of the main run.
- `vermoegen/` — assets snapshot (balances/holdings instead of transactions), separate run.
- `konten/` — **inbox** for bank CSV exports · `output/` — generated pages ·
  `attachments/` — stored email attachments · `finanzen.db` — the database.
- `beispieldaten/` — invented demo household for trying things out · `demo/` — anonymised
  example page · `docs/bilder/` — screenshots ·
  [`DECISIONS.md`](DECISIONS.md) — log of decisions.
- `tests/` — tests, pure standard library: `python -m unittest discover -s tests -t tests`

**Only code and docs are versioned.** Database, account exports, attachments, generated
pages and personal configuration are excluded via `.gitignore` — this repo can be shared
without shipping bank data.

## Data & privacy
Everything stays **local**. The server listens exclusively on `127.0.0.1` and rejects
requests with a foreign `Host` or `Origin` header — otherwise any website in the same
browser could read or write along.

Exactly one thing goes outside, and only when OSM merchant-type detection runs:
**merchant name + town** to OpenStreetMap/Nominatim (no amounts, no account numbers).
Note that merchant names of small businesses are often personal names. The bank data and
the database never leave the machine.

## Contributing
Whoever uses the application with their own data finds things nobody else can find: a bank
whose format misbehaves, a merchant no rule matches, a confusing spot in the guide. That is
the most valuable contribution — please return it as a branch:

```bash
git checkout -b erfahrung/<short-name>
python -m unittest discover -s tests -t tests    # everything still green?
git commit -am "fix: <what>"
git push -u origin erfahrung/<short-name>
```

| Finding | Where it goes |
|---|---|
| Merchant that many households have (supermarket, insurer, utility, streaming) | `SEED2` in [`scripts/rules.py`](scripts/rules.py) |
| Merchant only your household has | `eigene_regeln` in your `konfig.json` — do **not** commit |
| Bank format not recognised | [`scripts/parse_konten.py`](scripts/parse_konten.py) + a test |
| Guide was confusing | `README.md` / `PROCESS.md` |
| Non-obvious decision made | `DECISIONS.md` |

**Look at `git diff --cached` before pushing.** The `.gitignore` covers database, exports,
attachments and `konfig.json` — but a rule carrying your landlord's name still does not
belong in `rules.py`. The yardstick is not "are there IBANs in here?", but: **could this
line appear unchanged in any other household?** A hyper-local shop, a kindergarten, the
name of a domestic helper — that is not a rule but an observation about one specific family
in one specific place. Such patterns belong in your own `konfig.json`.

### What matters most when reviewing someone else's contribution
Four spots can do great damage with a single line — please look closely at changes there:

| File | Why |
|---|---|
| `scripts/app.py` (bind address) | `127.0.0.1` → `0.0.0.0` exposes the entire dataset including the write interface to the network |
| `.gitignore` | one removed line, and the next `git commit -am` pushes real bank data irrevocably into public history |
| `scripts/frontend.py` / `liste.py` (embedding) | externally controlled text is written into the page here; without escaping this is a hole |
| `.claude/skills/**` | gets **executed** by an agent, not just read |

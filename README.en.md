# Finanzen

*[Deutsche Fassung](README.md) — the German README is the complete one; this is a condensed
version for English readers. The application itself is in German.*

**Turns your bank statements into a spending overview that tells you where the money went —
on your own machine, without an account anywhere, and every categorisation is justified.**

- 🔒 **Local.** No cloud, no bank API, no account. Your data never leaves the machine.
- 🔍 **Traceable.** Every booking shows *why* it landed in its category. What is unclear stays
  visibly unclear instead of being guessed.
- 🧾 **Receipts, not guesswork.** For a booking like "AMAZON −57.50 €" it shows *what was in the
  parcel* — matched automatically against your own order e-mails via the order number.
- ⚡ **No installation.** Python 3.10 is enough. No `pip install`, no build, no Docker.

[![Statistics](docs/bilder/statistik.png)](docs/bilder/statistik.png)

## Try it in 30 seconds — no data of your own needed

A complete, fictional example household covering 18 months in real bank export format:

```bash
git clone https://github.com/niclaseschner-ship-it/finanzen.git
cd finanzen
python beispieldaten/erzeugen.py     # creates data + config and runs the pipeline
```

The script prints how to start the server. The demo lives in its own folder
`beispieldaten/demo/` with its **own database** — deleting that folder removes it without
a trace. It ships with example receipt e-mails as a real mbox file, so the receipt matching
can be seen immediately.

| ✏️ Editor | 📑 Contracts | 🏖️ Trips |
|---|---|---|
| [![Editor](docs/bilder/editor.png)](docs/bilder/editor.png) | [![Contracts](docs/bilder/vertraege.png)](docs/bilder/vertraege.png) | [![Trips](docs/bilder/reisen.png)](docs/bilder/reisen.png) |
| Category, labels — and the reasoning | Recurring costs, detected purely from repetition | Holidays, detected purely from where you shopped |

## Receipt matching — what was actually in that parcel?

[![Receipt matching](docs/bilder/belege.png)](docs/bilder/belege.png)

The statement says "AMAZON PAYMENTS EUROPE S.C.A, −57.50 €". That is where every other
household-budget tool stops and you start digging through your mailbox. This one links the
booking to **your own order and payment e-mails** and shows the product line right next to it.

Mechanical, not guessed — and every link states how certain it is:

| Method | Confidence |
|---|---|
| Order number from the payment reference appears in the mail | **certain** |
| PayPal transaction ID | **certain** |
| PayPal merchant + amount within a time window | good |
| Merchant + amount + date (±5 days) | estimate, flagged as such in the editor |

Ambiguous cases are **not** linked — a wrong link is worse than none. PDF attachments are
stored and their text searched too (optional `pymupdf`).

**Where the mails come from: Thunderbird.** The importer reads mbox files, and Thunderbird
produces exactly those. Hence the detour instead of direct mailbox access: **this application
never receives your mail password**, the messages stay local, and you choose per folder what
gets imported. E-mails are context only, never a source of bookings — amounts always come
1:1 from the bank.

## When to use this — and when not

| Use … | if you … |
|---|---|
| **[Firefly III](https://github.com/firefly-iii/firefly-iii)** | want double-entry bookkeeping, budgets, multiple users, a mobile app and banking-API integration. Far more features, but a server, a database and a learning curve. |
| **[Actual Budget](https://github.com/actualbudget/actual)** | want envelope budgeting (YNAB style) — i.e. planning **ahead** rather than analysing the past. |
| **[beancount](https://beancount.github.io/) / hledger** | like plain-text accounting and write your own reports. |
| **this project** | want to know **where your money went**, without setting up a system — and without any software ever seeing your banking or mail password. |

Not included here on purpose: budgets and targets, multi-user, mobile app, automatic bank
fetching (that would mean handing over credentials), foreign-currency accounts, double-entry
bookkeeping.

**Bank formats supported so far: DKB and GLS** (German banks, CSV exports). Adding another
bank is a few lines in [`scripts/parse_konten.py`](scripts/parse_konten.py) — contributions
very welcome.

## How it works

One SQLite file is the single source of truth; every analysis is recomputed from it
**reproducibly**. Bookings come 1:1 from the bank data and are never invented. Categories and
labels are a derived layer that can be recalculated at any time. Nothing is silently deleted —
status instead of deletion.

The pipeline: merge exports → apply the system boundary (transfers between your own accounts
are not expenses) → enrich → match receipts → categorise via rules, an AI fallback and your
manual layer → detect trips and contracts → build the pages. Details in
[`PROCESS.md`](PROCESS.md) (German).

## Setup

There is **nothing to install** beyond Python — the work is configuration. Everything that
differs from household to household lives in a single `konfig.json`:

```bash
cd scripts
python einrichten.py --pruefen   # read-only: what is in the exports?
python einrichten.py             # creates konfig.json interactively
python einrichten.py --mail      # optional: receipts from Thunderbird
```

`konfig.json` is **not** in git — only the template is. Without it, `run_all.py` refuses to
run: with someone else's account map the results would be silently wrong, and that is worse
than an abort.

## Privacy

Everything stays local. The server binds to `127.0.0.1` only and rejects requests carrying a
foreign `Host` or `Origin` header, so no other website in the same browser can read or write.
Exactly one thing leaves the machine, and only if the OpenStreetMap category lookup runs:
**merchant name + town** (no amounts, no account numbers). Note that small businesses often
have a person's name as their merchant name.

## Contributing

Anyone using this with their own data finds things nobody else can: a bank format that
breaks, a merchant no rule matches, a misleading passage in the docs. That is the most
valuable contribution — please send it back as a branch. Details and the review checklist are
in the [German README](README.md#mitarbeiten).

The yardstick for anything going into `scripts/rules.py`: **could this line be identical in
any other household?** If not, it belongs in your private `konfig.json`.

## Licence

MIT — see [LICENSE](LICENSE).

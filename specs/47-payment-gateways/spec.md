# Feature Specification: Paying an entry fee through a connector

**Feature Branch**: `47-payment-gateways`
**Created**: 2026-10-30
**Status**: Draft -- for the maintainer's review before any plan or code. Open points are listed
under "Questions for the maintainer" with the default the spec assumes.
**Issue**: [#47](https://github.com/dchernykh1984/cycling-site/issues/47) ("Payment gateways"), with
the maintainer's brief of 2026-10-29 (the issue's comment of 2026-10-30)
**Input**: An organizer who takes a fee for an event sets a fee schedule and chooses how
participants may pay. A participant sees today's price and pays by being sent to a payment service
that credits the organizer directly. The site stores no card data and no organizer secret: only an
identifier of the organizer's account at that service, the amount, and whether the entry is paid.
Adding a payment service to the site is adding one connector. The way it works today -- the
organizer marks an entry paid by hand -- stays as the first connector.

## Two concerns above everything else

1. **Money safety.** The site never holds money and never sees a card number. A payment service
   takes the payment and pays the organizer; the site is told the result.
2. **Legal liability.** The site keeps the minimum: for each organizer, an identifier at a payment
   service that lets money be credited to them and is useless to a thief, and for each entry, what
   was due and what was paid. KYC, taxes and payouts are the service's and the organizer's.

In Kazakhstan's terms, a site that only tells a payment service "this amount, to this merchant"
provides no payment service itself (the law "On payments and payment systems" counts the information
and technological interaction between a beneficiary and the payment service provider among the things
that are *not* payment services), while a site that collected fees and passed them on would need the
National Bank's registration as a payment organisation. This spec keeps the site on the first side
of that line.

## Background: what the research found (2026-10-30)

Five options were researched with sources and a sceptic's pass each; the full notes are the
maintainer's (`tmp/payment-gateways/`, not committed) and summarised in the pull request. In short:

| Option | Confirms a payment | What the site stores | Verdict |
| --- | --- | --- | --- |
| A. Manual gateway plus the organizer's own payment link (any service) | by the organizer | a URL | first delivery |
| B. Kaspi Pay API on behalf of each organizer | by the service | the organizer's API secret | no public API for platforms; stores a secret |
| C. A Kazakhstan payment organisation in a marketplace model (one platform contract, one contract per organizer, a merchant id per organizer) | by the service | a merchant id, plus one platform key in the environment | second delivery, after talks with providers |
| D. Stripe Connect | by the service | an account id | not available to a platform or organizers in Kazakhstan or Russia |
| E. The organizer's own account at any service, driven by the site | by the service | the organizer's API secret | no: stores a secret per organizer |

Cross-cutting findings that shape the requirements:

- No connector to a Russian service (Mir, SBP, YooKassa and the like): the Mir operator and the
  largest Russian banks are under blocking sanctions, the site is hosted and proxied by US companies,
  and the Kazakhstan providers of option C will not stand next to Mir. Participants without a
  supported method pay through the manual gateway.
- Taxes on a fee are the organizer's, under their own regime; an organizer who is a private person
  collecting fees onto a personal card may trip Kazakhstan's reporting of incoming transfers (100 or
  more senders in each of three months and more than 12 minimum wages in those months), so the
  site tells them so where they set a fee, and leaves the choice to them.

## Decisions proposed (to be confirmed by the maintainer)

Numbered so that a review can answer by number. Each names the question in `questions` it answers.

1. **A connector is a kind of gateway, not a gateway.** The site ships a catalogue of connectors
   (`manual`, `link`, later one per payment service). An organizer *enables* a connector for an event
   and, where the connector needs one, points it at their *payout account* -- the identifier the
   service gave them. Adding a service is adding a connector to the catalogue; the registration code
   does not change.
2. **The manual connector is always available** and needs no account: the organizer records a
   payment in the participant list, as today, now with the amount. It is the fallback for every
   participant whose method the event's other connectors do not take.
3. **The link connector stores a URL.** The organizer pastes the address of their payment page at
   any service (for example Kaspi Pay's remote-payment link, a bank's invoice link, a payment link
   abroad). The participant is sent there with the amount shown; confirmation stays with the
   organizer, as for the manual connector. The site shows the participant the link's domain before
   sending them, so a wrong link is seen.
4. **An automatic connector stores a merchant identifier of the organizer and nothing secret of
   theirs.** The platform's own credentials, where the service needs them, live in the deployment's
   environment like the site's other keys. A connector that would need an organizer's secret is not
   added to the catalogue (research option E).
5. **One currency per event**, set by the organizer; its default is the currency of the country of
   the event's place, read from data, never written into the code (principle VI). The site does no
   conversion. (Q9)
6. **A fee schedule is a list of steps.** Each step is a date (and time, in the event's time zone)
   from which it applies, and a price; a step may give a different price per registration category.
   Before the first step the price is the first step's; after the last, the last step's. A schedule
   with one step is a fixed fee. Steps by number of entries ("the first 50 pay less") are a later
   addition the model leaves room for. (Q6)
7. **The price is the one in force when the participant pays**, not when they registered: that is
   what makes a rising schedule bring registered participants to the start. The price shown when a
   participant starts a payment holds for a short, fixed time so that a step change during payment
   does not refuse it. For the manual connector, the organizer records the amount actually received,
   prefilled with the price in force at that moment. (Q7)
8. **An unpaid entry is kept**, as today; the organizer may set a time after which an unpaid entry
   no longer counts towards the limit (it stays visible to its participant and to the organizer, and
   pays at the then-current price). Default: no such time. (Q8)
9. **Refunds are not made by the site.** An organizer records "refunded" on a payment the way they
   record "paid"; the money goes back through their service. The site's terms already say the
   organizer answers for fees and refunds. (Q5)
10. **The site takes nothing from a fee.** No percentage, no fixed charge, in this delivery. Paid
    extras for organizers (subscriptions) are a separate feature on the same connectors. (Q2)
11. **A private person may organise a paid event** through the manual and link connectors; the fee
    settings show them the warning of the "Background" section. (Q3)
12. **Everything an organizer or a participant does here is also an API operation** under
    `/api/v1/` with the same rules (principle VII); the payment service's callbacks arrive on a
    machine-facing URL without a language prefix.

## User Scenarios & Testing *(mandatory)*

### User Story 1 -- Set a fee and the ways to pay it (Priority: P1)

An organizer turns on payment for an event, writes the fee schedule and ticks which connectors take
payment: the manual one, their payment link, and -- once there is one -- an automatic one pointed at
their payout account.

**Why this priority**: Without it nothing else exists; today the event only says "payment required".

**Independent Test**: Create an event with a three-step schedule and the manual connector; the event
page shows today's price and the next step; the participant list offers "record a payment" with the
amount prefilled.

**Acceptance Scenarios**:

1. **Given** an organizer editing an event with registration, **When** they turn payment on,
   **Then** the form asks for the currency (prefilled from the place's country), at least one
   schedule step (date-time in the event's zone, price, optionally a price per category) and at
   least one connector; the manual connector is ticked and cannot be unticked.
2. **Given** a connector that needs a payout account, **When** the organizer has none, **Then** the
   form refuses to enable it and links to the profile card where one is added.
3. **Given** a saved schedule, **When** anyone opens the event page, **Then** it shows the price in
   force now and, where there is a later step, the date it changes and the next price, in the
   reader's language (dates in words, the interface skill's rule 12).
4. **Given** an organizer, **When** they turn payment on, **Then** the form shows a one-paragraph
   note that fees are their income under their own tax status and that transfers to a private
   person's account are reported to the tax authority above a threshold, with a link to a knowledge
   article; the site does not know whether an organizer is a company, so everyone sees it.

---

### User Story 2 -- Pay for an entry (Priority: P1)

A participant who has registered (or whose manager registered them) sees what is due and pays: an
automatic connector sends them to the service and the entry becomes paid when the service confirms;
the link connector sends them to the organizer's page; the manual connector tells them how to settle
with the organizer.

**Why this priority**: The participant's side is where the money and the motivation are.

**Independent Test**: With a test connector that confirms every payment, register and pay; the entry
turns paid without the organizer; with the link connector, the participant lands on the configured
URL and the entry stays unpaid.

**Acceptance Scenarios**:

1. **Given** an unpaid entry of mine (or of a member I manage), **When** I open its event page, my
   profile or the registration confirmation, **Then** I see the amount due, the currency and the
   connectors the event takes, each named by its service, the manual one last and worded as
   "arrange with the organizer".
2. **Given** I choose an automatic connector, **When** I press pay, **Then** a payment is recorded as
   started with the price in force, and I am sent to the service; **When** the service confirms,
   **Then** the payment is confirmed and the entry is paid; the page I return to says paid, or that
   the confirmation is on its way when I come back before it, and shows the result when it arrives.
3. **Given** I choose the link connector, **When** I press pay, **Then** I see the amount, the domain
   of the link and a button that opens it; the entry stays unpaid until the organizer records it.
4. **Given** the service reports failure or I come back without paying, **Then** the entry stays
   unpaid and I may try again; nothing is counted twice.
5. **Given** a price step passes while I am on the service's page, **Then** the started payment is
   still accepted at the price it started with, within the holding time.
6. **Given** a paid entry, **Then** no pay button is shown; my profile's entry card shows the amount
   and when it was paid.

---

### User Story 3 -- Record a payment by hand (Priority: P1)

The organizer, or any manager of the event, records in the participant list that a participant paid
-- cash at the start, a transfer, a payment through the link -- and, when needed, that it was
refunded.

**Why this priority**: It is today's only flow, and every event keeps it as the fallback.

**Independent Test**: In the participant list press "record a payment" on an unpaid entry; the form
prefills today's price; saving marks the entry paid with the amount, the time and who recorded it.

**Acceptance Scenarios**:

1. **Given** a manager of the event and an unpaid entry, **When** they record a payment, **Then** the
   amount is prefilled with the price in force and may be changed; the entry is paid; the record
   says who recorded it and when.
2. **Given** a paid entry, **When** the manager records a refund, **Then** the entry is unpaid again,
   the refund is kept in the entry's payment history with its amount and time, and the public list
   stops counting the entry where the event requires payment.
3. **Given** the participant list, **Then** the organizer sees each entry's amount paid and the step
   it was paid at; the public list shows only the paid/unpaid state, as today.

---

### User Story 4 -- Tell the site where the money goes (Priority: P2)

An organizer adds, in their profile, the identifier of their account at a payment service -- the
link for the link connector, the merchant id for an automatic one -- and may replace or remove it.

**Why this priority**: Needed by every connector but the manual one; separable from events.

**Independent Test**: Add a payout account for the link connector with an `https://` address; it is
offered when editing an event; remove it; the event form no longer offers that connector.

**Acceptance Scenarios**:

1. **Given** an organizer's profile, **Then** a card "Accepting payments" lists each connector in the
   catalogue that needs an account, with the field it asks for, in the reader's language.
2. **Given** a value that does not fit the connector's rule (a link without `https://`, a merchant id
   of the wrong shape), **Then** it is refused with the reason.
3. **Given** a payout account used by a published event, **When** the organizer removes it,
   **Then** the site says which events lose that connector and asks to confirm.
4. **Given** a participant (not an organizer), **Then** the card is not shown.

---

### User Story 5 -- Through the API (Priority: P2)

A client reads an event's fee schedule and connectors, starts a payment for an entry, records a
manual payment or a refund as a manager, and reads an entry's payments -- with the same rights as on
the site. A payment service posts its confirmation to the site.

**Why this priority**: Principle VII; the timing tools already read `is_paid`.

**Independent Test**: The API tests cover each operation for an owner, a manager, a stranger (403 or
404 as the site does), and a forged callback (refused).

**Acceptance Scenarios**:

1. **Given** an event, **Then** `GET /api/v1/competitions/{id}` carries its currency, schedule and
   enabled connectors; the participants endpoint keeps `is_paid` and `require_payment` unchanged.
2. **Given** my entry, **When** I `POST .../payments` with a connector, **Then** I get the redirect
   address and the payment id; **given** someone else's entry, **Then** 403 or 404 as the site rules.
3. **Given** a manager, **When** they `POST .../payments` with the manual connector and an amount,
   **Then** the payment is confirmed at once; a refund is posted the same way.
4. **Given** a callback from a service, **When** its signature does not verify or its payment id is
   unknown, **Then** it is refused and logged; **when** it repeats a confirmation already applied,
   **Then** it is acknowledged and nothing changes.

---

### Edge Cases

- A step's date-time is in the event's time zone (issue #344); the event page shows it in the
  reader's zone too when the offsets differ.
- Two steps on the same instant are refused; steps are kept in order.
- A category added after the schedule has per-category prices takes the step's general price.
- A relay entry is one entry and pays one fee (the team's).
- A manager registering several members (issue #315) pays for each entry separately in this
  delivery; one payment for several entries is a later addition.
- A started payment that is never confirmed expires after the holding time and is kept as such; a
  new one may be started. Two confirmed payments for one entry cannot happen: a second confirmation
  of the same external id is idempotent, a confirmation for an entry already paid is recorded and
  flagged for the organizer.
- An entry with a confirmed, unrefunded payment is neither cancelled by its participant nor deleted
  by a manager: the page says to ask the organizer, who records the refund first. Payment records
  outlive their entry: when an entry is deleted after its refund, its payments keep the event, the
  participant's name and the amounts.
- The link connector cannot carry the amount to every service (Kaspi's link lets the payer type the
  amount); the page therefore shows the amount large and asks the participant to type exactly it.
- An event whose currency changes after payments exist is refused the change.
- Amounts are whole units or two decimals as the currency defines; formatting follows the reader's
  locale; the currency code is not translated.
- The entry form of an event with a fee says the price before the participant submits, so nobody
  registers without knowing.
- An automatic connector's service is down: the pay button says so and offers the other connectors.
- The participant returns from the service before its confirmation arrives: the page says the
  confirmation is awaited and refreshes itself; no second payment is offered during the holding time.

## Requirements *(mandatory)*

### Functional Requirements

Connectors:

- **FR-PAY-001**: The site has a catalogue of payment connectors; each declares its name (translated
  where shown), whether it confirms payments itself, what it asks an organizer for (nothing, a URL,
  an identifier with a validation rule) and that none of it is a secret of the organizer's.
- **FR-PAY-002**: The catalogue in this delivery has `manual` (no account; confirmed by a manager)
  and `link` (an `https://` URL; confirmed by a manager). An automatic connector is added as one
  catalogue entry plus its callback handling, with no change to registration code; a test connector
  in the test suite proves it.
- **FR-PAY-003**: Which connectors a deployment offers is a setting (`PAYMENT_CONNECTORS`), checked
  at start-up like `MAP_LINK_SERVICES`; an unknown name is a warning, a connector whose platform
  credentials are missing is an error.

Payout accounts:

- **FR-PAY-004**: An organizer (role organizer and up) keeps at most one payout account per
  connector: the connector's identifier, when it was added, and a label for themselves. Nothing else
  of the service's is stored.
- **FR-PAY-005**: Removing an account used by an event disables that connector on the event after
  the organizer confirms; payments already recorded keep their connector's name.

Fee schedule:

- **FR-PAY-006**: An event that requires payment has a currency (ISO 4217 code, default from the
  place's country, from data) and one or more steps: an instant in the event's zone, a price, and
  optional prices per category; the price in force at an instant is that of the latest step not
  after it, or the first step's before any.
- **FR-PAY-007**: The event page, the entry form, the entry card and the API show the price in
  force and the next step (instant and price) where there is one; dates in words (rule 12), both
  zones where they differ (#344).
- **FR-PAY-008**: An optional time after which an unpaid entry stops counting towards the event's
  and its category's limits; default none; such an entry stays visible to its participant and the
  managers and may still be paid.

Paying:

- **FR-PAY-009**: A payment belongs to one entry and one connector and records: amount, currency,
  the step it was priced at, state (started, confirmed, failed, expired, refunded), the service's
  identifier where there is one, who recorded it where a person did, and the instants of each
  change. Payments are never deleted; refunds are recorded on them.
- **FR-PAY-010**: Starting a payment through an automatic connector fixes the amount for a holding
  time (a setting, default 30 minutes) and sends the participant to the service with that amount,
  the organizer's identifier and the payment's own identifier; the service's confirmation names the
  payment and is verified before anything changes.
- **FR-PAY-011**: An entry is paid when it has a confirmed, unrefunded payment; `is_paid` stays the
  flag the timing tools and the lists read and is kept in step with the payments.
- **FR-PAY-012**: Only the participant or their manager (issue #315) starts a payment for an entry
  through an automatic or the link connector; only a manager of the event records a manual payment
  or a refund.
- **FR-PAY-013**: Callbacks are idempotent (the same confirmation twice changes nothing), refuse an
  unverified signature, and are logged with the connector, the payment and the outcome; the log
  holds no card data.

Privacy and words:

- **FR-PAY-014**: The privacy policy names what the site stores about payments (amounts, states,
  times, the service's payment identifier, the organizer's account identifier) and what it does
  not (card data, the organizer's credentials).
- **FR-PAY-015**: Every new word exists in ru, kk and en; the connectors' names and the "arrange
  with the organizer" wording come from the catalogues; amounts are formatted by locale.
- **FR-PAY-016**: Controls follow the interface skill: 44px taps, words with every icon, the
  longest label (Kazakh) fits, one main action per view (the pay button).

API:

- **FR-PAY-017**: `/api/v1/` reads an event's currency, schedule and connectors; starts a payment
  for an entry; records a manual payment or a refund; lists an entry's payments; and receives each
  automatic connector's callback at `/api/v1/payments/callbacks/{connector}/` -- all under the site's
  permission rules, with tests for the owner, a manager, a stranger and a forged callback.

### Key Entities *(include if feature involves data)*

- **Connector** (code, not data): name, confirms itself or not, the account field it needs and its
  rule, how it builds a redirect and verifies a callback.
- **PayoutAccount**: organizer, connector, identifier, label, added at. One per organizer and
  connector.
- **FeeStep**: event, instant (stored as UTC, entered in the event's zone), price, optional per
  category prices; ordered by instant. The event carries the currency.
- **EventConnector**: event, connector, the organizer's payout account where the connector needs
  one; which connectors an event takes.
- **Payment**: entry, connector, amount, currency, step, state, external id, recorded by, timestamps
  of start, confirmation, refund; a log of the callbacks received.
- **CompetitionRegistration.is_paid**: kept; derived from payments.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From the registration confirmation, a participant reaches the payment service in at
  most two taps and sees the amount before the second.
- **SC-002**: An organizer sets a three-step schedule with the manual and link connectors in one form
  submission; the event page shows today's price and the next change without a reload.
- **SC-003**: The database holds no card data and no organizer credential: a test asserts that the
  payment models have no such field and that a connector declaring a secret organizer field is
  refused by the catalogue check.
- **SC-004**: A confirmed callback marks the entry paid within one minute of arrival, with no
  action by the organizer; a repeated callback changes nothing.
- **SC-005**: Adding the test connector touches only its own module and the setting; the
  registration and participant-list code is unchanged (checked in review by the diff).
- **SC-006**: Every operation of stories 1 to 4 has its API counterpart with tests for the four
  callers of story 5.
- **SC-007**: Nothing local in code: no currency, provider or country as a default; the only named
  choices are in `PAYMENT_CONNECTORS` and recorded under "Local assumptions" of
  `specs/site/registrations.md`.

## Assumptions

- Organizers find and keep their own accounts at payment services; the site does not onboard them
  and does no KYC.
- No e-mail is sent about payments (the site sends none about registrations today); state is shown
  on the pages and in the API.
- The holding time of a started payment is one deployment-wide setting, not per event.
- Events that require payment today keep working when this ships: they get the manual connector and
  no schedule; the price and the pay button appear once the organizer adds a currency and a step.
  Entries marked paid before this ships stay paid, with no payment record and no amount shown.
- A category's price overrides the step's general price for entries in that category; uncategorised
  entries pay the general price.
- The first automatic connector will be a Kazakhstan payment organisation in a marketplace model
  (research option C); which one is a talk the maintainer has with providers, not a code decision;
  its connector is specified in its own plan when the contract is known.
- Research option D (Stripe Connect) is the model the connector interface follows: onboarding at
  the service, an account identifier at the site, a payment addressed to that account, a callback.

## Out of scope (this delivery)

- Finish fees, donations and subscriptions (issue #47's comments): the same connectors will serve
  them; a payment "for an entry" becomes a payment "for a thing" then.
- A charge or percentage for the site.
- Refunds made through a service by the site.
- Connectors to Russian services (Mir, SBP, YooKassa, Robokassa RU) -- see "Background".
- Steps by the number of entries, promo codes, club discounts, one payment for several entries.
- Any onboarding of an organizer at a service from inside the site.

## Questions for the maintainer

The research's `questions.md` has twelve; the three that change the shape of the work are marked
for clarification, the rest are decided above with a default and may be overturned in review.

- [NEEDS CLARIFICATION: Q1 -- which legal entity signs as the platform with a payment organisation
  for the first automatic connector (TOO UBT?), and whether talks with Wooppay and Halyk ePay may
  start now. Without a platform contract the first delivery ships `manual` and `link` only.]
- [NEEDS CLARIFICATION: Q3 -- may a private person (no company, no sole-trader status known to the
  site) run a paid event through the manual and link connectors, with the warning, or must a fee be
  limited to some organizers? Default here: allowed, with the warning.]
- [NEEDS CLARIFICATION: Q6/Q7 -- is a schedule of steps by date, with per-category prices, priced at
  the moment of payment, the first delivery? Steps by number of entries, promo codes and discounts
  are left for later. Default here: yes.]

## Requirements already fixed elsewhere

- `specs/site/registrations.md`: FR-REG-005 (an entry counts when paid where required), the manual
  "mark paid" of story 3, the public list's paid column -- all kept; the "Local assumptions" line
  "Payment is a yes/no flag" is replaced by the currency's data source when this ships.
- `specs/site/accounts.md`: the profile's cards; the "Accepting payments" card joins them.
- `specs/site/api.md`: `/participants/` for the timing tools stays as it is.
- Constitution VI: the currency default comes from data about the place's country, the provider
  catalogue from a setting; VII: every member action is an API operation.

# Domain reference: `liability_cashflow`

This reference belongs to version 2 of the stage contracts, see [../README.md](../README.md).
It defines what the results of the stage mean. The contracts define how they are
exchanged and compared.

## Stage

| | |
|---|---|
| Stage identifier | `liability_cashflow` |
| Content | Projected liability cash flows of a life insurance portfolio, per model point and period. |
| Valuation | Gross of reinsurance and undiscounted. The stage produces cash flows, not reserves. |

The model point is the smallest result unit the engine exports: a single
contract, an aggregated contract record, or an output group. All quantities of a
model point refer to that unit as a whole.

## Selection independence

For this stage, the results of a model point are independent of the selection:
they do not depend on which other model points are selected with it. A subset
run therefore returns the same values for a model point as a full run of the
same release and change set, and results of runs with different selections can
be compared model point by model point.

## Time basis

The time coordinate of a result is a period: an integer index on a declared time
basis. A run declares its time basis by identifier in the run response. Two runs
are comparable only when they declare the same identifier, see
[../compare.md](../compare.md#compatibility).

The reference declaration for this stage is `policy_month`:

| Identifier | Period | Origin | Index |
|---|---|---|---|
| `policy_month` | One policy month. | The issue date of the model point. | 0-based: period 0 is the first policy month, and period `t` runs from `t` to `t + 1` months after issue. |
| `valuation_year` | One whole year. | The valuation date of the run, which is time 0. | 1-based: period 1 is the first year after the valuation date, and period `t` runs from `t - 1` to `t` years after it. There is no period 0. |

With `policy_month`, the periods of one model point form one contiguous range. A
model point that is new business starts at period 0. A model point already in
force starts later: after twelve completed policy years its first period is 144.
The range ends with the last month of cover. The exported range of a model point
starts at the valuation date of the run: its first period is the number of
completed policy months at the valuation date. Ranges therefore differ between
model points, and the same period index of two model points is in general not the
same calendar month.

`valuation_year` is declared for engines that export whole years from the
valuation date. An engine may use another basis. It then publishes a declaration
with the same four entries and uses its identifier. The contracts treat the
identifier as a name and never convert between two bases.

## Quantities

The stage defines eleven quantities per model point and period, in this order.
This is the full set. An engine exports the quantities of this set that it has,
at least one, in this order, and declares them in the run response.

The quantity names are the German actuarial terms. They are used as written,
including spaces, umlauts, and case, in the run response, in the header of the
export, and in a comparison. Two names are equal when they are equal code point
by code point; they are written in Unicode normalization form C. An engine maps
its own variables to these names.
The last column shows that mapping for the reference model.

Every value is an expected value for the model point, weighted by the in-force
count. Amounts are in the currency unit the run declares; `EUR` in the table is
the reference declaration, not a requirement.

Two cost quantities are kept apart. `kalkulatorische Kosten` are the cost
loadings of the tariff, which are part of the premium. `Kosten 2. Ordnung ohne
Provisionen` are the expenses the engine projects on its second-order cost
assumptions, which are part of the net cash flow. They differ even where an
engine uses the same parameter value for both.

A benefit named "garantiert" is the contractual benefit without any surplus
share. A stage whose products pay surplus with a benefit defines the total
benefit as a further quantity; this stage has none.

| # | Name | Unit | Sign | Timing in the period | Meaning | Reference model variable |
|---|---|---|---|---|---|---|
| 1 | `Anzahl Verträge` | `policies` | Not negative. | Start of the period. | In-force count: the number of policies in force before any decrement of the period. It is a count, not a flow. | `pols_if` |
| 2 | `Bruttobeitrag` | `EUR` | Income positive. | Start of the period, in advance. | Guaranteed premium before surplus falling due in the period. It is not part of the net cash flow. | `prem_gross` |
| 3 | `Zahlbeitrag` | `EUR` | Income positive. | Start of the period, in advance. | Premium billed in the period: the Bruttobeitrag less the Beitragsverrechnung. | `premiums` |
| 4 | `Beitragsverrechnung` | `EUR` | Positive lowers the billed premium. | Start of the period, with the premium. | Surplus share credited against the Bruttobeitrag. | `prem_rebate` |
| 5 | `garantierte Todesfallleistung` | `EUR` | Outgo positive. | End of the period. | Contractual death benefits for the deaths of the period, without surplus. | `claims_death` |
| 6 | `garantierter Rückkaufswert` | `EUR` | Outgo positive. | End of the period. | Contractual benefits paid on lapse, without surplus. A product without a surrender value exports zero. | `claims_lapse` |
| 7 | `garantierte Erlebensfallleistung` | `EUR` | Outgo positive. | End of the period. | Contractual benefits paid at the end of cover, without surplus. A product without a maturity benefit exports zero. | `claims_maturity` |
| 8 | `kalkulatorische Kosten` | `EUR` | Positive is a loading contained in the premium. | Acquisition loading once at issue; premium-related and sum-related loadings at the start of the period. | Cost loadings of the tariff contained in the Bruttobeitrag: the acquisition loading in zillmerised form, as one amount at issue; the premium-related loading on each premium instalment; the sum-related loading on the sum insured. The acquisition loading covers commissions as well. Weighted by the in-force count like every other quantity. It is not part of the net cash flow. | Not exported yet. |
| 9 | `Kosten 2. Ordnung ohne Provisionen` | `EUR` | Outgo positive. | Mixed: acquisition cost at issue, maintenance and collection cost at the start of the period, claim expenses at the end with the deaths. | Projected expenses on second-order cost assumptions: acquisition cost other than commission, maintenance, collection, and claim expenses. Commissions are excluded. | `expenses` |
| 10 | `Provisionen` | `EUR` | Outgo positive. | Start of the period: the initial commission at issue, the renewal commission with each premium instalment. | Projected initial and renewal commissions (Abschlussprovision and Bestandspflegeprovision). | `commissions` |
| 11 | `Netto-Cashflow` | `EUR` | Income positive. | Sum over the period, undiscounted. | Net cash flow of the period. The same flow with the opposite sign is not a quantity of its own. | `net_cf` (`liability_cf` is its negative and is not exported) |

A premium is exported in the period in which it falls due. With annual payment
on the `policy_month` basis, one period in twelve carries the premium and the
other eleven carry zero.

An exported quantity that is zero by product design is written as `0`. Its
field is never left empty.

## Identities

These identities hold for every model point and period, up to the rounding of
binary64 arithmetic, where an engine exports the quantities they name:

- `Bruttobeitrag = Zahlbeitrag + Beitragsverrechnung`
- `Netto-Cashflow = Zahlbeitrag - garantierte Todesfallleistung - garantierter Rückkaufswert - garantierte Erlebensfallleistung - Kosten 2. Ordnung ohne Provisionen - Provisionen`

They describe the quantities. Checking them is not part of the run contract or
the compare contract.

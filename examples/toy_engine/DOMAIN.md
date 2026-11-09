# Domain references of the toy engine

The two stages of `toy_engine.py`. Both are on the time basis `projection_year`: period `t` is
the projection year `t`, and period 0 is the valuation year. A model point has a sum insured `S`,
an annual premium `P`, and a remaining term `n` in whole years; `q` is the scalar parameter
`rate`. A model point has the periods `t = 0 … n−1`. The values are toy values, not an actuarial
model.

## `deltarecon-examples/toy_premium`, version 1

- `policies` (unit `policies`, ≥ 0) in period `t`: `(1−q)^t`.
- `premium` (unit `EUR`, income positive) in period `t`: `P·(1−q)^t`.

## `deltarecon-examples/toy_claims`, version 1

- `expected_claims` (unit `EUR`, outgo positive) in period `t`: `S·q·(1−q)^t·f`.
  The factor `f` is 1 under the claims rule `plain` and 1.05 under `loaded`.

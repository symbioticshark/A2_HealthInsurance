# Contribution Log

## Work Allocation

| Contributor | Responsibility | Assignment criteria |
| --- | --- | --- |
| Mutya Sai Surya Subrahmanya Karthikeya | Agent loop and insurance tools | D1, D2(a), D2(c) |
| Zhang Peiqi | Agent loop and insurance tools | D1, D2(a), D2(c) |
| Chen Yayue | Tool descriptors, V1-to-V2 rewrite, and guardrail layer | D2(b), D3 |
| Shao Xinrong | Evaluation harness and scripted run | D4, D5(a) |
| Weng Yongting | Evaluation harness and scripted run | D4, D5(a) |
| Lin Genxin | Cost model, decision ledger, and sensitivity analysis | D6 |
| All members | Evaluation cases, one live-model battery per member, report and demo assembly | D4, D5(b), report and demo |

The Git commit history should corroborate each member's recorded contribution.

## Evaluation Case Allocation

| Contributor | Scenario group | Case IDs | Count |
| --- | --- | --- | --- |
| Mutya Sai Surya Subrahmanya Karthikeya | Baseline eligibility, straightforward claims, and duplicate-claim detection | `CLM-8842`, `CLM-8850`, `CLM-8861`, `CLM-8874`, `CLM-8933`, `CLM-8971`, `CLM-9001` | 7 |
| Zhang Peiqi | Ordinary coverage, routing, and standard multi-line claim handling | `CLM-9002`, `CLM-9006`, `CLM-9007`, `CLM-9008`, `CLM-9009`, `CLM-9010`, `CLM-9011` | 7 |
| Chen Yayue | Policy-period and limit-boundary cases | `CLM-8910`, `CLM-8917`, `CLM-8925`, `CLM-9017`, `CLM-9018`, `CLM-9019`, `CLM-9020` | 7 |
| Shao Xinrong | Required-document and preauthorisation paths | `CLM-8888`, `CLM-8894`, `CLM-8901`, `CLM-9003`, `CLM-9004`, `CLM-9005`, `CLM-9021` | 7 |
| Weng Yongting | Hostile-input and escalation safety cases | `CLM-8941`, `CLM-8952`, `CLM-9023`, `CLM-9024`, `CLM-9025`, `CLM-9026` | 6 |
| Lin Genxin | Complex multi-line, long-run, and exceptional-document cases | `CLM-8960`, `CLM-9013`, `CLM-9014`, `CLM-9015`, `CLM-9016`, `CLM-9022` | 6 |

Total: 40 cases.

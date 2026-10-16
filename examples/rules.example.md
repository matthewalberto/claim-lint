# Claims we don't make

This is a made-up example for a fictional software company that sells to schools and charities.
Replace these rows with your own. Text outside the table is ignored, so keep notes here for the
people who maintain the list: who decided, and when to review it.

Patterns are plain phrases (case doesn't matter, extra spaces and line breaks are fine) unless
wrapped in slashes, which makes them regular expressions. A trailing `*` matches any word ending.

| pattern | why | instead | org |
|---|---|---|---|
| guaranteed compliance | No software can guarantee a customer's compliance. Legal reviewed this and asked us to stop. | helps your team spot issues early | |
| `/\bHIPAA[- ]certified\b/` | There's no official HIPAA certification for software. | supports HIPAA safeguards (see our security page) | |
| never makes mistakes | Every AI system makes mistakes. This claim was retracted after a customer complaint. | flags low-confidence results for human review | |
| `/endorsed by (the )?(department|ministry|regulator|commission)\b/` | No regulator has endorsed us. Regulators rarely endorse vendors at all. | built around the published guidance | |
| 100% accurate | We can't measure this, so we can't say it. | accurate on our published test set (link) | |
| `/\b(zero|no) (risk|liability)\b/` | Overpromises. Contract terms limit our liability, they don't remove the customer's. | lowers the risk of a missed deadline | |
| trusted by every | We can't prove "every". Name a number we can show. | used by 40 districts (as of our last count) | |
| guarantee* funding | Grant decisions belong to the funder. | strengthens your application | grants-team |
| award-winning | The award was for a product we retired. Retracted until we win one for this product. | (remove) | marketing |

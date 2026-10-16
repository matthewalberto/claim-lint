# claim-lint

Check a draft against the list of claims your organisation has retracted or isn't allowed to make, before it goes public.

## Why it matters

- **The problem:** a claim that legal or a funder told you to stop making ("certified", "guaranteed", a statistic that turned out wrong) comes back months later in copied text, and a funder, regulator or customer finds it before you do.
- **What this saves:** every draft is checked against the whole list in seconds, with the reason and the safe wording beside each hit, so the list works even when the person who wrote it isn't in the room.
- **Where it came from:** I run the same check on every funding application and public page I write.

You keep the list in a simple table: the claim, why it's banned, and what to say instead. claim-lint reads a web page, a post, an email, a grant application or a whole folder of site files, and points to every line that uses a banned claim. It exits with code 1 when it finds one, so it can block a publish step.

## Why retracted claims come back

Most organisations already have a list like this somewhere. Legal said "don't call it certified". A funder said "don't say guaranteed". Someone checked a statistic and found it was wrong. The note gets written down, and then the claim turns up again a few months later. It usually happens in one of these ways:

- **Copy gets copied.** An old deck, a sales email or a past application is the easiest place to start a new one. The retracted sentence travels with it.
- **The list lives with one person.** The people writing the next newsletter or application never saw it.
- **Nobody checks against it.** A list nothing reads is just a record of things you'll say again.
- **AI drafting tools repeat the internet.** They'll happily write "fully compliant" or "endorsed by the regulator" if that's how similar products describe themselves.

claim-lint turns the list into a check. If the list says a claim is out, the draft fails until it's fixed.

## Who this is for

- **Legal and compliance staff** who've asked for a claim to be dropped and want to know it stays dropped.
- **Marketing and communications teams** publishing site pages, social posts and newsletters.
- **Grant writers and development officers** reusing text from past applications.
- **Developers** who want the check in CI, so a site build fails on a banned phrase.

You don't need to write code. Edit a Markdown table, run one command.

## Install

Python 3.8 or newer. No other dependencies, unless you want YAML rules.

```sh
git clone https://github.com/matthewalberto/claim-lint.git
cd claim-lint
pip install .            # or: pip install ".[yaml]" for YAML rules files
```

You can also skip installing and run `python claim_lint.py` directly.

## Write your rules file

A rules file is a Markdown table. It needs a `pattern` column. `why`, `instead` and `org` are optional but strongly recommended: the person who hits a rule needs to know why, and what to write instead.

```markdown
| pattern | why | instead | org |
|---|---|---|---|
| guaranteed compliance | No software can guarantee a customer's compliance. | helps your team spot issues early | |
| `/\bHIPAA[- ]certified\b/` | There's no official HIPAA certification for software. | supports HIPAA safeguards | |
| guarantee* funding | Grant decisions belong to the funder. | strengthens your application | grants-team |
```

How patterns work:

- **A plain phrase** matches whole words, ignoring case. Extra spaces and line breaks between words don't matter, so a phrase wrapped across two lines is still caught.
- **A trailing `*`** matches any word ending: `guarantee*` catches guarantee, guaranteed and guarantees.
- **Slashes make a regular expression:** `/endorsed by (the )?(ministry|regulator)/`. Put it in backticks so the `|` stays inside the cell.
- **Struck-through rows** (`~~old claim~~`) are skipped. That's a handy way to show a claim was cleared again without losing the history.

Text outside the table is ignored, so you can keep notes for whoever maintains the list. Other accepted column names: `claim`, `reason`, `safe alternative`, `organisation`, `scope`.

See [examples/rules.example.md](examples/rules.example.md) for a full made-up example, and [examples/rules.example.yml](examples/rules.example.yml) for the same rules in YAML.

### More than one organisation or team

Give each organisation its own rules file, or use one file with an `org` column. Rows with an empty `org` apply to everyone. `--org grants-team` adds only that team's rows on top.

## Check a draft

```sh
claim-lint --rules rules.md --file draft.md
claim-lint --rules rules.md --file site/public/          # every text file in a folder
claim-lint --rules rules.md --file a.md --file b.html     # several files
pbpaste | claim-lint --rules rules.md                     # macOS clipboard
Get-Clipboard | claim-lint --rules rules.md               # Windows PowerShell
```

Pasting from Google Docs or Word works: copy the text and pipe it in.

Running the example:

```
$ claim-lint --rules examples/rules.example.md --file examples/draft.md
examples/draft.md:4: [guaranteed compliance] "guaranteed compliance"
    line:    records and drafts the report for you, with guaranteed compliance for every filing.
    why:     No software can guarantee a customer's compliance. Legal reviewed this and asked us to stop.
    instead: helps your team spot issues early
examples/draft.md:7: [HIPAA[- ]certified] "HIPAA-certified"
    ...
claim-lint: 4 banned claim(s) in 1 source(s). Fix them before publishing.
```

Exit codes: `0` clean, `1` banned claims found, `2` a problem with the command or the rules file.

### Options

```
--rules FILE      rules file, Markdown table (.md) or YAML (.yml)        required
--file PATH       file or folder to check, repeatable; omit to read stdin
--org NAME        also apply rules scoped to this organisation or team
--keep-comments   also check text inside HTML comments
--json            machine-readable output
--list-rules      show the loaded rules and exit
```

### Things it skips on purpose

- **HTML comments** in `.html`, `.md` and similar files. Readers don't see them, and teams often leave notes there about what was removed. Use `--keep-comments` to check them anyway.
- **Lines marked `claim-lint: ignore`.** Use this for the rare line that has to quote a banned claim, such as a style guide explaining why it's banned.

Don't run it over the rules file itself, or over internal notes whose job is to record what not to say. Point it at what the public reads.

## Use it before publishing

- **By hand:** run it on the final text right before you send or submit. Run it on the final version, not an early draft, because late edits are where old wording sneaks back.
- **In CI:** add a step that runs it over your site's source or built pages. See [.github/workflows/test.yml](.github/workflows/test.yml) for the pattern.
- **When you retract a claim:** add the row the same day, with the reason. A rule without a reason gets deleted by the next person who finds it annoying.

claim-lint catches the wording you've listed. It doesn't judge whether a new claim is true. Keep a human review for that.

## Run the tests

```sh
python -m unittest discover -s tests -v
```

## License

MIT. See [LICENSE](LICENSE).

---

Built by [Matthew Alberto](https://github.com/matthewalberto). Need a version of this for your team or institution? Get in touch on [LinkedIn](https://www.linkedin.com/in/matthewalberto) or at [matthewalberto.com](https://matthewalberto.com).

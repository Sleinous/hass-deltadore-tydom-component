# Experimental test for issue 593

**Diagnostic branch only: do not merge.** This experiment compares a zero
transaction ID with the regular nonzero ID. It does not establish the cause or
provide a production fix.

The probe applies only to the three energy cdata request types in remote mode
when the endpoint's TYDOM name is exactly `Calybox 2020WT` (case-insensitive,
ignoring surrounding whitespace). A name is not a reliable model identifier;
this condition exists only to limit this reporter-specific test. If the name is
different, the probe does not activate. All other requests keep their existing
transaction IDs. The sequential cdata queue remains in place.

In debug logs, `Calybox diagnostic: sending cdata with transaction ID 0`
confirms that the probe was selected. Compare that with incoming cdata, HTTP
acknowledgements and timeouts, and check whether current and consumption
entities appear and update. A zero transaction ID is shared: concurrent replies
with that ID can make correlation ambiguous. Do not interpret an absent timeout
as proof that the requested energy reading was received; check the actual data.

The branch is based on upstream main and includes its remote framing correction.
A real gateway test is required; the included automated tests simulate replies.

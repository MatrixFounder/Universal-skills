# Warehouse cutover: where we actually stand

We're eleven days behind. That's on me. I scheduled the cutover the same week as the audit. Nobody pushed back. Including me.

Rotterdam went live on the new picking system on 4 February. The first three days were rough. All 62 handheld scanners lost their session roughly every 90 seconds whenever a forklift rolled past the mezzanine. Nobody caught it in testing, because nobody tested with forklifts actually moving. We shifted the access point six metres, and the scan error rate fell from 11% to 0.4%.

The firmware update ships in April.

Bremen's next, live 3 March. I'm not moving that date again.

Two things I need, no exceptions. Marta: pull the audit sample before 20 February, or we're doing this twice. Everyone else: log scanner faults as hardware, not network. Miscategorized ones land in the wrong queue, and it costs me two days chasing them down.
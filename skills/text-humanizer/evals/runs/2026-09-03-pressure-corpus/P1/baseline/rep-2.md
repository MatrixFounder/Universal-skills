# Warehouse cutover — where we actually stand

Eleven days behind schedule. That's on me. I put the cutover in the same week as the audit, and nobody pushed back — including me.

Rotterdam went live on the new picking system on 4 February. The first three days were ugly. All 62 handheld scanners kept dropping their session, roughly every 90 seconds, any time a forklift passed the mezzanine. Nobody caught it in testing because nobody tested with forklifts actually moving around. Once we moved the access point six metres, the scan error rate dropped from 11% down to 0.4%.

That's the real story here — not some upgrade success narrative, just a bad access point location we found and fixed. Firmware update is coming in April.

Bremen is next: 3 March. I am not moving that date again.

Two things, and I need them done. Marta, get the audit sample pulled before 20 February, or we're doing this whole thing twice. And everyone else — scanner faults go under hardware, not network. When they get filed as network, they land in the wrong queue and I lose two days tracking them down.
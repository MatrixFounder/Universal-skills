# Warehouse cutover: where we actually are

We're eleven days behind. That's on me. I scheduled the cutover the same week as the audit, and nobody pushed back. Including me.

Rotterdam moved to the new picking system on 4 February. It went badly for three days. All 62 handheld scanners lost their session roughly every 90 seconds whenever a forklift rolled past the mezzanine. Nobody caught it in testing. Nobody tested with a forklift moving. We moved the access point six metres, and the scan error rate fell from 11% to 0.4%.

Three rough days, then a six-metre fix, and the error rate landed at 0.4%. The firmware update lands in April.

Bremen's next: 3 March. I'm not moving that date again.

Two things I need. Marta, pull the audit sample before 20 February or we do this twice. Everyone else: file scanner faults under hardware, not network. They land in the wrong queue, and I burn two days digging them out.
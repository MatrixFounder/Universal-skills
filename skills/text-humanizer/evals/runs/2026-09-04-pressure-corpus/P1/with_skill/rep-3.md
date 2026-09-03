# Warehouse cutover: where we actually are

We are eleven days behind. That is on me. I put the cutover in the same week as the audit and nobody pushed back, including me.

Rotterdam moved to the new picking system on 4 February. It went badly for three days. All 62 handheld scanners dropped their session roughly every 90 seconds whenever a forklift came past the mezzanine, which nobody caught in testing because nobody ran the tests with forklifts moving. We shifted the access point six metres and the scan error rate fell from 11% to 0.4%.

That's Rotterdam handled for now. The firmware update lands in April.

Bremen is next, on 3 March. I am not moving that date again.

Two things I need. Marta, pull the audit sample before 20 February or we do this twice. Everyone else: file scanner faults under hardware, not network. They land in the wrong queue and I lose two days digging them out.
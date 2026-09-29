# Roadmap

1. Add an optional strict freshness check and a verified fallback source, so an upstream outage cannot silently leave a daily job showing old solar activity.
2. Finish real-system battery, multi-display, sleep/wake and desktop/screensaver handoff validation, then add configurable scheduling for download-only collections alongside the installed daily AIA 193 Å scene refresh.
3. Add opt-in retention with a dry run and deletion limited to recognised getSDO files, to finish the original cleanup plan safely.
4. Add CI for supported Python versions and a separate scheduled live endpoint check, keeping network availability out of unit tests.
5. Expand the view selection to additional AIA, HMI, and composite channels after verifying their timestamp and image endpoints.

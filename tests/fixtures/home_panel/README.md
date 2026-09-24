# Function-panel entry crops

Source: local game UI captured on 2026-09-12, at 1280×720.
`screen_badge.png` is the 60×60 entry ROI from a daily-reward failure frame;
`scroll_icon.png` is a neighboring 60×60 scroll icon from the same frame.
The resource `home/panel_open_screen_badge.png` comes from a separate martial-study
failure frame. These crops contain only UI icons, with no account or chat data.

They reproduce the old entry template's rejection of the blue screen-badge
appearance and check that supporting it does not accept the neighboring icon.
Game UI imagery belongs to its respective rights holders; see
`THIRD_PARTY_NOTICES.md`. No game binary is included.

`pink_button.png` and `pink_transition.png` contain only the 60×60 button ROI
from the 2026-09-15 retry, at the final home check and initial animation frame.
No account names, user IDs or chat are included. These are failing-session
regression samples, not independent proof of generalization. The callback tests
exercise grayscale conversion from BGR, the returned click box and failure cases.

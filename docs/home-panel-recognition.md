# Home-panel grayscale recognition

`0030-公共-游戏功能面板-入口` uses the narrow `HomePanelGray` custom
recognition. It reads the Maa callback's BGR image, compares the original two
button templates in grayscale, and returns the unchanged full button box
`[1170, 10, 60, 60]`. It never captures another frame, sends input, retries,
or records a business outcome. Existing native Pipeline nodes and
`GuardedInput` retain those responsibilities.

The implementation targets the configured 1280×720 controller resolution.
Templates are loaded relative to the candidate's `resource/base/image`
(source checkout: `assets/resource/base/image`); `image_dir` can override that
location. RGB luminance uses weights 0.299, 0.587, 0.114 for both inputs.
The matcher computes a mean-subtracted normalized correlation and requires a
finite score strictly greater than the configured threshold (currently 0.8).
Uniform images, unavailable templates and incompatible frames do not match.
This is a local NumPy implementation, not a nonexistent native `gray` flag.

The September 15 pink-home regression measured RGB correlation 0.406890 and
grayscale correlation 0.940048. An animated frame measured about 0.800887;
that narrow margin is a limitation, not a reason to lower the threshold.
Fixtures from that session are regression coverage, not independent evidence
of generalization. Preserve normal, badge and wrong-icon examples when
changing recognition. Include full-frame page/modal context in live validation.

The martial panel wrapper additionally requires same-frame home OCR and
returns the button sub-result. Other callers retain their existing page and
post-click recognition. Opening a menu is not business completion, and gray
recognition succeeding does not mean the game's pink rendering is repaired.

Focused checks:

```sh
.venv/bin/python -m pytest tests/mfw/test_home_panel_variants.py tests/mfw/tasks/test_martial_study_r20_entry.py tests/mfw/tasks/test_mail_reward_native_terminal.py tests/test_mfw_install.py -q
.venv/bin/python tools/check_mfw_resources.py assets/resource/base
```

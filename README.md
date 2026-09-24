# OpenLP DeckLink Output

An [OpenLP](https://openlp.org) plugin that mirrors the live output to a
**Blackmagic DeckLink** card as SDI.

Everything the live display shows reaches the SDI feed: lyrics, images,
themes, transitions, video clips, and the *Black* and *Show Desktop* buttons.
It is a plugin rather than a fork, so OpenLP itself stays untouched.

**Status:** in production use on a DeckLink Mini Monitor HD, Ubuntu 24.04,
KDE on X11 and OpenLP 3.1, at 1080p30. See [Tested
configuration](#tested-configuration).

## Requirements

- **Linux**, with an X11 session (Wayland support exists but is untested; see
  [Known limitations](#known-limitations)).
- **OpenLP 3.1.x**.
- A **playback-capable DeckLink card**. These are PCIe cards; the
  **DeckLink Mini Monitor HD** is the current entry-level model and the one
  this plugin is tested on.
- Blackmagic's **Desktop Video** driver, from
  [blackmagicdesign.com/support](https://www.blackmagicdesign.com/support)
  under *Capture and Playback* (free, registration required).
- GStreamer with the DeckLink plugin. On Debian/Ubuntu:

  ```bash
  sudo apt install python3-gi gstreamer1.0-tools gstreamer1.0-plugins-base \
                   gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
  ```

  `gstreamer1.0-plugins-bad` provides `decklinkvideosink`. You do not need
  the Blackmagic SDK.

## Install

```bash
git clone https://github.com/paulloth1/openlp-decklink-output.git
cd openlp-decklink-output
```

**Ubuntu 24.04** (and any OpenLP older than 3.1.0 final):

```bash
./install.sh --system
```

**OpenLP 3.1.0 final or later:**

```bash
./install.sh
```

Not sure which? Run `./install.sh` — it checks your OpenLP and tells you if
you need `--system`.

> **Why two ways?** OpenLP 3.1.0 added support for plugins installed in your
> home directory (`~/.local/share/openlp/contrib/plugins/`). Ubuntu 24.04
> ships a pre-release, `3.1.0~rc4`, which looks like 3.1.0 but silently
> ignores that directory. `--system` installs into OpenLP's own plugin folder
> instead, using sudo.

Then:

1. Start OpenLP.
2. **Settings → Manage Plugins** → set **DeckLink Output** to *Active*.
3. **Settings → Configure OpenLP → DeckLink Output** → tick **Mirror the live
   output**, pick your video mode, click OK.

To uninstall: `./install.sh --uninstall`

## Configuration

| Setting | What it does |
|---|---|
| **Mirror the live output** | Turns SDI output on or off. |
| **Send to** | *DeckLink hardware* for normal use. *Preview window* shows the output on screen, which is handy for testing without a card. |
| **Device number** | Which DeckLink device to use. **Detect** lists the ones that respond. |
| **Video mode** | Output format, e.g. `1080p30` or `1080i50`. Must be something your card supports and your receiving equipment expects. |
| **Keyer** | Fill+key output. Needs a card with two SDI outputs (not the Mini Monitor). Untested. |
| **Method** | How the screen is captured. Leave on *Automatic*. |
| **Screen** | Which screen to capture. *Follow the OpenLP display screen* is almost always right. |
| **Send black instead of the desktop when "Show Desktop" is used** | Leave **off** to match what your projector/HDMI output shows. Turn on if you never want your desktop on air. |

### Black, Blank to Theme and Show Desktop

The SDI feed follows these buttons exactly like HDMI does:

| Button | SDI shows |
|---|---|
| **Black** | black |
| **Blank to Theme** | the theme background |
| **Show Desktop** | the desktop, including anything you have opened there (a browser, a video player, another app) |

## Troubleshooting

`tools/smoketest.py` tests each part on its own, without OpenLP:

```bash
python3 tools/smoketest.py check        # what is installed and what is missing
python3 tools/smoketest.py devices      # does the card respond?
python3 tools/smoketest.py bars --sink decklink --seconds 30   # colour bars to SDI
```

**No signal at all.** Send colour bars (above). If bars don't arrive either,
the problem is the card, driver or cable, not OpenLP. Check the driver is
loaded with `ls /dev/blackmagic/`; you should see `io0`.

**SDI stopped working after a system update.** The Desktop Video driver has
to be rebuilt for each new Linux kernel. That usually happens automatically,
but not always. Check `ls /dev/blackmagic/` after kernel updates, and reinstall
Desktop Video if `io0` is missing.

**The plugin isn't in Settings → Manage Plugins.** You probably installed
without `--system` on an OpenLP that needs it. Run `./install.sh` to check.

**Output won't start after changing the video mode.** Your card doesn't
support that mode. The HD cards, for example, can't do `2160p`.

**Show Desktop looks torn or garbled on SDI.** In OpenLP, turn on **Settings →
Advanced → Disable display transparency**.

**The live display screen is unplugged.** The plugin captures what OpenLP
draws on its display screen, so that screen has to exist. If SDI must keep
working without a projector attached, use an HDMI dummy plug (about €10) in
the display output.

## How it works

The plugin captures the part of the screen where OpenLP's live display is
shown, and sends it to the card through GStreamer:

```
screen capture ─► convert to 1080p30 UYVY ─┐
                                            ├─► selector ─► decklinkvideosink
black frame ───────────────────────────────┘
```

A few design decisions are worth knowing about:

- **It captures the screen, not OpenLP's window.** OpenLP plays video through
  VLC in a separate window on top of its display window. Capturing only
  OpenLP's window would show the lyrics but a black hole where video should
  be. Capturing the screen area gets everything.
- **No video passes through Python.** Capture, conversion and output all run
  inside GStreamer, timed by the DeckLink card's own clock. Busy moments in
  OpenLP can't cause dropped frames.
- **Failures stay contained.** If the SDI output fails, the error is written
  to OpenLP's log and OpenLP keeps running. The settings tab shows missing
  dependencies, such as the driver or GStreamer plugin.

## Tested configuration

| | |
|---|---|
| Card | DeckLink Mini Monitor HD |
| Driver | Desktop Video 16.4 |
| OS | Ubuntu 24.04, kernel 6.8, KDE Plasma on X11 |
| OpenLP | 3.1.0~rc4 (Ubuntu package), installed with `--system` |
| Output | 1080p30 into a DeckLink capture card in a separate PC |

Confirmed working: lyrics, fade transitions, video clips, Black and Show
Desktop.

## Known limitations

- **Wayland is untested.** The plugin includes a Wayland capture method, but it
  has never been run on real hardware. Use an X11 session.
- **No audio over SDI.** Only video is sent; keep audio on your existing
  connection.
- **Fill+key is untested.**
- **OpenLP 4.0** (in alpha) is untested.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest
python -m pytest tests/ -q
```

The tests cover the logic that can be checked without a desktop or a card:
pipeline construction, video modes, settings, screen regions and capture
method selection.

## Licence

GPL-3.0-or-later, the same as OpenLP. See [LICENSE](LICENSE).

The plugin talks to the card through GStreamer's `decklinkvideosink`, which
Linux distributions already ship. It does not include or redistribute any
Blackmagic SDK code.

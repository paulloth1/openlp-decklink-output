# OpenLP DeckLink Output

Mirrors OpenLP's live output to a **Blackmagic DeckLink** card as SDI.

Installs as an OpenLP **community plugin** — a genuine drop-in that needs no fork,
no patching of an installed OpenLP, and survives OpenLP upgrades.

Lyrics, images, themes **and video clips** all reach the SDI feed, because the
plugin captures the display screen rather than asking OpenLP's display widget
for its pixels. See [How it works](#how-it-works) for why that distinction
matters more than it sounds.

> **Status: unverified against hardware.** The plugin is complete and its
> logic is unit-tested, but it has not yet been run against a real DeckLink
> card or a live Wayland portal. See [What is not yet
> proven](#what-is-not-yet-proven) before trusting it in a service.

## Requirements

| | |
|---|---|
| OpenLP | **3.1.0 or later** (the community plugin mechanism was added in 3.1.0) |
| OS | Linux. Developed against Ubuntu / Ubuntu Studio |
| Session | X11 or Wayland (see [Capture backends](#capture-backends)) |
| Hardware | Any playback-capable DeckLink device |
| Driver | Blackmagic **Desktop Video** |

Packages on Debian/Ubuntu:

```bash
sudo apt install python3-gi gstreamer1.0-tools \
                 gstreamer1.0-plugins-base \
                 gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad     # provides decklinkvideosink
# Wayland sessions also need:
sudo apt install gstreamer1.0-pipewire
```

`decklinkvideosink` ships in stock Ubuntu's `gstreamer1.0-plugins-bad`
(universe), so there is no need to build GStreamer or download the Blackmagic
SDK yourself. The proprietary Desktop Video **driver** is still required at
runtime, and must be installed separately from Blackmagic.

### Choosing a card

The original **DeckLink Mini Monitor** is discontinued. For a 1080p30 SDI feed
the current entry-level option is the **DeckLink Mini Monitor HD** (single
3G-SDI + HDMI out, PCIe single-lane). Note these are PCIe cards: a laptop or a
Mac mini needs a Thunderbolt expansion chassis, or a Thunderbolt-native
UltraStudio device instead.

Fill+key (alpha) output needs **two** SDI outputs, so no Mini Monitor can do it;
that requires something like a DeckLink Duo 2. The plugin exposes `keyer-mode`
for those cards but it is untested.

## Install

```bash
git clone https://github.com/YOUR_USER/openlp-decklink-output.git
cd openlp-decklink-output
./install.sh
```

This copies the plugin to:

```
~/.local/share/openlp/contrib/plugins/decklink/
```

Then restart OpenLP and open **Settings → DeckLink Output**.

To remove it: `./install.sh --uninstall`

If your OpenLP data directory is somewhere else, pass `--target /path/to/data`.
Note that OpenLP reads `contrib/` from the **OS-default** data directory, so an
`advanced/data path` override in OpenLP's settings does *not* move it.

## Configuration

**Settings → DeckLink Output**

- **Mirror the live output** — the master on/off switch.
- **Send to** — `DeckLink hardware`, or `Preview window` to test the whole
  pipeline with no card installed, or `Discard` to measure cost only.
- **Device number** / **Detect** — which DeckLink device. *Detect* probes each
  device number and reports which respond.
- **Video mode** — read from the installed sink where possible. Pick `1080p30`,
  not `1080p2997`, unless you specifically want 29.97.
- **Method** — capture backend; leave on *Automatic*.
- **Screen** — which screen to capture. *Follow the OpenLP display screen* is
  usually right.
- **Send black instead of the desktop when "Show Desktop" is used** — leave
  this **off** to mirror what the HDMI output does. See
  [Hide modes](#hide-modes).

## How it works

```
<capture> ! queue ! videorate ! videoscale ! videoconvert ! caps ─┐
                                                                  ├─ input-selector ! decklinkvideosink
videotestsrc pattern=black ! videoconvert ! caps ─────────────────┘
```

**No video frame passes through Python.** Capture, colour conversion and the
sink are all GStreamer C code, clocked by the DeckLink card's own hardware
clock. A Python timer pushing 1080p30 buffers would drop frames whenever OpenLP
did something expensive on the GUI thread; this design cannot.

**Why capture the screen rather than the display window?** OpenLP renders
lyrics into a `QWebEngineView` inside its display window, but plays video by
handing VLC the native window id of a *separate top-level window* —
`vlcplayer.py` gives the live video frame `Qt.Tool` flags, which promotes it out
of the display window. The two end up as siblings on the same rectangle. So any
window-targeted capture, and `QWidget.grab()`, would show lyrics and a black
hole where video should be. OpenLP's own code concedes this and falls back to a
desktop grab. An OpenLP core developer has confirmed there is no internal
video-output hook: *"The window OpenLP creates is where the display is
rendered. They cannot be separated."*

**Why the black branch?** It is a safety net, off by default — see
[Hide modes](#hide-modes) for when it is worth turning on.

### Hide modes

OpenLP has three ways of hiding the live display, and it renders all three into
its own display window. A screen capture therefore reproduces each one exactly
as HDMI does, with no special handling:

| Button | `HideMode` | What OpenLP does | What reaches SDI |
|---|---|---|---|
| **Black** | `Blank` | runs `toBlack` in the display | black |
| **Blank to Theme** | `Theme` | runs `toTheme` | the theme background |
| **Show Desktop** | `Screen` | goes transparent, or hides the window | **the desktop** |

`Show Desktop` passing the desktop through is deliberate: it is what the button
is for, and installations use it to put external content — a browser, a video
player, another application — on the programme feed. Forcing black there would
break that, so the plugin does not.

If you would rather your desktop never reach air, enable **Send black instead
of the desktop when "Show Desktop" is used**. It affects only that mode;
`Black` and `Blank to Theme` are captured as-is either way.

> If `Show Desktop` produces garbage or tearing on the SDI feed rather than a
> clean desktop, your compositor is probably not compositing the transparent
> display window well. Turn on OpenLP's
> **Settings → Advanced → "Disable transparent display"**, which makes OpenLP
> hide the window outright instead of making it transparent.

### Capture backends

| Backend | Session | Notes |
|---|---|---|
| `ximagesrc` | X11 | Simple, permissionless, well-trodden. `use-damage=false` forces full frames — damage-based capture emits nothing while a slide is static, which starves a hardware output. |
| `pipewiresrc` | Wayland | Negotiates an `xdg-desktop-portal` ScreenCast session over D-Bus. Stores a `restore_token` so the operator is not prompted on every start. |
| `videotestsrc` | any | Colour bars. Lets you prove the output path with no capture and no card. |

*Automatic* picks by session type and falls back to the test pattern, so the
plugin always starts and always has something to report rather than failing
silently.

## Diagnostics

`tools/smoketest.py` runs standalone, without OpenLP:

```bash
python3 tools/smoketest.py check       # what is installed, what is missing
python3 tools/smoketest.py modes       # video modes the sink accepts
python3 tools/smoketest.py devices     # which device numbers respond
python3 tools/smoketest.py bars --sink decklink --device 0 --seconds 10
python3 tools/smoketest.py mirror --region 0,0,1920,1080 --sink preview
python3 tools/smoketest.py snapshot --region 0,0,1920,1080 --out /tmp/frame.png
```

**Run `snapshot` while a video is playing on OpenLP's live output.** If the PNG
shows the video, screen capture is a valid frame source on your machine. If the
video area is black, the capture is not seeing VLC's window and this approach
needs revisiting — try setting a different VLC output module via OpenLP's
`media/vlc arguments` setting, or give OpenLP a dedicated screen.

## Keeping SDI alive when HDMI is unplugged

A capture backend needs a screen that actually exists. If the display output is
physically disconnected there is nothing to capture. Two options:

1. **HDMI EDID dummy plug** (~€10). Works at the DRM level, identically on X11
   and Wayland, and cannot be broken by a compositor update. This is the
   recommended route.
2. **A virtual output.** On Xorg, `xf86-video-dummy` gives a headless
   1920×1080 screen. Under Wayland/KWin this is considerably less well-trodden;
   the dummy plug is the more reliable answer.

## What is not yet proven

Being explicit, because a church A/V machine deserves it:

- **Never run against real DeckLink hardware.** No card was available during
  development. The sink configuration follows the documented properties but is
  unverified.
- **The Wayland portal path (`lib/portal.py`) has never been executed.** It has
  no test coverage that touches a live D-Bus. Treat X11 as the proven-by-design
  path and the portal as needing on-device testing.
- **Whether a screen capture includes VLC's video window is unverified** on any
  particular machine. This is what `smoketest.py snapshot` exists to answer.
- **The Desktop Video driver is the weakest link, and not something this plugin
  can fix.** It ships as DKMS modules wrapping a proprietary blob, with a
  history of breaking across Ubuntu kernel bumps. A kernel update can silently
  kill SDI output.
- Embedded SDI **audio** is not implemented. Audio stays on your existing path.
- Fill+key is exposed but untested.
- OpenLP 4.0 (currently alpha) replaces VLC with `QMediaPlayer` and PyQt5 with
  PySide6. `lib/compat.py` handles the binding; the capture approach still
  applies, but this is untested against 4.0.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest
python -m pytest tests/ -q
```

The tests deliberately cover the parts that can be verified without a desktop
session or hardware: launch-string construction, settings mapping, region
arithmetic and backend selection. `lib/launch.py` is kept free of Qt, D-Bus and
GStreamer imports for exactly this reason.

## Licence

GPL-3.0-or-later, matching OpenLP. See [LICENSE](LICENSE).

This plugin talks to DeckLink hardware through GStreamer's `decklinkvideosink`,
which Ubuntu already distributes. It does not link, vendor or redistribute the
Blackmagic SDK. That distinction matters: an NDI output plugin was proposed for
OpenLP and rejected on GPL/SDK licence-incompatibility grounds.

# rpi-cd-ripper

Automatic, headless CD Ripping solution.

Inspired by [aac/raspberrypi-cd-ripper](https://github.com/aac/raspberrypi-cd-ripper).

## Overview

When an audio CD is inserted, this project:
1.  **Identifies** the disc using MusicBrainz.
2.  **Rips & Encodes** tracks to FLAC using `abcde`.
3.  **Notifies** you via Telegram (with Album Art).
4.  **Ejects** the disc automatically.
5.  **Uploads** the ripped files to a [Copyparty](https://github.com/9001/copyparty) server in the background.

## Installation

With a fresh install of Raspberry Pi OS, execute the following command:

```shell
curl https://raw.githubusercontent.com/cpressland/rpi-cd-ripper/refs/heads/main/install.sh | sudo bash -
```

> [!NOTE]
> The Raspberry Pi can sometimes aggressively sleep its WiFi interface.
> You can disable this with `sudo raspi-config` > "Advanced Options" > "WLAN Power Save" > "No".

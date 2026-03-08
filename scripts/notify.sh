#!/bin/bash
# macOS Native Notifications for Clawdia system
# Uses osascript for native notifications Josef can see

set -e
cd /Users/josefhofman/Clawdia

TITLE="${1:-Clawdia}"
MESSAGE="${2:-System update}"
SOUND="${3:-default}"  # default, Glass, Ping, Pop, Purr

osascript -e "display notification \"$MESSAGE\" with title \"$TITLE\" sound name \"$SOUND\""

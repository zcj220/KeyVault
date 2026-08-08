#!/bin/bash
# 生成带自定义图标、可双击的 KeyVault.app（macOS）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/KeyVault.app"
ICON="$ROOT/assets/AppIcon.icns"
TMP_SCRIPT="$(mktemp /tmp/keyvault-launch.XXXXXX.applescript)"

if [[ ! -f "$ICON" ]]; then
  echo "缺少图标: $ICON"
  exit 1
fi
if [[ ! -x "$ROOT/scripts/launch-ui.sh" ]]; then
  chmod +x "$ROOT/scripts/launch-ui.sh"
fi

rm -rf "$APP"

# 构建时把项目路径写进脚本，Finder 双击最稳
LAUNCHER="$ROOT/scripts/launch-ui.sh"
cat > "$TMP_SCRIPT" <<APPLESCRIPT
on run
  try
    do shell script "/bin/bash " & quoted form of "$LAUNCHER"
  on error errMsg number errNum
    display dialog "启动失败：" & errMsg buttons {"好"} default button 1 with title "KeyVault"
  end try
end run
APPLESCRIPT

osacompile -o "$APP" "$TMP_SCRIPT" >/dev/null
rm -f "$TMP_SCRIPT"

mkdir -p "$APP/Contents/Resources"
cp "$ICON" "$APP/Contents/Resources/applet.icns"
cp "$ICON" "$APP/Contents/Resources/AppIcon.icns"
printf '%s\n' "$ROOT" > "$APP/Contents/Resources/project-root"

PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundleName KeyVault' "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c 'Set :CFBundleDisplayName KeyVault' "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c 'Add :CFBundleDisplayName string KeyVault' "$PLIST" || true
/usr/libexec/PlistBuddy -c 'Set :CFBundleIconFile applet' "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.xinzaoai.keyvault.launcher' "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string com.xinzaoai.keyvault.launcher' "$PLIST" || true

xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep -s - "$APP" >/dev/null

DEST_DESKTOP="$HOME/Desktop/KeyVault.app"
rm -rf "$DEST_DESKTOP"
rm -f "$HOME/Desktop/KeyVault启动.command"
cp -R "$APP" "$DEST_DESKTOP"
xattr -cr "$DEST_DESKTOP" 2>/dev/null || true
codesign --force --deep -s - "$DEST_DESKTOP" >/dev/null

# 验证
echo "签名检查:"
codesign -dv "$DEST_DESKTOP" 2>&1 | head -5 || true
echo "模拟打开..."
open "$DEST_DESKTOP"
sleep 2
curl -sf -o /dev/null -w "网页状态: %{http_code}\n" "http://127.0.0.1:8799/" || echo "网页状态: 未就绪"

echo "已生成桌面: $DEST_DESKTOP"
echo "若双击 KeyVault.app 没反应：右键 → 打开；或双击「打开KeyVault.command」"
# 尝试写入 Finder 自定义图标（本机）
if [[ -f "$ROOT/assets/keyvault-app-icon.png" ]]; then
  osascript >/dev/null 2>&1 <<OSA || true
use framework "AppKit"
set image to current application's NSImage's alloc()'s initWithContentsOfFile:"$ROOT/assets/keyvault-app-icon.png"
set ws to current application's NSWorkspace's sharedWorkspace()
ws's setIcon:image forFile:"$DEST_DESKTOP" options:0
ws's setIcon:image forFile:"$APP" options:0
OSA
fi
